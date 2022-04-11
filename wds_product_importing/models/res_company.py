# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields

class ResCompany(models.Model):
    _inherit = "res.company"

    def _domain_company(self):
        company = self.env.company
        return ['|', ('company_id', '=', False), ('company_id', '=', company)]

    import_folder = fields.Many2one('documents.folder', string="Importing Workspace", domain=_domain_company,
                                    default=lambda self: self.env.ref('wds_product_importing.documents_import_folder',
                                                                      raise_if_not_found=False))

    complete_import_folder = fields.Many2one('documents.folder', string="Imported Workspace", domain=_domain_company,
                                             default=lambda self: self.env.ref('wds_product_importing.documents_complete_import_folder',
                                                                               raise_if_not_found=False))

    stale_product_handling = fields.Selection(string="Stale Product Handling", selection=[('archive','Automatically archive'),('flag','Flag for removal'),('none','Don\'t do anything.')],
        default='archive',
        required=True,
        help='''How to handle existing products no longer in the imported documents:
        * Automatically archive: Archive all products and variants not existing in most recent import.
        * Flag for removal: Set the "To Remove" field to True for manual archival/deletion.
        * Don't do anything.: Self-explanatory.''')
