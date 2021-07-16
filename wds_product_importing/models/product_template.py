# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields, api

import base64
import requests
import re
import logging
# import xmlrpc.client
# from PIL import Image
# import io
# import pudb

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

    '''
    import all products from documents in the designated product folder then move attachment to different folder
    '''

    def _cron_import_all_products(self):
        company = self.company_id or self.env.company
        docs = company.import_folder.document_ids
        self._import_documents(docs)

    def _import_documents(self, documents):
        '''
        input: documents
        output: product.templates, product.products, imported documents placed in completed folder

        todo: create rollback and add batches
        '''
        company = self.company_id or self.env.company
        templates = self.env['product.template']
        _logger.info('importing document(s)')
        for doc in documents:
            data = base64.b64decode(doc.attachment_id.datas)
            sheet = xlrd.open_workbook(file_contents=data).sheet_by_index(0)
            vals_to_create = []
            fields = self._get_fields_from_sheet(sheet)
            for row_num in range(1, sheet.nrows):
                # go through sheet, creating or updating product.templates and product.products
                vals = self._prepare_product_template_vals_from_row(sheet, row_num, fields)
                product_to_update = self.search([('product_code', '=', vals.get('product_code'))], limit=1) if 'product_code' in vals else None
                if product_to_update:
                    _logger.info('updating product: %s', vals.get('product_code'))
                    product_to_update._update_product(vals)
                else:
                    vals_to_create.append(vals)
            if vals_to_create:
                templates += self.create(vals_to_create)
            if len(templates):
                self._create_variants_from_fields(templates)
            doc.folder_id = company.complete_import_folder.id
        _logger.info('done')
        return templates

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
            'type': 'product',
            'uom_id': self.env['uom.uom'].search([], limit=1, order='id').id,
            'uom_po_id': self.env['uom.uom'].search([], limit=1, order='id').id
        }
        # can use instead self.env.ref('uom.product_uom_unit')
        for idx in range(len(fields)):
            if fields[idx] and fields[idx]['name'] == 'image_1920' and sheet.cell_type(row_num, idx) != 0:
                vals[fields[idx]['name']] = base_import._import_image_by_url(sheet.cell_value(row_num, idx), requests.Session(), 'image_1920', row_num)
            elif fields[idx] and sheet.cell_type(row_num, idx) != 0:
                val = sheet.row_values(row_num)
                if fields[idx]['type'] in ['char', 'text', 'html']:
                    try:
                        vals[fields[idx]['name']] = str(int(sheet.cell_value(row_num, idx)))
                    except Exception:
                        vals[fields[idx]['name']] = sheet.cell_value(row_num, idx)
                else:
                    vals[fields[idx]['name']] = sheet.cell_value(row_num, idx)
        return vals

    def _prepare_product_product_vals(self, product, idx):
        return {
            'base_list_price': product['list_' + str(idx)],
            'standard_price': product['cost_' + str(idx)],
            'unit': product['unit_' + str(idx)],
            'unitqty': product['unitqty_' + str(idx)],
            'size': product['size_' + str(idx)],
            'is_published': True,
            'default_code': ''.join((product['product_code'], product['unit_' + str(idx)]))
        }

    def _create_attribute(self, size):
        size_attr = self.env['product.attribute'].search([('name', '=', 'Size')], limit=1)
        variant_value = size_attr.value_ids.search([('name', '=', size)], limit=1)
        if not variant_value:
            size_attr.write({
                'value_ids': [[0, 0, {'name': size}]]
            })

    def _create_variants_from_fields(self, templates):
        # self.search([('id', 'in', ids)])
        size_attr = self.env['product.attribute'].search([('name', '=', 'Size')], limit=1)
        # create variants based on size_n
        # create or fetch id of attribute
        for product in templates:
            size_attr_vals = []
            for idx in range(1, 4):
                if product['size_' + str(idx)]:
                    self._create_attribute(product['size_' + str(idx)])
                    size_attr_vals.append(product['size_' + str(idx)])
            # create attribute lines for values of variants
            if size_attr_vals:
                size_attr_ids = size_attr.value_ids.search(
                    [('name', 'in', size_attr_vals)])
                product.write({
                    'attribute_line_ids': [[0, False, {'attribute_id': size_attr.id, 'value_ids': [[6, False, size_attr_ids.mapped('id')]]}]]
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
                # product.product_variant_id.write({
                    'base_list_price': product['list_1'],
                    'standard_price': product['cost_1'],
                    'unit': product['unit_1'],
                    'unitqty': product['unitqty_1'],
                    # 'size': product['size_1'],
                    'is_published': True,
                    'default_code': ''.join((product['product_code'], product['unit_1']))
                })

                product.write({
                    'list_price': product['list_1'],
                    'standard_price': product['cost_1']
                })

            pricelists = product._generate_pricelists()
            product.write({
                'seller_ids': pricelists,
                'is_published': True
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
            for product in self.product_variant_ids:
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
        to_rem = ['categ_id', 'product_variant_ids', 'purchase_line_warn', 'sale_line_warn', 'tracking', 'type', 'uom_id', 'uom_po_id']
        for key, val in vals.items():
            try:
                if val == self[key].id:
                    to_rem.append(key)
            except Exception:
                if val == self[key]:
                    to_rem.append(key)

        [vals.pop(key) for key in set(to_rem)]
        # find size_ in vals, only new values will exist
        new_variants = [key for key in vals.keys() if key.startswith('size_')]

        if not vals:
            return 0

        self.write(vals)

        # update variants
        self._update_variants()

        # create new variants
        if len(new_variants):
            size_attr = self.env['product.attribute'].search([('name', '=', 'Size')], limit=1)
            size_attr_vals = []
            for size in new_variants:
                self._create_attribute(self[size])
                size_attr_vals.append(self[size])
            size_attr_ids = size_attr.value_ids.search([('name', 'in', size_attr_vals)])
            attribute_line = self.env['product.template.attribute.line'].search([('product_tmpl_id', '=', self.id), ('attribute_id', '=', size_attr.id)], limit=1)
            # variants get created here
            if attribute_line:
                attribute_line.write({'value_ids': [[0, False, size_attr_ids.mapped('id')]]})
            else:
                self.write({
                    'attribute_line_ids': [[0, False, {'attribute_id': size_attr.id, 'value_ids': [[6, False, size_attr_ids.mapped('id')]]}]]
                })
            # get newly created variants and update with _prepare_product_product_vals(self, num)
            for size in new_variants:
                new_variant_vals = self._prepare_product_product_vals(self, int(size[-1]))
                for variant in self.product_variant_ids:
                    if self[size] in variant.product_template_attribute_value_ids.mapped('name'):
                        variant.write(new_variant_vals)
        
        # # edge case that might not matter
        # # for products w/o variant, if cost_1/list_1 changes, need to update price
        # # after variants created/updated
        # # list_1 and cost_1 could differ however
        if len(self.product_variant_ids) == 1 and ('list_1' in vals or 'cost_1' in vals):
            for field in [('list_price', 'list_1'), ('standard_price', 'cost_1')]:
                if field[1] in vals:
                    self.write({field[0]: vals[field[1]]})

        self._update_pricelists()

    def _update_variants(self):
        '''
        input: updated product_template
        out: updated variants, set flag to filter unused products
        '''
        variant_ids = self.product_variant_ids
        for idx in range(1, 4):
            if self['size_' + str(idx)]:
                vals = self._prepare_product_product_vals(self, idx)
                [vals.pop(key) for key in ['size', 'unit', 'is_published']]
                for variant in self.product_variant_ids:
                    if vals['default_code'] == variant.default_code:
                        to_rem = []
                        for key, val in vals.items():
                            if val == variant[key]:
                                to_rem.append(key)
                        [vals.pop(key) for key in set(to_rem)]
                        if vals:
                            variant.write(vals)
                        variant_ids -= variant
        # variant_ids will either be empty recordset or recordset of variants to remove
        if len(variant_ids):
            variant_ids.to_remove = True

    def _update_pricelists(self):
        partner_id = self.env['res.partner'].search(
            [('name', '=', self.vendor_name)], limit=1).id
        if not partner_id:
            partner_id = self.env['res.partner'].create([{
                'name': self.vendor_name,
                'type': 'contact',
            }]).id
        update_fields = [('standard_price', 'price'), ('mfr_name', 'mfr_name'), ('mfr_num', 'mfr_num')]
        if len(self.product_variant_ids) > 1:
            # match variant to pricelist, update price, mfr_name,num?
            # remove variant from variants
            variants = self.product_variant_ids.filtered(lambda r: r.to_remove is False)
            for pricelist in self.seller_ids:
                for variant in self.product_variant_ids.filtered(lambda r: r.to_remove is False):
                    vals = {}
                    if pricelist.product_id.id == variant.id:
                        for field in update_fields:
                            if variant[field[0]] != pricelist[field[1]]:
                                vals[field[1]] = variant[field[0]]
                    if vals:
                        pricelist.write(vals)
                        variants -= variant
            if len(variants):
                # remaining variants do not have a pricelist yet
                pricelists = []
                for variant in variants:
                    pricelists.append((0, False, {'sequence': 1, 'name': partner_id, 'product_id': variant.id, 'product_name': False, 'product_code': variant.default_code,
                                                  'currency_id': self.env.ref('base.main_company').currency_id.id, 'mfr_name': variant.mfr_name, 'mfr_num': variant.mfr_num,
                                                  'date_start': False, 'date_end': False, 'company_id': self.env.company.id, 'min_qty': 0, 'price': variant.standard_price, 'delay': 1}))
                self.write({'seller_ids': pricelists})
        else:
            # case where product w/o variants updates
            vals = {}
            for field in update_fields:
                if self.seller_ids and self[field[0]] != self.seller_ids[:1][field[1]]:
                    vals[field[1]] = self[field[0]]
            if vals:
                self.seller_ids[:1].write(vals)

# cant update size/unit as unit is used to generate the unique id


class SupplierInfo(models.Model):
    _inherit = 'product.supplierinfo'

    to_remove = fields.Boolean(related='product_id.to_remove')
