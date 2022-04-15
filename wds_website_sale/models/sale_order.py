# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _is_hidden_add_to_cart_public(self):
        return self.env.company.is_hidden_add_to_cart_public or False
