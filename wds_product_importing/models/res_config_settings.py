# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    import_folder = fields.Many2one('documents.folder', related='company_id.import_folder', readonly=False,
                                    string="product import workspace")
