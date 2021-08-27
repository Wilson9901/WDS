# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields, api

import base64
import requests
import re
import logging



_logger = logging.getLogger(__name__)

try:
    import xlrd
    try:
        from xlrd import xlsx
    except ImportError:
        xlsx = None
except ImportError:
    xlrd = xlsx = None


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    name = fields.Char(string='SHORT DESCRIPTION', index=True, required=True, translate=True)
    description = fields.Text(string='LONG DESCRIPTION', translate=True)

    categ_one = fields.Char(string='CATEGORY1')
    categ_two = fields.Char(string='CATEGORY2')
    unspsc = fields.Char(string='UNSPSC Code')

    # image_1920 = fields.Binary(string='IMAGE')
    product_url = fields.Char(string='PRODUCT URL')
    weblink = fields.Char(string='ADDITIONAL WEBLINK')
    weblink_title = fields.Char(string='ADDITIONAL WEBLINK_TITLE')

    upc_code = fields.Char(string='UPC')
    upn_code = fields.Char(string='UPN')

    # purchase tab
    product_code = fields.Char(string='CATNO')
    mfr_num = fields.Char(string='MFRNO')
    mfr_name = fields.Char(string='MFRNAME')
    vendor_name = fields.Char(string='Vendor Name')

    # product variants
    size_1 = fields.Char(string='SIZE_1')
    unit_1 = fields.Char(string='UNIT_1')
    unitqty_1 = fields.Char(string='UNITQTY_1')
    cost_1 = fields.Float(string='COST1')
    list_1 = fields.Float(string='LIST1')

    size_2 = fields.Char(string='SIZE_2')
    unit_2 = fields.Char(string='UNIT_2')
    unitqty_2 = fields.Char(string='UNITQTY_2')
    cost_2 = fields.Float(string='COST2')
    list_2 = fields.Float(string='LIST2')

    size_3 = fields.Char(string='SIZE_3')
    unit_3 = fields.Char(string='UNIT_3')
    unitqty_3 = fields.Char(string='UNITQTY_3')
    cost_3 = fields.Float(string='COST3')
    list_3 = fields.Float(string='LIST3')

    size = fields.Char(related='product_variant_id.size')
    unit = fields.Char(related='product_variant_id.unit')
    unitqty = fields.Char(related='product_variant_id.unitqty')

    to_remove = fields.Boolean(string='To Remove', default=False)

    attachment_id = fields.Many2one(comodel_name='ir.attachment')

    '''
    import all products from documents in the designated product folder then move attachment to different folder
    '''
    def _cron_import_all_products(self):
        company = self.company_id or self.env.company
        docs = company.import_folder.document_ids
        self._import_documents(documents=docs)

    def _import_documents(self, documents, batch_size=80):
        '''
        input: documents
        output: product.templates, product.products, imported documents placed in completed folder
        '''
        company = self.company_id or self.env.company
        _logger.info('importing document(s)')
        for doc in documents:
            data = base64.b64decode(doc.attachment_id.datas)
            sheet = xlrd.open_workbook(file_contents=data).sheet_by_index(0)
            fields = self._get_fields_from_sheet(sheet)
            while batch_size * doc.attachment_id.batch < sheet.nrows:
                templates = self.env['product.template']
                vals_to_create = []
                current_batch = [batch_size * doc.attachment_id.batch or 1, (batch_size * doc.attachment_id.batch) + 500]
                if current_batch[1] > sheet.nrows:
                    current_batch[1] = sheet.nrows
                for row_num in range(current_batch[0], current_batch[1]):
                    # go through sheet, creating or updating product.templates and product.products
                    vals = self.with_context(attachment_id=doc.attachment_id.id)._prepare_product_template_vals_from_row(sheet, row_num, fields)
                    product_to_update = self.search([('product_code', '=', vals.get('product_code'))], limit=1) if 'product_code' in vals else None
                    if product_to_update:
                        _logger.info('updating product: %s', vals.get('product_code'))
                        product_to_update._update_product(vals)
                    else:
                        vals_to_create.append(vals)
                if vals_to_create:
                    _logger.info('creating products in batch: %s', doc.attachment_id.batch)
                    templates += self.create(vals_to_create)
                    self._create_variants_from_fields(templates)
                doc.attachment_id.batch += 1
                self.env.cr.commit()
                '''
                commit cursor here, pass current attachment_id to products
                '''
            doc.folder_id = company.complete_import_folder.id

        self.env['product.template'].search([]).write({'to_remove': False})
        self.env['product.template'].search([('attachment_id', 'not in', documents.mapped('attachment_id').ids)]).write({'to_remove': True})

        self.env['product.product'].search([]).write({'to_remove': False})
        self.env['product.product'].search([('attachment_id', 'not in', documents.mapped('attachment_id').ids)]).write({'to_remove': True})

        _logger.info('done')
        return True

    def _get_fields_from_sheet(self, sheet):
        '''
        input: xlsx sheet, use header to match table rows
        output: list matching column of sheet w/ corresponding field, None if no field can be found
        need to get correct type from field here
        fields = [None, None, ...]
        create list of field name, string, type
        if field in sheet, change None at index of sheet column to field at fields[index]
        '''
        fields = [None] * sheet.ncols
        product_fields = []
        for name, field in self.fields_get().items():
            if field.get('deprecated', False) is not False:
                continue
            field_value = {
                'name': name,
                'string': field['string'].lower(),
                'type': field['type'],
            }
            product_fields.append(field_value)

        for idx in range(sheet.ncols):
            curr_col = sheet.cell_value(0, idx).lower().strip()
            for field in product_fields:
                if curr_col == field['name'] or curr_col == field['string']:
                    fields[idx] = field
                elif re.search('^image', curr_col):
                    fields[idx] = {'name': 'image_1920', 'string': 'image', 'type': 'binary'}
        return fields

    def _prepare_product_template_vals_from_row(self, sheet, row_num, fields):
        '''
        input: xlsx sheet, row to create product from, list of fields(matching index with column of sheet)
        output: dictionary with field name:val of non empty cells
        '''
        base_import = self.env['base_import.import']
        vals = {
            'categ_id': self.env.ref('product.product_category_all').id,
            'product_variant_ids': [[6, False, []]],
            'purchase_line_warn': 'no-message',
            'sale_line_warn': 'no-message',
            'tracking': 'none',
            'type': 'consu',
            'uom_id': self.env['uom.uom'].search([], limit=1, order='id').id,
            'uom_po_id': self.env['uom.uom'].search([], limit=1, order='id').id,
            'attachment_id': self.env.context.get('attachment_id')
        }
        # can use instead self.env.ref('uom.product_uom_unit')
        for idx in range(len(fields)):
            current_field = sheet.cell_value(row_num, idx)
            if fields[idx] and fields[idx]['name'] == 'image_1920' and sheet.cell_type(row_num, idx) != 0:
                try:
                    vals[fields[idx]['name']] = base_import._import_image_by_url(sheet.cell_value(row_num, idx), requests.Session(), 'image_1920', row_num)
                except ValueError as e:
                    _logger.warning('Image timeout on product at row {}'.format(row_num))
                except:
                    _logger.warning('Unexpected error importing image on product at row {}'.format(row_num))
            elif fields[idx] and sheet.cell_type(row_num, idx) != 0:
                val = sheet.row_values(row_num)
                if fields[idx]['type'] in ['char', 'text', 'html']:
                    try:
                        vals[fields[idx]['name']] = str(int(sheet.cell_value(row_num, idx)))
                    except Exception:
                        vals[fields[idx]['name']] = sheet.cell_value(row_num, idx)
                else:
                    vals[fields[idx]['name']] = sheet.cell_value(row_num, idx)
            elif fields[idx]:
                if fields[idx]['type'] in ['float', 'int']:
                    vals[fields[idx]['name']] = 0
                else:
                    vals[fields[idx]['name']] = False
        return vals

    def _prepare_product_product_vals(self, product, idx):
        return {
            'to_remove': False,
            'base_list_price': product['list_' + str(idx)],
            'standard_price': product['cost_' + str(idx)],
            'unit': product['unit_' + str(idx)],
            'unitqty': product['unitqty_' + str(idx)],
            'size': product['size_' + str(idx)],
            'is_published': True,
            'default_code': ''.join((product['product_code'], product['unit_' + str(idx)], product['unitqty_' + str(idx)])),
            'attachment_id': product['attachment_id'].id
        }

    def _create_attribute(self, size):
        '''
        create attribute.value and return it or search and return existing attribute.value
        '''
        size_attr = self.env['product.attribute'].search([('name', '=', 'Size')], limit=1)
        attribute_value = size_attr.value_ids.search([('name', '=', size)], limit=1)
        if attribute_value:
            return attribute_value
        else:
            return self.env['product.attribute.value'].create({'attribute_id': size_attr.id, 'name': size})

    def _create_variants_from_fields(self, templates):
        # self.search([('id', 'in', ids)])
        size_attr = self.env['product.attribute'].search([('name', '=', 'Size')], limit=1)
        # create variants based on size_n
        # create or fetch id of attribute
        for product in templates:
            attribute_values = self.env['product.attribute.value']
            for idx in range(1, 4):
                if product['size_' + str(idx)]:
                    attribute_value = self._create_attribute(product['size_' + str(idx)])
                    attribute_values += attribute_value
            # create attribute lines for values of variants
            if attribute_values:
                product.write({
                    'attribute_line_ids': [[0, False, {'attribute_id': size_attr.id, 'value_ids': [[6, False, attribute_values.ids]]}]]
                })
                for variant in product.product_variant_ids:
                    for idx in range(1, 4):
                        # variant should only have one tag, but in case multiple, using mapped
                        if product['size_' + str(idx)] and product['size_' + str(idx)] in variant.product_template_attribute_value_ids.mapped('name'):
                            vals = self._prepare_product_product_vals(product, idx)
                            variant.write(vals)
            else:
                # if size_(1,2,3) are empty, update product.template fields
                product.product_variant_ids[:1].write({
                    'base_list_price': product['list_1'],
                    'standard_price': product['cost_1'],
                    'unit': product['unit_1'],
                    'unitqty': product['unitqty_1'],
                    # 'size': product['size_1'],
                    'is_published': True,
                    'default_code': ''.join((product['product_code'], product['unit_1'], product['unitqty_1'])),
                    'attachment_id': product['attachment_id'].id
                })

                product.write({
                    'standard_price': product['cost_1']
                })

            pricelists = product._generate_pricelists()
            # set list price and standard price to list and cost of lowest unitqty variant
            min = product.product_variant_ids[:1]
            for variant in product.product_variant_ids:
                if variant.lst_price < min.lst_price:
                    min = variant
            product.write({
                'seller_ids': pricelists,
                'is_published': True,
                'list_price': min.lst_price
            })
        return templates

    def _generate_pricelists(self):
        partner_id = self.env['res.partner'].search(
            [('name', '=', self.vendor_name)], limit=1).id
        if not partner_id:
            partner_id = self.env['res.partner'].create([{
                'name': self.vendor_name,
                'type': 'contact',
            }]).id
        if len(self.product_variant_ids) > 1:
            pricelists = []
            for product in self.product_variant_ids.filtered(lambda p: p.to_remove is False):
                pricelists.append((0, False, {'sequence': 1, 'name': partner_id, 'product_id': product.id, 'product_name': False, 'product_code': product.default_code,
                                   'currency_id': self.env.ref('base.main_company').currency_id.id, 'mfr_name': product.mfr_name, 'mfr_num': product.mfr_num,
                                   'date_start': False, 'date_end': False, 'company_id': self.env.company.id, 'min_qty': 0, 'price': product.standard_price, 'delay': 1}))
            return pricelists
        else:
            return [(0, False, {'sequence': 1, 'name': partner_id, 'product_id': False, 'product_name': False, 'product_code': self.default_code,
                    'currency_id': self.env.ref('base.main_company').currency_id.id, 'mfr_name': self.mfr_name, 'mfr_num': self.mfr_num,
                    'date_start': False, 'date_end': False, 'company_id': self.env.company.id, 'min_qty': 0, 'price': self.cost_1, 'delay': 1})]

    def _update_product(self, vals):
        '''
        input: product to update is self, value dict with product variants/product to update
        output: update product/variant
        update template, update variants, unlink old variant if variants change, create new variant?
        '''
        self.ensure_one()
        # ids to update: self.product_variant_ids
        # search for values
        # remove default values and values that are unchanged, product_variant_ids will cause apples to oranges warning but doesnt matter
        product = self
        product.write({'to_remove': False})
        to_rem = ['categ_id', 'product_variant_ids', 'purchase_line_warn', 'sale_line_warn', 'tracking', 'type', 'uom_id', 'uom_po_id']
        for key, val in vals.items():
            try:
                if val == self[key].id:
                    to_rem.append(key)
            except Exception:
                if val == self[key]:
                    to_rem.append(key)
                # elif not val and product.fields_get(key)[key]['type'] != 'boolean':
                #     to_rem.append(key)
        [vals.pop(key) for key in set(to_rem)]
        # find size_ in vals, only new values will exist
        new_variants = [key for key, val in vals.items() if key.startswith('size_') and val]

        if not vals:
            return 0

        product.write(vals)

        # update variants
        product._update_variants()

        # create new variants
        if len(new_variants):
            '''
            create new attributes and update attribute_line_ids on product
            '''
            size_attr = self.env['product.attribute'].search([('name', '=', 'Size')], limit=1)
            attribute_values = self.env['product.attribute.value']
            # for key, size in enum(new_variants):
            for size in new_variants:
                attribute_value = product._create_attribute(product[size])
                attribute_values += attribute_value
            attribute_line = product.attribute_line_ids.filtered(lambda r: r.attribute_id == size_attr)
            # variants get created here
            if attribute_line:
                updated_pav = attribute_line.value_ids + attribute_values
                product.write({'attribute_line_ids': [[1, attribute_line.id, {'value_ids': [[6, False, updated_pav.ids]]}]]})
            else:
                product.write({
                    'attribute_line_ids': [[0, False, {'attribute_id': size_attr.id, 'value_ids': [[6, False, attribute_values.ids]]}]]
                })
            # get newly created variants and update with _prepare_product_product_vals(self, num)
            for size in new_variants:
                new_variant_vals = self._prepare_product_product_vals(product, int(size[-1]))
                for variant in product.product_variant_ids:
                    x = variant.product_template_attribute_value_ids.mapped('name')
                    y = attribute_values.mapped('name')
                    if product[size] in variant.product_template_attribute_value_ids.mapped('name'):
                        variant.write(new_variant_vals)

        if len(product.product_variant_ids) == 1 and ('list_1' in vals or 'cost_1' in vals):
            for field in [('list_price', 'list_1'), ('standard_price', 'cost_1')]:
                if field[1] in vals:
                    product.write({field[0]: vals[field[1]]})

        product._update_pricelists()

        min = product.product_variant_ids.filtered(lambda p: p.active)[:1]
        for variant in product.product_variant_ids.filtered(lambda p: p.active):
            if variant.lst_price < min.lst_price:
                min = variant
        product.list_price = min.lst_price

    def _update_variants(self):
        '''
        input: updated product_template
        out: updated variants, set flag to filter unused products
        '''
        # variant_ids = self.product_variant_ids
        # variant_ids.write({'to_remove': False})
        for idx in range(1, 4):
            if self['size_' + str(idx)]:
                vals = self._prepare_product_product_vals(self, idx)
                [vals.pop(key) for key in ['size', 'is_published']]
                # need to match by attribute, in this case, find attr by size
                for variant in self.product_variant_ids:
                    if self['size_' + str(idx)] and self['size_' + str(idx)] in variant.product_template_attribute_value_ids.mapped('name'):
                        to_rem = []
                        for key, val in vals.items():
                            if val == variant[key]:
                                to_rem.append(key)
                        [vals.pop(key) for key in set(to_rem)]
                        if vals:
                            variant.write(vals)
                        # variant_ids -= variant
                        break
        # variant_ids will either be empty recordset or recordset of variants to remove
        # if len(variant_ids) and len(self.product_variant_ids) > 1:
        #     variant_ids.write({'to_remove': True})

    def _update_pricelists(self):
        self.ensure_one()
        pricelists = self._generate_pricelists()
        self.write({'seller_ids': [(5, 0, 0)]})
        self.write({'seller_ids': pricelists})
