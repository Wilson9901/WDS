# -*- coding: utf-8 -*-
{
    'name': "WDS Product Importing",

    'summary': """module to create products from vendor xls""",

    'description': """
        [2420357]
        create product variants from importing product templates,
        list products automatically in website
        """,

    'author': 'Odoo',
    'website': 'https://www.odoo.com/',

    'category': 'Custom Development',
    'version': '1.0',
    'license': 'OEEL-1',

    # any module necessary for this one to work correctly
    'depends': ['base_import',
                'documents',
                'product',
                'purchase',
                'stock',
                'website_sale',
                ],

    # always loaded
    'data': [
        'data/actions.xml',
        'data/data.xml',
        'views/documents_views.xml',
        'views/product_template_views.xml',
        'views/product_product_views.xml',
        'views/templates.xml',
    ],
    # only loaded in demonstration mode
    'demo': [],
    'application': False,
    'installable': True,
}
