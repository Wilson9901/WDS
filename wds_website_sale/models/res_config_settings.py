# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    is_hidden_add_to_cart_public = fields.Boolean(
        related="company_id.is_hidden_add_to_cart_public", readonly=False
    )
