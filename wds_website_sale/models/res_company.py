# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    is_hidden_add_to_cart_public = fields.Boolean(
        string="Hide 'Add to Cart' buttons for Public Users",
        help="Enabling this option will hide the 'Add to Cart' buttons for Public Users on Website pages",
    )
