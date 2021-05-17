# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields

class ResCompany(models.Model):
    _inherit = "res.company"

    def _domain_company(self):
        company = self.env.company
        return ['|', ('company_id', '=', False), ('company_id', '=', company)]

    import_folder = fields.Many2one('documents.folder', string="Imported Workspace", domain=_domain_company,
                                    default=lambda self: self.env.ref('wds_product_importing.documents_imported_folder',
                                                                      raise_if_not_found=False))
