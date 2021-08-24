# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields, api


class ProductTemplateAttributeValue(models.Model):
    _inherit = 'product.template.attribute.value'

    def _only_active(self):
        res = super(ProductTemplateAttributeValue, self)._only_active()
        # only single combination variants so mapped will always be len 1 array, use any() just in case
        # hides variant if product has to_remove or is archived
        for val in res:
            if any(val.ptav_product_variant_ids.mapped('to_remove')) or not all(val.ptav_product_variant_ids.mapped('active')):
                res -= val
        return res
