# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    import_folder = fields.Many2one('documents.folder', related='company_id.import_folder', readonly=False,
                                    string="product importing workspace")

    complete_import_folder = fields.Many2one('documents.folder', related='company_id.complete_import_folder', readonly=False,
                                             string="product imported workspace")

    stale_product_handling = fields.Selection(related='company_id.stale_product_handling', readonly=False)