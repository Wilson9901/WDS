# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields, api


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # name = fields.Char(string='SHORT DESCRIPTION', index=True, required=True, translate=True)
    # description = fields.Text(string='LONG DESCRIPTION', translate=True)

    categ_one = fields.Char(string='CATEGORY1')
    categ_two = fields.Char(string='CATEGORY2')
    unspsc = fields.Char(string='UNSPSC Code')

    image_1920 = fields.Binary(string='IMAGE')
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
