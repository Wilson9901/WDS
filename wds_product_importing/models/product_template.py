# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields, api

import base64
import requests
import re
import xmlrpc.client
from PIL import Image
import io

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
    weblink_title = fields.Char(string='ADDITIONAL WEBLINK TITLE')

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
    list_1 = fields.Float(string='LIST_1')

    size_2 = fields.Char(string='SIZE_2')
    unit_2 = fields.Char(string='UNIT_2')
    unitqty_2 = fields.Char(string='UNITQTY_2')
    cost_2 = fields.Float(string='COST2')
    list_2 = fields.Float(string='LIST_2')

    size_3 = fields.Char(string='SIZE_3')
    unit_3 = fields.Char(string='UNIT_3')
    unitqty_3 = fields.Char(string='UNITQTY_3')
    cost_3 = fields.Float(string='COST3')
    list_3 = fields.Float(string='LIST_3')

    '''
    import all products from documents in the designated product folder then move attachment to different folder
    '''

    def _cron_import_all_products(self):
        company = self.company_id or self.env.company
        docs = company.product_folder.document_ids
        self._import_documents(docs)

    def _get_fields_from_sheet(self, sheet):
        '''
        input: xlsx sheet, use header to match table rows
        output: list matching column of sheet w/ corresponding field, None if no field can be found


        fields = [None, None, ...]
        get all fields from model
        get descriptions from model
        create {description:field}
        if field in sheet, change None at index of sheet column to field at fields[index]
        '''
        fields = [None] * sheet.ncols
        field_names = self.env['product.template']._fields
        field_strings = [self.env['product.template']._fields[val].string.lower() for val in field_names]
        field_pairs = dict(zip(field_strings, field_names))

        for idx in range(sheet.ncols):
            if sheet.cell_value(0, idx).lower().strip() in field_names:
                fields[idx] = sheet.cell_value(0, idx).lower().strip()
            elif sheet.cell_value(0, idx).lower().strip() in field_strings:
                fields[idx] = field_pairs[sheet.cell_value(0, idx).lower().strip()]
            # elif re.search('^external.?id$', sheet.cell_value(0, idx).lower().strip()):
            #     fields[idx] = 'external id'
            elif re.search('^image', sheet.cell_value(0, idx).lower().strip()):
                fields[idx] = 'image_1920'
        return fields

    def _get_vals_from_row(self, sheet, row_num, fields):
        '''
        input: xlsx sheet, row to create product from, list of fields(matching index with column of sheet)
        output: dictionary with field:val of non empty cells
        '''
        def grabImage(url):
            img = Image.open(requests.get(url, stream=True).raw)
            image_buffer = io.BytesIO()
            img = img.convert("RGB")
            img.save(image_buffer, format="JPEG")
            image_data = base64.b64encode(image_buffer.getvalue())
            return image_data

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
            if fields[idx] == 'image_1920' and sheet.cell_type(row_num, idx) != 0:
                vals[fields[idx]] = grabImage(sheet.cell_value(row_num, idx))
            elif fields[idx] is not None and sheet.cell_type(row_num, idx) != 0:
                vals[fields[idx]] = sheet.cell_value(row_num, idx)
        return vals

    def _create_variants_from_fields(self, templates):
        # self.search([('id', 'in', ids)])
        size_attr = self.env['product.attribute'].search([('name', '=', 'Size')], limit=1)
        # create variants based on size_n
        for product in templates:
            size_attr_vals = []
            for idx in range(1, 4):
                if product['size_' + str(idx)]:
                    # need to search before writing
                    variant_value = size_attr.value_ids.search([('name', '=', product['size_' + str(idx)])])
                    if not variant_value:
                        size_attr.write({
                            'value_ids': [[0, 0, {'name': product['size_' + str(idx)]}]]
                        })
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
                            variant.write({
                                'base_list_price': product['list_' + str(idx)],
                                'standard_price': product['cost_' + str(idx)],
                                'unit': product['unit_' + str(idx)],
                                'unitqty': product['unitqty_' + str(idx)],
                                'size': product['size_' + str(idx)],
                                'is_published': True,
                            })

            partner_id = self.env['res.partner'].search(
                [('name', '=', product['vendor_name'])], limit=1).id
            if not partner_id:
                partner_id = self.env['res.partner'].create([{
                    'name': product['vendor_name'],
                    'type': 'contact',
                }]).id
            product.write({
                'seller_ids': [[0, False, {'sequence': 1, 'name': partner_id, 'product_id': False, 'product_name': False, 'product_code': product['product_code'],
                                            'currency_id': self.env.ref('base.main_company').currency_id.id, 'mfr_name':product['mfr_name'], 'mfr_num':product['mfr_num'],
                                            'date_start': False, 'date_end': False, 'company_id': self.env.company.id, 'min_qty': 0, 'price': 0, 'delay': 1}]],
                'is_published': True
            })
        return templates

    def _import_documents(self, documents):
        '''
        import documents from cron or manually from server action on documents.document
        '''
        company = self.company_id or self.env.company
        templates = self.env['product.template']
        for doc in documents:
            data = base64.b64decode(doc.attachment_id.datas)
            sheet = xlrd.open_workbook(file_contents=data).sheet_by_index(0)
            vals_to_create = []
            fields = self._get_fields_from_sheet(sheet)
            for row_num in range(1, sheet.nrows):
                vals = self._get_vals_from_row(sheet, row_num, fields)
                product_to_update = self.search([('default_code', '=', vals.pop('default_code'))], limit=1) if 'default_code' in vals else None
                if product_to_update:
                    # product = self.env['ir.model.data'].xmlid_to_res_id(vals.pop('external id'))
                    product_to_update.write(vals)
                    templates += product
                else:
                    vals_to_create.append(vals)
            if vals_to_create:
                templates += self.create(vals_to_create)
        if templates:
            self._create_variants_from_fields(templates)
        doc.folder_id = company.import_folder
        return templates
