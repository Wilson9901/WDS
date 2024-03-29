# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import itertools
import logging
import math
import threading
from datetime import datetime, timedelta

import requests
from odoo import _, fields, models, api, tools
from psycopg2.extras import execute_values
from .sql_queries import _queries 
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
            elif vals['type'] in ['text','char','html']:
                try:
                    value = str(int(value))
                except Exception:
                    value = str(value)
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
    unspsc = fields.Char(string='UNSPSC')

    # image_1920 = fields.Binary(string='IMAGE')
    image_url = fields.Char(string="IMAGE")
    image_updated = fields.Boolean(string="Image Needs Downloading", default=False, readonly=True, index=True)
    image_failed = fields.Boolean(string="Image Import Failed", default=False, readonly=True, index=True)
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

    to_remove = fields.Boolean(string='To Remove', default=False)
    attachment_id = fields.Many2one(comodel_name='ir.attachment', index=True)

    '''
    import all products from documents in the designated product folder then move attachment to different folder
    '''

    def _cron_import_all_products(self):
        '''
            Importing a large number of records will often take longer than the timeout limit. If that
            happens, we just reschedule the action since the batches already imported will remain
            commited to the database.
        '''
        def schedule_next_import(thread):
            thread.timed_out = True
            _logger.info('Reschedule import')

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

        thread = threading.current_thread()
        thread.timed_out = False
        timer = threading.Timer(500.0, schedule_next_import, [thread])
        timer.start()
        self._import_images()
        timer.cancel()

    def _import_documents(self, documents, batch_size=1000):
        if not documents:
            return
        _logger.info('Importing documents')
        self = self.with_context(active_test=False, prefetch_fields=False, mail_notrack=True, tracking_disable=True, mail_activity_quick_update=False)
        company = self.company_id or self.env.company
        failed_imports = self.env['documents.document']
        for doc in documents.with_context(prefetch_fields=False):
            doc._prefetch_ids = doc._ids
            # Get first rows in dictionary form
            data_rows = doc.attachment_id._read_as_dict_list(0, 1)
            # Get table column header to field mapping
            field_mapping = self._get_fields_column_mapping(next(data_rows).keys())
            del data_rows
            if self.user_has_groups('base.group_no_one'):
                doc.attachment_id.batch = 0 # Useful for debugging. This lets you reuse the same document repeatedly.
            while True:
                try:
                    if threading.current_thread().timed_out:
                        return False
                except AttributeError:  # timed_out won't exist if launched from action menu and not cron
                    pass
                batch = doc.attachment_id.batch
                try:
                    batched_rows = doc.attachment_id._read_as_dict_list( batch_size*doc.attachment_id.batch, batch_size*(doc.attachment_id.batch + 1))
                    to_create, to_update = self.with_context(attachment_id=doc.attachment_id.id)._split_rows_into_new_and_existing_products(batched_rows, field_mapping)
                    if len(to_create)==0 and len(to_update) == 0:
                        break
                    # Update existing
                    updated_products = self._optimized_update(to_update)
                    # Create new
                    new_product_templates = self._optimized_create(to_create) 
                    # Post-processing
                    ## Write attachment_id to product variants that don't need updating so that they won't get archived later
                    updated_products['updated_products'].write({'attachment_id': doc.attachment_id.id})
                    updated_products['no_new_variants'].mapped('product_variant_ids').filtered(lambda p: p.active).write({'attachment_id': doc.attachment_id.id})
                    ## Enable dropshipping on products
                    new_product_templates.enable_dropshipping()
                    ## Flag products to update images
                    (new_product_templates + updated_products['to_update_images']).write({'image_updated': True})
                    ## Create / update variants
                    products_to_update_variants = new_product_templates + updated_products['to_update_variants']
                    # all_products = new_product_templates + updated_products['updated_products']
                    if (products_to_update_variants):
                        products_to_update_variants.with_context(attachment_id=doc.attachment_id.id)._update_product_variants()
                        products_to_update_variants._update_pricelists()
                        products_to_update_variants._set_list_price()
                    # Increase batch
                    _logger.info(f'Importing batch #{doc.attachment_id.batch} from {doc.attachment_name} done. {len(new_product_templates)} products created. {len(updated_products["to_update_variants"])} products updated.')
                    doc.attachment_id.batch += 1
                    self._cr.commit()
                except Exception as e:
                    _logger.error(f"There was an error somewhere in file {doc.attachment_name} between rows {batch_size * batch + 2} and {batch_size*(batch + 1) + 2}.\nError: {e}")
                    self._cr.rollback()
                    failed_imports += doc
                    break
            doc.invalidate_cache()

        if not failed_imports:
            _logger.info('Data import done! Handling stale products now.')
            self._handle_stale_products(documents)
            documents.folder_id = company.complete_import_folder
            documents._cr.commit()
            _logger.info('Import done!')
            try:
                self.env.ref('wds_product_importing.cron_import_images').nextcall = datetime.now() + timedelta(minutes=5)
            except Exception:
                pass
        else:
            _logger.error(f"The following document ids failed to import fully: {failed_imports.ids}")

        return True

    def _handle_stale_products(self, documents):
        company = self.company_id or self.env.company
        tables = ('product_template', 'product_product')
        for table in tables:
            self._cr.execute(f'''
                UPDATE {table}
                SET active = true, to_remove = false
                WHERE attachment_id IN %s
            ''', (tuple(documents.mapped('attachment_id').ids), ))

            self._cr.execute(f'''
                UPDATE {table}
                SET 
                    {"active = false," if company.stale_product_handling == 'archive' else ''} 
                    to_remove = true
                WHERE
                    attachment_id NOT IN %s OR attachment_id IS NULL
            ''', (tuple(documents.mapped('attachment_id').ids), ))

        self._cr.commit()

    def enable_dropshipping(self):
        dropship_route = self.env.ref('stock_dropshipping.route_drop_shipping')
        self.write({'route_ids': [(4,dropship_route.id,0)]})

    def _import_images(self, batch_size = 80):
        self = self.with_context(active_test=False, prefetch_fields=False, mail_notrack=True, tracking_disable=True, mail_activity_quick_update=False)
        if self:
            count = len(self)
            batch_size = count
        else:
            domain = [('image_updated','=',True),('image_failed','=',False)]
            count = self.search(domain,count=True)
        num_batches = math.ceil(count / batch_size)
        _logger.info(f"Started importing images. {count} images to import.")
        for _ in range(num_batches):
            try:
                if threading.current_thread().timed_out:
                    return False
            except AttributeError:  # timed_out won't exist if launched from action menu and not cron
                pass
            images_to_update = self or self.search(domain, limit=batch_size) # No need to set an offset since we are committing at the end of each iteration
            for product in images_to_update:
                product._import_single_image()
                # try:
                #     product.image_1920 = product._import_image_cached(product.image_url, product.id)
                #     product.image_updated = False
                #     product.image_failed = False
                # except Exception:
                #     _logger.warning(f'Error importing image on product {product.name}')
                #     product.image_1920 = self.env.company.logo
                #     product.image_failed = True
            images_to_update._cr.commit()
            _logger.info(f"Batch of {len(images_to_update)} images imported.")
        _logger.info("Image import done.")
        return True

    def _import_single_image(self):
        self.ensure_one()
        try:
            self.image_1920 = self._import_image_cached(self.image_url, self.id)
            self.image_updated = False
            self.image_failed = False
        except Exception:
            _logger.warning(f'Error importing image on product {self.name}')
            self.image_1920 = self.env.company.logo
            self.image_failed = True

    @api.model
    @tools.ormcache('url')
    def _import_image_cached(self, url, line_number = 0):
        return self.env['base_import.import']._import_image_by_url(url, requests.Session(), 'image_1920', line_number)

    def _update_product_variants(self):
        params = {
            'template_ids': tuple(self.ids),
            'size_attr_id': self.env.ref('wds_product_importing.size_attribute').id,
            'field_id': self.env['ir.model.fields'].search([('name','=','standard_price'),('model','=','product.product')], limit=1).id,
            'company_id': self.env.company.id,
            'attachment_id': self.env.context.get('attachment_id', None)
        }
        # CREATE ANY NEW ATTRIBUTES
        self._cr.execute(_queries['create_product_attribute_values'], params)
        # CREATE/UPDATE VARIANTS
        self._cr.execute(_queries['create_product_variants'], params)
        product_ids = self._cr.fetchall()
        product_ids = [product[0] for product in product_ids]
        params['new_product_ids'] = tuple(product_ids)
        # UPDATE COMBINATION_INDICES ON PRODUCT_PRODUCT
        self._cr.execute(_queries['write_product_product_combination_indices'], params)

        return True

    def _get_fields_column_mapping(self, headers):
        ''' Creates a dict mapping fields to csv/xlsx headers '''
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
        ''' Parse a list of rows and splits them into existing and new products '''
        to_update = {}
        to_create = []
        for row in rows:
            product = self.search([('product_code', '=', row.get(mapping['product_code']['name']))], limit=1)
            data = clean_data_row(row, mapping)
            if product:
                data.update(product._extra_import_update_vals())
                to_update[product.id] = data
            else:
                data.update(self._extra_import_create_vals())
                to_create.append(data)
        return to_create, to_update

    def _extra_import_create_vals(self):
        return {
            'categ_id': self.env.ref('product.product_category_all').id,
            'purchase_line_warn': 'no-message',
            'sale_line_warn': 'no-message',
            'tracking': 'none',
            'type': 'consu',
            'uom_id': self.env.ref('uom.product_uom_unit').id,
            'uom_po_id': self.env.ref('uom.product_uom_unit').id,
            'attachment_id': self.env.context.get('attachment_id', None),
            'active': True,
            'is_published': True,
            'sale_ok': True,
            'purchase_ok': True,
            'invoice_policy': self.env['ir.default'].get('product.template','invoice_policy') or 'order',
            'purchase_method': self.env['ir.default'].get('product.template','purchase_method') or 'receive',
        }

    def _extra_import_update_vals(self):
        return {
            'attachment_id': self.env.context.get('attachment_id', None),
            'active': True,
            'is_published': True,
        }

    def _optimized_update(self, vals_dict):
        ''' Update values for records via SQL, returning records that need further postprocessing '''
        Product = self.env['product.template']
        if not vals_dict:
            return {
                'to_update_variants': Product, 
                'to_update_images': Product, 
                'updated_products': Product,
                'no_new_variants': Product
            }
        # Step 0: Preprocessing
        fields = list(list(vals_dict.values())[0].keys())
        fields.append('id')
        values = [
            tuple(list(vals.values()) + [id])
            for id, vals in vals_dict.items()
        ]

        # Step 1: Read fields that we need to know if they change for additional postprocessing
        fields_to_check = fields.copy()
        fields_to_check.remove('attachment_id')
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
        image_index = fields_to_check.index('image_url')+1
        update_images = [
            i[1][0] for i in zip(init_values, final_values)
            if i[0][image_index] != i[1][image_index] and i[1][image_index]
        ]
        # size_indexes = range(1, 4)
        update_variants = [
            i[1][0] for i in zip(init_values, final_values)
            if i[0] != i[1]
        ]
        return {
            'to_update_variants': Product.browse(update_variants),
            'to_update_images': Product.browse(update_images),
            'updated_products': Product.browse(product_ids),
            'no_new_variants': Product.browse(product_ids) - Product.browse(update_variants)
        }

    def _optimized_create(self, vals_list):
        ''' Create product.template via SQL '''
        Product = self.env['product.template']
        if not vals_list:
            return Product
        fields = list(vals_list[0].keys())
        for idx, val in enumerate(vals_list):
            vals_list[idx] = [v for k, v in val.items()]
        query_create_templates = f"INSERT INTO product_template ( {', '.join(fields)} ) VALUES %s RETURNING id"
        # fetch was added in psycopg version 2.8. If it doesn't exist we expand the page size adn then manually fetch
        try:
            tmpl_ids = execute_values(
                self._cr, query_create_templates, vals_list, fetch=True)
        except Exception:
            execute_values(self._cr, query_create_templates,
                           vals_list, page_size=len(vals_list))
            tmpl_ids = self._cr.fetchall()
        ids = [v[0] for v in tmpl_ids]
        return Product.browse(ids)

    def _set_list_price(self):
        params = {'tmpl_ids': tuple(self.ids)}
        self._cr.execute(_queries['write_product_product_lst_price'], params)
        self._cr.execute(_queries['write_product_template_list_price'], params)
        
    def _update_pricelists(self):
        ''' Create vendor pricelists for each of the products imported. '''
        params = {
            'field_id': self.env['ir.model.fields'].search([('name','=','standard_price'),('model','=','product.product')], limit=1).id,
            'tmpl_ids': tuple(self.ids),
            'currency_id': self.env.ref('base.main_company').currency_id.id,
            'company_id': self.env.company.id
        }
        # GENERATE ANY NEW PARTNERS
        self._cr.execute(_queries['create_res_partner'], params)
        # DELETE ALL CURRENT PRICELISTS
        self._cr.execute(_queries['unlink_product_supplierinfo'], params)
        # CREATE NEW PRICELISTS
        # 1) First, handle product templates with only a single variant
        self._cr.execute(_queries['create_product_supplierinfo_single_variant'], params)
        # 2) Handle products with multiple variants
        self._cr.execute(_queries['create_product_supplierinfo_multiple_variant'], params)
