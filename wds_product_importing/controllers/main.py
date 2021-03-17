# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

from odoo import fields, http, SUPERUSER_ID, _
from odoo.http import request
from odoo.addons.website_sale.controllers.main import WebsiteSale
from odoo.osv import expression
_logger = logging.getLogger(__name__)

class WebsiteSale(WebsiteSale):

    def _get_search_domain(self, search, category, attrib_values, search_in_description=True):
        domains = [request.website.sale_product_domain()]
        if search:
            for srch in search.split(" "):
                subdomains = [
                    [('name', 'ilike', srch)],
                    [('product_variant_ids.default_code', 'ilike', srch)],
                    [('product_variant_ids.product_code', 'ilike', srch)],
                    [('product_variant_ids.mfr_num', 'ilike', srch)],
                    [('product_variant_ids.mfr_name', 'ilike', srch)],
                    [('product_variant_ids.vendor_name', 'ilike', srch)],
                ]
                if search_in_description:
                    subdomains.append([('description', 'ilike', srch)])
                    subdomains.append([('description_sale', 'ilike', srch)])
                domains.append(expression.OR(subdomains))

        if category:
            domains.append([('public_categ_ids', 'child_of', int(category))])

        if attrib_values:
            attrib = None
            ids = []
            for value in attrib_values:
                if not attrib:
                    attrib = value[0]
                    ids.append(value[1])
                elif value[0] == attrib:
                    ids.append(value[1])
                else:
                    domains.append(
                        [('attribute_line_ids.value_ids', 'in', ids)])
                    attrib = value[0]
                    ids = [value[1]]
            if attrib:
                domains.append([('attribute_line_ids.value_ids', 'in', ids)])

        return expression.AND(domains)
