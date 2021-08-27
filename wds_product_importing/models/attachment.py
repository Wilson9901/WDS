# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields, api


class IrAttachment(models.Model):
    _inherit = 'ir.attachment'

    batch = fields.Integer(default=0)
