# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    def _is_hidden_add_to_cart_public(self):
        return self.env.company.is_hidden_add_to_cart_public or False
