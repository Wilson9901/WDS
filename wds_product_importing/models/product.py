# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields, api


class ProductProduct(models.Model):
    _inherit = 'product.product'

    _sql_constraints = [
        ('default_code_unique', 'UNIQUE(default_code)', 'You can not have two records with the same default code!'),
        ('unique_id_unique', 'UNIQUE(unique_id)', 'You can not have two records with the same unique id!'), 
    ]

    size = fields.Char(string='Size')
    unit = fields.Char(string='Unit')
    unitqty = fields.Char(string='Unit Quantity')
    base_list_price = fields.Float(string='Variant Base Price')

    @api.depends('list_price', 'base_list_price')
    @api.depends_context('uom')
    def _compute_product_lst_price(self):
        to_uom = None
        if 'uom' in self._context:
            to_uom = self.env['uom.uom'].browse(self._context['uom'])

        for product in self:
            price = product.base_list_price if product.base_list_price != 0 else product.list_price
            if to_uom:
                list_price = product.uom_id._compute_price(price, to_uom)
            else:
                list_price = price
            product.lst_price = list_price

class SupplierInfo(models.Model):
    _inherit = 'product.supplierinfo'

    mfr_num = fields.Char(string='Manufacturer Number')
    mfr_name = fields.Char(string='Manufacturer Name')
