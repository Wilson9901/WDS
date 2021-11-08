# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.


{
    "name": "WDS: Website Shop Access",
    "summary": """
    Enable/disable 'Add to Cart' for public website users
        """,
    "description": """
        Task ID: 2669527

        This module gives Odoo users the ability enable/disable whether
        or not public users can purchase products from the eCommerce store.

        When this setting is enabled through Website Settings, the 'Add to
        Cart' button will be hidden from all web pages.
        """,
    "author": "Odoo Inc",
    "website": "https://www.odoo.com/",
    "category": "Custom Development",
    "version": "1.0",
    "license": "OPL-1",
    "depends": ["website_sale_wishlist", "website_sale_comparison"],
    "data": [
        "views/res_config_settings_views.xml",
        "views/website_sale_templates.xml",
        "views/website_sale_wishlist_templates.xml",
        "views/website_sale_comparison_templates.xml",
    ],
    "application": False,
}
