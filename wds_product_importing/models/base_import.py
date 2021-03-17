# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class Import(models.TransientModel):
    _inherit = 'base_import.import'

    def do(self, fields, columns, options, dryrun=False):
        """ Actual execution of the import
        :param fields: import mapping: maps each column to a field,
                    ``False`` for the columns to ignore
        :type fields: list(str|bool)
        :param columns: columns label
        :type columns: list(str|bool)
        :param dict options:
        :param bool dryrun: performs all import operations (and
                            validations) but rollbacks writes, allows
                            getting as much errors as possible without
                            the risk of clobbering the database.
        :returns: A list of errors. If the list is empty the import
                executed fully and correctly. If the list is
                non-empty it contains dicts with 3 keys ``type`` the
                type of error (``error|warning``); ``message`` the
                error message associated with the error (a string)
                and ``record`` the data which failed to import (or
                ``false`` if that data isn't available or provided)
        :rtype: dict(ids: list(int), messages: list({type, message, record}))
        """
        self.ensure_one()
        self._cr.execute('SAVEPOINT import')

        try:
            data, import_fields = self._convert_import_data(fields, options)
            # Parse date and float field
            data = self._parse_import_data(data, import_fields, options)
        except ValueError as error:
            return {
                'messages': [{
                    'type': 'error',
                    'message': str(error),
                    'record': False,
                }]
            }

        _logger.info('importing %d rows...', len(data))

        name_create_enabled_fields = options.pop('name_create_enabled_fields', {})
        import_limit = options.pop('limit', None)
        model = self.env[self.res_model].with_context(import_file=True, name_create_enabled_fields=name_create_enabled_fields, _import_limit=import_limit)
        import_result = model.load(import_fields, data)
        _logger.info('done')

        # If transaction aborted, RELEASE SAVEPOINT is going to raise
        # an InternalError (ROLLBACK should work, maybe). Ignore that.
        # TODO: to handle multiple errors, create savepoint around
        #       write and release it in case of write error (after
        #       adding error to errors array) => can keep on trying to
        #       import stuff, and rollback at the end if there is any
        #       error in the results.
        try:
            if dryrun:
                self._cr.execute('ROLLBACK TO SAVEPOINT import')
                # cancel all changes done to the registry/ormcache
                self.pool.clear_caches()
                self.pool.reset_changes()
            else:
                self._cr.execute('RELEASE SAVEPOINT import')
        except psycopg2.InternalError:
            pass

        # Insert/Update mapping columns when import complete successfully
        if import_result['ids'] and options.get('headers'):
            BaseImportMapping = self.env['base_import.mapping']
            for index, column_name in enumerate(columns):
                if column_name:
                    # Update to latest selected field
                    mapping_domain = [('res_model', '=', self.res_model), ('column_name', '=', column_name)]
                    column_mapping = BaseImportMapping.search(mapping_domain, limit=1)
                    if column_mapping:
                        if column_mapping.field_name != fields[index]:
                            column_mapping.field_name = fields[index]
                    else:
                        BaseImportMapping.create({
                            'res_model': self.res_model,
                            'column_name': column_name,
                            'field_name': fields[index]
                        })
        if 'name' in import_fields:
            index_of_name = import_fields.index('name')
            skipped = options.get('skip', 0)
            # pad front as data doesn't contain anythig for skipped lines
            r = import_result['name'] = [''] * skipped
            # only add names for the window being imported
            r.extend(x[index_of_name] for x in data[:import_limit])
            # pad back (though that's probably not useful)
            r.extend([''] * (len(data) - (import_limit or 0)))
        else:
            import_result['name'] = []

        skip = options.get('skip', 0)
        # convert load's internal nextrow to the imported file's
        if import_result['nextrow']: # don't update if nextrow = 0 (= no nextrow)
            import_result['nextrow'] += skip

        # create product variants and vendor lists for products
        if import_result['ids'] and self.res_model == 'product.template':
            products = self.env['product.template'].search([('id', 'in', import_result['ids'])])
            size_attr = self.env['product.attribute'].search([('name', '=', 'Size')], limit=1)
            # create variants based on size_n
            for product in products:
                size_attr_vals = []
                for idx in range(1, 4):
                    if product['size_' + str(idx)]:
                        # need to search before writing
                        variant_value = size_attr.value_ids.search([('name', '=', product['size_' + str(idx)])])
                        if not variant_value:
                            size_attr.write({
                                'value_ids': [[0, 0, {'name': product['size_' + str(idx)]}]]
                            })
                        size_attr_vals.append(product['size_' + str(idx)])
                # create attribute lines for values of variants
                if size_attr_vals:
                    size_attr_ids = size_attr.value_ids.search([('name', 'in', size_attr_vals)])
                    product.write({
                        'attribute_line_ids': [[0, False, {'attribute_id': size_attr.id, 'value_ids': [[6, False, size_attr_ids.mapped('id')]]}]]
                    })
                    for variant in product.product_variant_ids:
                        for idx in range(1, 4):
                            # variant should only have one tag, but in case multiple, using mapped
                            if product['size_' + str(idx)] and product['size_' + str(idx)] in variant.product_template_attribute_value_ids.mapped('name'):
                                variant.write({
                                    'base_list_price': product['list_' + str(idx)],
                                    'standard_price': product['cost_' + str(idx)],
                                    'unit': product['unit_' + str(idx)],
                                    'unitqty': product['unitqty_' + str(idx)],
                                    'size': product['size_' + str(idx)],
                                    'is_published': True,
                                })

                partner_id = self.env['res.partner'].search([('name', '=', product['vendor_name'])], limit=1).id
                if not partner_id:
                    partner_id = self.env['res.partner'].create([{
                        'name': product['vendor_name'],
                        'type': 'contact',
                    }]).id
                product.write({
                    'seller_ids': [[0, False, {'sequence': 1, 'name': partner_id, 'product_id': False, 'product_name': False, 'product_code': product['product_code'],
                                                'currency_id': self.env.ref('base.main_company').currency_id.id, 'mfr_name':product['mfr_name'], 'mfr_num':product['mfr_num'],
                                                'date_start': False, 'date_end': False, 'company_id': self.env.company.id, 'min_qty': 0, 'price': 0, 'delay': 1}]],
                    'is_published': True
                })
        return import_result
