# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import math
import threading
from datetime import datetime, timedelta

import requests
from odoo import _, fields, models
from psycopg2.extras import execute_values

_logger = logging.getLogger(__name__)


def clean_data_row(row_dict, field_mapping):
    ''' Remove unused columns and replaces column names with field names. Set empty values to None. 
    
    We don't omit blank values to keep a consistent data structure for the SQL injection. Default
    values of 0 and '' are used instead of None so that the data type for the column can be inferred.
    '''
    cleaned_dict = {}
    for field, vals in field_mapping.items():
        value = row_dict[vals['name']]
        if value:
            if vals['type'] in ['float', 'monetary']:
                value = float(value)
            elif vals['type'] in ['int']:
                value = int(value)
        elif vals['type'] in ['float', 'monetary', 'int']:
            value = 0
        cleaned_dict[field] = value
    return cleaned_dict


class ProductTemplateAttributeLine(models.Model):
    _inherit = 'product.template.attribute.line'

    _sql_constraints = [
        ('tmpl_attr_uniq', 'unique (attribute_id,product_tmpl_id)',
         'You cannot use the same attribute twice on a product.')
    ]


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # product_variant_id = fields.Many2one(comodel_name='product.product', store=True)

    name = fields.Char(string='SHORT DESCRIPTION',
                       index=True,
                       required=True,
                       translate=True)
    description = fields.Text(string='LONG DESCRIPTION', translate=True)

    categ_one = fields.Char(string='CATEGORY1')
    categ_two = fields.Char(string='CATEGORY2')
    unspsc = fields.Char(string='UNSPSC Code')

    # image_1920 = fields.Binary(string='IMAGE')
    image_url = fields.Char(string="IMAGE")
    image_updated = fields.Boolean(string="Image Needs Downloading", default=False, readonly=True)
    product_url = fields.Char(string='PRODUCT URL')
    weblink = fields.Char(string='ADDITIONAL WEBLINK')
    weblink_title = fields.Char(string='ADDITIONAL WEBLINK_TITLE')

    upc_code = fields.Char(string='UPC')
    upn_code = fields.Char(string='UPN')

    # purchase tab
    product_code = fields.Char(string='CATNO', index=True)
    mfr_num = fields.Char(string='MFRNO')
    mfr_name = fields.Char(string='MFRNAME')
    vendor_name = fields.Char(string='Vendor Name')

    # product variants
    size_1 = fields.Char(string='SIZE_1')
    unit_1 = fields.Char(string='UNIT_1')
    unitqty_1 = fields.Char(string='UNITQTY_1')
    cost_1 = fields.Float(string='COST1')
    list_1 = fields.Float(string='LIST1')

    size_2 = fields.Char(string='SIZE_2')
    unit_2 = fields.Char(string='UNIT_2')
    unitqty_2 = fields.Char(string='UNITQTY_2')
    cost_2 = fields.Float(string='COST2')
    list_2 = fields.Float(string='LIST2')

    size_3 = fields.Char(string='SIZE_3')
    unit_3 = fields.Char(string='UNIT_3')
    unitqty_3 = fields.Char(string='UNITQTY_3')
    cost_3 = fields.Float(string='COST3')
    list_3 = fields.Float(string='LIST3')

    # size = fields.Char(related='product_variant_id.size')
    # unit = fields.Char(related='product_variant_id.unit')
    # unitqty = fields.Char(related='product_variant_id.unitqty')

    to_remove = fields.Boolean(string='To Remove', default=False)
    attachment_id = fields.Many2one(comodel_name='ir.attachment', index=True)
    '''
    import all products from documents in the designated product folder then move attachment to different folder
    '''

    def _cron_import_all_products(self):
        def schedule_next_import(thread):
            thread.timed_out = True
            _logger.info('Reschedule import')
            self.env.ref('wds_product_importing.cron_import_product_documents').nextcall = datetime.now() + timedelta(minutes=1)

        thread = threading.current_thread()
        thread.timed_out = False
        timer = threading.Timer(500.0, schedule_next_import, [thread])
        timer.start()

        company = self.company_id or self.env.company
        docs = company.import_folder.document_ids
        self._import_documents(documents=docs)
        timer.cancel()

    def _cron_import_images(self):
        def schedule_next_import(thread):
            thread.timed_out = True
            _logger.info('Reschedule image download')
            self.env.ref('wds_product_importing.cron_import_images').nextcall = datetime.now() + timedelta(minutes=1)

        thread = threading.current_thread()
        thread.timed_out = False
        timer = threading.Timer(500.0, schedule_next_import, [thread])
        timer.start()
        self._import_images()
        timer.cancel()

    def _import_documents(self, documents, batch_size=80):
        _logger.info('Importing documents')
        self = self.with_context(active_test=False, prefetch_fields=False, mail_notrack=True, tracking_disable=True, mail_activity_quick_update=False)
        product = self.env['product.product'].with_context(active_test=False, prefetch_fields=False, mail_notrack=True, tracking_disable=True, mail_activity_quick_update=False)
        company = self.company_id or self.env.company
        for doc in documents:
            # Get table rows in dictionary form
            data_rows = doc.attachment_id._read_as_dict_list()
            if not data_rows:
                continue
            num_rows = len(data_rows)
            # Get table column header to field mapping
            field_mapping = self._get_fields_column_mapping(
                data_rows[0].keys())
            # doc.attachment_id.batch = 0 # For debugging
            while batch_size * doc.attachment_id.batch < num_rows:
                try:
                    if threading.current_thread().timed_out:
                        return False
                except AttributeError:  # timed_out won't exist if launched from action menu and not cron
                    pass
                batched_rows = data_rows[batch_size*doc.attachment_id.batch:batch_size*(doc.attachment_id.batch + 1)]
                to_create, to_update = self.with_context(attachment_id=doc.attachment_id.id)._split_rows_into_new_and_existing_products(batched_rows, field_mapping)
                # Update existing
                updated_products = self._optimized_update(to_update)
                # Create new
                new_product_templates = self._optimized_create(to_create)
                # Post-processing
                ## Flag products to update images
                (new_product_templates + updated_products['to_update_images']).write({'image_updated': True})
                ## Create / update variants
                # products_to_update_variants = new_product_templates + updated_products['to_update_variants']
                products_to_update_variants = new_product_templates + updated_products['updated_products']
                if (products_to_update_variants):
                    products_to_update_variants._update_product_variants()
                    products_to_update_variants._update_pricelists()
                    products_to_update_variants._set_list_price()
                # Increase batch
                _logger.info(f'Importing batch #{doc.attachment_id.batch} done.')
                doc.attachment_id.batch += 1
                self._cr.commit()
            doc.folder_id = company.complete_import_folder.id

        _logger.info('Import done!')

        self.search([]).write({'to_remove': False})
        self.search([
            ('attachment_id', 'not in', documents.mapped('attachment_id').ids)
        ]).write({'to_remove': True})
        product.search([]).write({'to_remove': False})
        product.search([
            ('attachment_id', 'not in', documents.mapped('attachment_id').ids)
        ]).write({'to_remove': True})

        self.env.ref('wds_product_importing.cron_import_images').nextcall = datetime.now() + timedelta(minutes=5)
        return True

    def _set_list_price(self):
        params = {'tmpl_ids': tuple(self.ids)}
        update_query = '''
            UPDATE
                product_template
            SET
                list_price = list_prices.lst_price
            FROM
                (
                    SELECT
                        product_template.id as product_tmpl_id,
                        MIN(product_product.lst_price) as lst_price
                    FROM
                        product_template
                        JOIN product_product ON product_product.product_tmpl_id = product_template.id
                    WHERE
                        product_template.id IN %(tmpl_ids)s AND
                        product_product.active = TRUE
                    GROUP BY
                        product_template.id
                ) AS list_prices
            WHERE
                product_template.id = list_prices.product_tmpl_id
        '''
        self._cr.execute(update_query, params)

    def _import_images(self, batch_size = 80):
        base_import = self.env['base_import.import']
        if self:
            images_to_update = self.ids
        else:
            images_to_update = self.search([('image_updated','=',True)]).ids
        num_batches = math.ceil(len(images_to_update)/batch_size)
        _logger.info(f"Started importing images. {len(images_to_update)} images to import.")
        for batch in range(num_batches):
            try:
                if threading.current_thread().timed_out:
                    return False
            except AttributeError:  # timed_out won't exist if launched from action menu and not cron
                pass
            for product in self.browse(images_to_update[batch_size*batch:batch_size*(batch+1)]):
                try:
                    product.image_1920 = base_import._import_image_by_url(
                        product.image_url, requests.Session(), 'image_1920',
                        product.id)
                    product.image_updated = False
                except ValueError as e:
                    _logger.warning('Image timeout on product {}'.format(product.name))
                except:
                    _logger.warning('Unexpected error importing image on product {}'.format(product.name))
            self._cr.commit()
            _logger.info(f"Batch of {batch_size} images imported.")
        _logger.info(f"Image import done.")
        return True

    def _get_cte_tables(self):
        return {
            "attribute_values": self._get_cte_attribute_values(),
            "template_sizes": self._get_cte_template_sizes(),
            "line_values": self._get_cte_line_values(),
            "inserted_template_attr_lines": self._get_cte_inserted_template_attr_lines(),
            "inserted_attribute_value_template_attribute_line_rel": self._get_cte_inserted_attribute_value_template_attribute_line_rel(),
            "inserted_product_template_attribute_value": self._get_cte_inserted_product_template_attribute_value(),
            "inserted_products": self._get_cte_inserted_products(),
            "insert_product_variant_combo": self._get_cte_insert_product_variant_combo(),
            "inserted_standard_price": self._get_cte_inserted_standard_price(),
            "inserted_attribute_values": self._get_cte_inserted_attribute_values()
        }

    def _get_cte_attribute_values(self):
        return """
            SELECT
                product_attribute_value.id,
                product_attribute_value."name",
                product_attribute.id as attribute_id,
                product_attribute.name as attribute_name
            FROM
                product_attribute_value
                JOIN product_attribute ON product_attribute_value.attribute_id = product_attribute.id
            WHERE product_attribute.id = %(size_attr_id)s
        """

    def _get_cte_template_sizes(self):
        return ' UNION '.join([f"""
            SELECT
                id,
                size_{idx} as size,
                unit_{idx} as unit,
                unitqty_{idx} as unitqty,
                cost_{idx} as cost,
                list_{idx} as list
            from
                product_template
            WHERE
                size_{idx} IS NOT NULL
                AND size_{idx} <> ''
                AND id IN %(template_ids)s
        """ for idx in range(1, 4)
        ])

    def _get_cte_line_values(self):
        return f"""
            SELECT
                product_template.id as tmpl_id,
                COALESCE(product_attribute_value.id,insert_attributes.id) as attr_value_id,
                size,
                unit,
                unitqty,
                cost,
                list,
                product_code,
                CONCAT(product_code, unit, unitqty) as default_code,
                product_template.attachment_id as attachment_id
            FROM
                template_sizes
                LEFT JOIN product_template ON template_sizes.id = product_template.id
                LEFT JOIN product_attribute_value ON template_sizes.size = product_attribute_value.name
                LEFT JOIN insert_attributes ON template_sizes.size = insert_attributes.name
        """

    def _get_cte_inserted_template_attr_lines(self):
        return """
            INSERT INTO
                product_template_attribute_line (active, attribute_id, product_tmpl_id)
            SELECT
                DISTINCT TRUE,
                attribute_values.attribute_id,
                product_template.id
            FROM
                (
                    SELECT
                        product_attribute_value.id,
                        product_attribute_value."name",
                        product_attribute.id as attribute_id,
                        product_attribute.name as attribute_name
                    FROM
                        (
                            product_attribute_value
                            JOIN product_attribute ON product_attribute_value.attribute_id = product_attribute.id
                        )
                    WHERE
                        product_attribute.id = %(size_attr_id)s
                ) AS attribute_values
                INNER JOIN line_values ON line_values.attr_value_id = attribute_values.id
                JOIN product_template ON line_values.tmpl_id = product_template.id 
            ON CONFLICT ON CONSTRAINT product_template_attribute_line_tmpl_attr_uniq DO
            UPDATE
            SET
                active = TRUE RETURNING id,
                attribute_id,
                product_tmpl_id
        """

    def _get_cte_inserted_standard_price(self):
        return """
            INSERT INTO
                ir_property (company_id, fields_id, "name", res_id, "type", value_float)
            SELECT
                %(company_id)s,
                %(field_id)s,
                'standard_price',
                CONCAT('product.product,', inserted_products.id),
                'float',
                line_values.cost
            FROM
                inserted_products
                JOIN line_values ON inserted_products.default_code = line_values.default_code
                JOIN inserted_product_template_attribute_value ON product_attribute_value_id = attr_value_id
                AND inserted_product_template_attribute_value.product_tmpl_id = inserted_products.product_tmpl_id
            ON CONFLICT (fields_id, COALESCE(company_id, 0), COALESCE(res_id, ''::character varying)) DO UPDATE SET
                value_float = EXCLUDED.value_float
            RETURNING 
                id, company_id, fields_id, "name", res_id, value_float
        """

    def _get_cte_insert_product_variant_combo(self):
        return """
            INSERT INTO
                product_variant_combination (
                    product_product_id,
                    product_template_attribute_value_id
                )
            SELECT
                inserted_products.id,
                inserted_product_template_attribute_value.id
            FROM
                inserted_products
                JOIN line_values ON inserted_products.default_code = line_values.default_code
                JOIN inserted_product_template_attribute_value ON product_attribute_value_id = attr_value_id
                AND inserted_product_template_attribute_value.product_tmpl_id = inserted_products.product_tmpl_id
        """

    def _get_cte_inserted_products(self):
        return """
            INSERT INTO
                product_product (product_tmpl_id, to_remove, base_list_price, unit, unitqty, size, attachment_id, active, default_code)
            SELECT DISTINCT ON(default_code) 
                tmpl_id, FALSE, list, unit, unitqty, size, attachment_id, TRUE, line_values.default_code
            FROM
                line_values 
            ON CONFLICT ON CONSTRAINT product_product_default_code_unique 
            DO UPDATE SET
                to_remove = FALSE,
                base_list_price = EXCLUDED.base_list_price,
                size = EXCLUDED.size,
                attachment_id = EXCLUDED.attachment_id,
                active = TRUE 
            RETURNING id,
                product_tmpl_id,
                default_code
        """

    def _get_cte_inserted_product_template_attribute_value(self):
        return """
            INSERT INTO
                product_template_attribute_value (
                    attribute_line_id,
                    price_extra,
                    product_attribute_value_id,
                    ptav_active,
                    product_tmpl_id,
                    attribute_id
                )
            SELECT DISTINCT 
                inserted_template_attr_lines.id,
                0,
                attr_value_id,
                TRUE,
                inserted_template_attr_lines.product_tmpl_id,
                %(size_attr_id)s
            FROM
                inserted_template_attr_lines
                JOIN line_values ON inserted_template_attr_lines.product_tmpl_id = line_values.tmpl_id 
            ON CONFLICT DO NOTHING 
            RETURNING 
                id,
                attribute_line_id,
                product_attribute_value_id,
                product_tmpl_id
        """

    def _get_cte_inserted_attribute_value_template_attribute_line_rel(self):
        return """
            INSERT INTO
                product_attribute_value_product_template_attribute_line_rel (
                    product_template_attribute_line_id,
                    product_attribute_value_id
                )
            SELECT
                id,
                attr_value_id
            FROM
                inserted_template_attr_lines
                JOIN line_values ON inserted_template_attr_lines.product_tmpl_id = line_values.tmpl_id 
            ON CONFLICT DO NOTHING
        """

    def _get_cte_inserted_attribute_values(self):
        return f'''
            INSERT INTO product_attribute_value (name, attribute_id) 
            SELECT DISTINCT size, %(size_attr_id)s
            FROM template_sizes
            ON CONFLICT DO NOTHING
            RETURNING
                id, name
        '''

    def _update_product_variants(self):
        params = {
            'template_ids': tuple(self.ids),
            'size_attr_id': self.env.ref('wds_product_importing.size_attribute').id,
            'field_id': self.env['ir.model.fields'].search([('name','=','standard_price'),('model','=','product.product')], limit=1).id,
            'company_id': self.env.company.id
        }
        cte_tables = self._get_cte_tables()

        self._cr.execute(f'''
            WITH template_sizes AS ({cte_tables['template_sizes']})
            INSERT INTO product_attribute_value (name, attribute_id) 
            SELECT DISTINCT size, %(size_attr_id)s
            FROM template_sizes
            ON CONFLICT DO NOTHING''', params)

        # CREATE/UPDATE VARIANTS
        query = f"""
            WITH
                 template_sizes AS ({cte_tables['template_sizes']}),
                 insert_attributes AS ({cte_tables['inserted_attribute_values']}),
                 line_values AS ({cte_tables['line_values']}),
                 inserted_template_attr_lines AS ({cte_tables['inserted_template_attr_lines']}),
                 inserted_attribute_value_template_attribute_line_rel AS ({cte_tables['inserted_attribute_value_template_attribute_line_rel']}),
                 inserted_product_template_attribute_value AS ({cte_tables['inserted_product_template_attribute_value']}),
                 inserted_products AS ({cte_tables['inserted_products']}),
                 insert_product_variant_combo AS ({cte_tables['insert_product_variant_combo']}),
                 inserted_standard_price AS ({cte_tables['inserted_standard_price']})
            SELECT
                id
            FROM
                inserted_products
        """
        self._cr.execute(query, params)
        product_ids = self._cr.fetchall()
        product_ids = [product[0] for product in product_ids]
        params['new_product_ids'] = tuple(product_ids)
        # UPDATE COMBINATION_INDICES ON PRODUCT_PRODUCT
        query = '''
            UPDATE product_product
            SET combination_indices = combination_to_write.combination_indices
            FROM 
                (
                    SELECT
                        product_product.id as id,
                        STRING_AGG(
                            product_variant_combination.product_template_attribute_value_id :: VARCHAR,
                            ','
                        ) AS combination_indices
                    FROM
                        product_product
                        JOIN product_variant_combination ON product_product.id = product_variant_combination.product_product_id
                    WHERE
                        id IN %(new_product_ids)s
                    GROUP BY
                        product_product.id
                ) AS combination_to_write
            WHERE product_product.id = combination_to_write.id
        '''
        self._cr.execute(query, params)

        return True

    def _get_fields_column_mapping(self, headers):
        fields = self.fields_get()
        field_strings = {v['string']: f for f, v in fields.items()}
        field_strings_lower = {v['string'].lower(): f for f, v in fields.items()}
        mapping = {}
        for header in headers:
            mapped_field = field_strings.get(header.strip(),False) or \
                            field_strings_lower.get(header.lower().strip(),False) or \
                            fields.get(header.lower().strip(),{}).get('name',False) or \
                            False
            if mapped_field:
                mapping[mapped_field] = {
                    'name': header,
                    'type': fields[mapped_field]['type']
                }
        return mapping

    def _split_rows_into_new_and_existing_products(self, rows, mapping):
        ''' Parse a list of rows and splits them into existing and new products'''
        to_update = {}
        to_create = []
        for row in rows:
            product = self.search([('product_code', '=', row.get(mapping['product_code']['name']))], limit=1)
            data = clean_data_row(row, mapping)
            if product:
                to_update[product.id] = data
            else:
                data.update(self._extra_import_create_vals())
                to_create.append(data)
        return to_create, to_update

    def _extra_import_create_vals(self):
        return {
            'categ_id': self.env.ref('product.product_category_all').id,
            # 'product_variant_ids': [[6, False, []]],
            'purchase_line_warn': 'no-message',
            'sale_line_warn': 'no-message',
            'tracking': 'none',
            'type': 'consu',
            'uom_id': self.env.ref('uom.product_uom_unit').id,
            'uom_po_id': self.env.ref('uom.product_uom_unit').id,
            'attachment_id': self.env.context.get('attachment_id', None),
            'active': True,
            'is_published': True
        }

    def _optimized_update(self, vals_dict):
        Product = self.env['product.template']
        if not vals_dict:
            return {'to_update_variants': Product, 'to_update_images': Product, 'updated_products': Product}
        # Step 0: Preprocessing
        fields = list(list(vals_dict.values())[0].keys())
        fields.append('id')
        values = [
            tuple(list(vals.values()) + [id])
            for id, vals in vals_dict.items()
        ]

        # Step 1: Read fields that we need to know if they change
        fields_to_check = ['size_1', 'size_2', 'size_3', 'image_url']
        product_ids = tuple(vals_dict.keys())
        init_search_query = f"SELECT {', '.join(['id']+fields_to_check)} FROM product_template WHERE id IN %s ORDER BY id"
        self._cr.execute(init_search_query, (product_ids, ))
        init_values = self._cr.fetchall()

        # Step 2: Update
        set_params = ', '.join([f'{f} = payload.{f}' for f in fields])
        bulk_update_query = f'''
            UPDATE product_template
            SET {set_params}
            FROM (VALUES %s) AS payload ({', '.join(fields)}) 
            WHERE product_template.id = payload.id
        '''
        execute_values(self._cr, bulk_update_query, values)

        # Step 3: Read those same fields
        self._cr.execute(init_search_query, (product_ids, ))
        final_values = self._cr.fetchall()

        # Step 4: For all fields we care about that changed, determine which ones need additional computation
        size_indexes = range(1, 4)
        update_images = [
            i[1][0] for i in zip(init_values, final_values)
            if i[0][4] != i[1][4] and i[1][4]
        ]
        update_sizes = [
            i[1][0] for i in zip(init_values, final_values)
            if any(i[0][size] != i[1][size] and i[1][size]
                   for size in size_indexes)
        ]
        return {
            'to_update_variants': Product.browse(update_sizes),
            'to_update_images': Product.browse(update_images),
            'updated_products': Product.browse(product_ids)
        }

    def _optimized_create(self, vals_list):
        Product = self.env['product.template']
        if not vals_list:
            return Product
        fields = list(vals_list[0].keys())
        for idx, val in enumerate(vals_list):
            vals_list[idx] = [v for k, v in val.items()]
        query_create_templates = f"INSERT INTO product_template ( {', '.join(fields)} ) VALUES %s RETURNING id"
        execute_values(self._cr, query_create_templates, vals_list)
        tmpl_ids = self._cr.fetchall()
        ids = [v[0] for v in tmpl_ids]
        return Product.browse(ids)

    def _update_pricelists(self):
        params = {
            'field_id': self.env['ir.model.fields'].search([('name','=','standard_price'),('model','=','product.product')], limit=1).id,
            'tmpl_ids': tuple(self.ids),
            'currency_id': self.env.ref('base.main_company').currency_id.id,
            'company_id': self.env.company.id
        }
        # GENERATE ANY NEW PARTNERS
        create_partner_query = '''
            INSERT INTO res_partner
                (name, type, display_name, active)
            SELECT
                vendor_name, 'contact', vendor_name, TRUE
            FROM
                (
                    SELECT DISTINCT 
                        vendor_name,
                        res_partner.id as partner_id
                    FROM
                        product_template
                        LEFT JOIN res_partner ON res_partner.name = product_template.vendor_name
                    WHERE
                        product_template.id IN %(tmpl_ids)s
                ) as vendors
            WHERE
                vendor_name <> '' AND partner_id IS NULL
        '''
        self._cr.execute(create_partner_query, params)

        # DELETE ALL CURRENT PRICELISTS
        delete_supplierinfo_query = '''
            DELETE FROM product_supplierinfo
            WHERE 
                product_tmpl_id IN %(tmpl_ids)s 
                OR product_id IN (SELECT id FROM product_product WHERE product_tmpl_id IN %(tmpl_ids)s)
        '''
        self._cr.execute(delete_supplierinfo_query, params)

        # CREATE NEW PRICELISTS
        # 1) First, handle product templates with only a single variant
        insert_supplierinfo_query = '''
            INSERT INTO product_supplierinfo
                (sequence, name, product_tmpl_id, product_name, product_code, currency_id, mfr_name, mfr_num, date_start, date_end, company_id, min_qty, price, delay)
            SELECT
                1 as sequence,
                res_partner.id as name, 
                product_template.id as product_tmpl_id,
                NULL as product_name,
                product_template.default_code as product_code,
                %(currency_id)s as currency_id,
                product_template.mfr_name as mfr_name,
                product_template.mfr_num as mfr_num,
                NULL as date_start,
                NULL as date_end,
                %(company_id)s as company_id,
                0 as min_qty,
                product_template.cost_1 as price,
                1 as delay
            FROM
                (
                    SELECT
                        product_product.product_tmpl_id,
                        COUNT(product_product.product_tmpl_id) as num_variants
                    FROM
                        product_template 
                        JOIN res_partner ON product_template.vendor_name = res_partner.name
                        JOIN product_product ON product_template.id = product_product.product_tmpl_id
                    WHERE product_template.id IN %(tmpl_ids)s
                    GROUP BY product_product.product_tmpl_id
                ) AS product_variant_counts
                JOIN product_template ON product_tmpl_id = product_template.id
                JOIN res_partner ON product_template.vendor_name = res_partner.name
            WHERE num_variants = 1
        '''
        self._cr.execute(insert_supplierinfo_query, params)
        # 2) Handle products with multiple variants
        insert_supplierinfo_query = '''
            INSERT INTO product_supplierinfo
                (sequence, name, product_id, product_name, product_code, currency_id, mfr_name, mfr_num, date_start, date_end, company_id, min_qty, price, delay)
            SELECT
                1 as sequence,
                res_partner.id as name, 
                product_product.id as product_id,
                NULL as product_name,
                product_template.default_code as product_code,
                %(currency_id)s as currency_id,
                product_template.mfr_name as mfr_name,
                product_template.mfr_num as mfr_num,
                NULL as date_start,
                NULL as date_end,
                %(company_id)s as company_id,
                0 as min_qty,
                ir_property.value_float as price,
                1 as delay
            FROM
                (
                    SELECT
                        product_product.product_tmpl_id,
                        COUNT(product_product.product_tmpl_id) as num_variants
                    FROM
                        product_template JOIN res_partner ON product_template.vendor_name = res_partner.name
                        JOIN product_product ON product_template.id = product_product.product_tmpl_id
                    WHERE product_template.id IN %(tmpl_ids)s
                    GROUP BY
                        product_product.product_tmpl_id
                ) AS product_variant_counts
                JOIN product_product ON product_variant_counts.product_tmpl_id = product_product.product_tmpl_id
                LEFT JOIN product_template ON product_product.product_tmpl_id = product_template.id
                JOIN res_partner ON product_template.vendor_name = res_partner.name
                JOIN ir_property ON res_id = CONCAT('product.product,',product_product.id)
            WHERE num_variants > 1 AND ir_property.fields_id = %(field_id)s
        '''
        self._cr.execute(insert_supplierinfo_query, params)
