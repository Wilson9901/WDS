# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields, api


class ProductProduct(models.Model):
    _inherit = 'product.product'

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
            if to_uom:
                list_price = product.uom_id._compute_price(product.base_list_price, to_uom)
            else:
                list_price = product.base_list_price
            product.lst_price = list_price

class SupplierInfo(models.Model):
    _inherit = 'product.supplierinfo'

    mfr_num = fields.Char(string='Manufacturer Number')
    mfr_name = fields.Char(string='Manufacturer Name')
