# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields, api


class ProductTemplateAttributeValue(models.Model):
    _inherit = 'product.template.attribute.value'

    def _only_active_wds(self):
        res = super(ProductTemplateAttributeValue, self)._only_active()
        # only single combination variants so mapped will always be len 1 array, use any() just in case
        # hides variant if product has to_remove or is archived
        hidden_variants = self.env['product.template.attribute.value']
        for val in res:
            if not len(val.ptav_product_variant_ids):
                hidden_variants += val
        res -= hidden_variants
        return res
