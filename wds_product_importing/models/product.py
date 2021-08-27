# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields, api


class ProductProduct(models.Model):
    _inherit = 'product.product'

    _sql_constraints = [
        ('default_code_unique', 'UNIQUE(default_code)', 'You can not have two records with the same default code!'),
    ]

    size = fields.Char(string='Size')
    unit = fields.Char(string='Unit')
    unitqty = fields.Char(string='Unit Quantity')
    base_list_price = fields.Float(string='Variant Base Price')
    to_remove = fields.Boolean(string='To Remove', default=False)
    
    attachment_id = fields.Many2one(comodel_name='ir.attachment')

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

    def price_compute(self, price_type, uom=False, currency=False, company=None):
        res = super(ProductProduct, self).price_compute(price_type, uom, currency, company)
        products = self
        for product in products:
            res[product.id] = product.lst_price
        return res

class SupplierInfo(models.Model):
    _inherit = 'product.supplierinfo'

    mfr_num = fields.Char(string='Manufacturer Number')
    mfr_name = fields.Char(string='Manufacturer Name')
    to_remove = fields.Boolean(related='product_id.to_remove')
    catno = fields.Char(related='product_tmpl_id.product_code', string='Catalog Number')
