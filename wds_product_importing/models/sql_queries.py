# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

# Select all variants from the product template
_template_sizes = ' UNION '.join([
    f"""
        SELECT
            id,
            size_{idx} as size,
            unit_{idx} as unit,
            unitqty_{idx} as unitqty,
            cost_{idx} as cost,
            list_{idx} as list
        FROM
            product_template
        WHERE
            unitqty_{idx} IS NOT NULL
            AND unitqty_{idx} <> ''
            AND id IN %(template_ids)s
    """ for idx in range(1, 4)
])

# 
_select_line_values = """
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
        %(attachment_id)s as attachment_id
    FROM
        template_sizes
        LEFT JOIN product_template ON template_sizes.id = product_template.id
        LEFT JOIN product_attribute_value ON template_sizes.size = product_attribute_value.name
        LEFT JOIN insert_attributes ON template_sizes.size = insert_attributes.name
"""

# Relate product templates to attributes
_create_product_template_attribute_line = """
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
    WHERE
        line_values.size IS NOT NULL AND line_values.size <> ''
    ON CONFLICT ON CONSTRAINT product_template_attribute_line_tmpl_attr_uniq DO
    UPDATE
    SET
        active = TRUE 
    RETURNING id, attribute_id, product_tmpl_id
"""

# Set the standard price field on product.product
_create_ir_property_standard_price = """
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
    ON CONFLICT (fields_id, COALESCE(company_id, 0), COALESCE(res_id, ''::character varying)) DO UPDATE SET
        value_float = EXCLUDED.value_float
    RETURNING 
        id, company_id, fields_id, "name", res_id, value_float
"""

_create_product_variant_combination = """
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

_create_product_product = """
    INSERT INTO
        product_product (product_tmpl_id, base_list_price, unit, unitqty, size, attachment_id, active, default_code)
    SELECT DISTINCT ON(default_code) 
        tmpl_id, list, unit, unitqty, size, %(attachment_id)s, TRUE, line_values.default_code
    FROM
        line_values 
    ON CONFLICT ON CONSTRAINT product_product_default_code_unique 
    DO UPDATE SET
        base_list_price = EXCLUDED.base_list_price,
        size = EXCLUDED.size,
        attachment_id = EXCLUDED.attachment_id,
        active = TRUE 
    RETURNING id,
        product_tmpl_id,
        default_code
"""

_create_product_template_attribute_value = """
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
    WHERE
        attribute_id IS NOT NULL
    ON CONFLICT DO NOTHING 
    RETURNING 
        id,
        attribute_line_id,
        product_attribute_value_id,
        product_tmpl_id
"""

_create_product_attribute_value_product_template_attribute_line_rel = """
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

_create_product_attribute_value = '''
    INSERT INTO product_attribute_value (name, attribute_id) 
    SELECT DISTINCT size, %(size_attr_id)s
    FROM template_sizes
    WHERE size IS NOT NULL
    ON CONFLICT DO NOTHING
    RETURNING
        id, name
'''

_create_product_attribute_values = f'''
    WITH template_sizes AS ({_template_sizes})
    INSERT INTO product_attribute_value (name, attribute_id) 
    SELECT DISTINCT size, %(size_attr_id)s
    FROM template_sizes
    ON CONFLICT DO NOTHING
'''

_create_product_variants = f"""
    WITH
        template_sizes AS ({_template_sizes}),
        insert_attributes AS ({_create_product_attribute_value}),
        line_values AS ({_select_line_values}),
        inserted_template_attr_lines AS ({_create_product_template_attribute_line}),
        inserted_attribute_value_template_attribute_line_rel AS ({_create_product_attribute_value_product_template_attribute_line_rel}),
        inserted_product_template_attribute_value AS ({_create_product_template_attribute_value}),
        inserted_products AS ({_create_product_product}),
        insert_product_variant_combo AS ({_create_product_variant_combination}),
        inserted_standard_price AS ({_create_ir_property_standard_price})
    SELECT
        id
    FROM
        inserted_products
"""

_write_product_product_combination_indices = '''
    UPDATE product_product
    SET 
        combination_indices = combination_to_write.combination_indices,
        attachment_id = %(attachment_id)s
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

_write_product_product_lst_price = '''
    UPDATE
        product_product
    SET
        lst_price = product.base_list_price
    FROM
        product_product as product
    WHERE
        product_product.id = product.id AND product.product_tmpl_id IN %(tmpl_ids)s
'''

_write_product_template_list_price = '''
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

_create_res_partner = '''
    INSERT INTO res_partner
        (name, type, display_name, active)
    SELECT
        vendor_name, 'contact', vendor_name, TRUE
    FROM
        (
            SELECT DISTINCT ON (vendor_name)
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

_unlink_product_supplierinfo = '''
    DELETE FROM product_supplierinfo
    WHERE 
        product_tmpl_id IN %(tmpl_ids)s 
        OR product_id IN (SELECT id FROM product_product WHERE product_tmpl_id IN %(tmpl_ids)s)
'''

_select_product_variant_counts = '''
    SELECT
        product_product.product_tmpl_id,
        COUNT(product_product.product_tmpl_id) as num_variants,
        MAX(res_partner.id) as vendor_id
    FROM
        product_product
        JOIN product_template ON product_template.id = product_product.product_tmpl_id
        JOIN res_partner ON product_template.vendor_name = res_partner.name
    WHERE product_template.id IN %(tmpl_ids)s
    GROUP BY product_product.product_tmpl_id, res_partner.name
'''

_create_product_supplierinfo_single_variant = f'''
    INSERT INTO product_supplierinfo
        (sequence, name, product_tmpl_id, product_name, product_code, currency_id, mfr_name, mfr_num, company_id, min_qty, price, delay)
    SELECT DISTINCT
        1 as sequence,
        product_variant_counts.vendor_id as name, 
        product_template.id as product_tmpl_id,
        NULL as product_name,
        product_template.default_code as product_code,
        %(currency_id)s as currency_id,
        product_template.mfr_name as mfr_name,
        product_template.mfr_num as mfr_num,
        %(company_id)s as company_id,
        0 as min_qty,
        product_template.cost_1 as price,
        1 as delay
    FROM
        ({_select_product_variant_counts}) AS product_variant_counts
        JOIN product_template ON product_tmpl_id = product_template.id
    WHERE num_variants = 1
'''

_create_product_supplierinfo_multiple_variant = f'''
    INSERT INTO product_supplierinfo
        (sequence, name, product_tmpl_id, product_id, product_name, product_code, currency_id, mfr_name, mfr_num, company_id, min_qty, price, delay)
    SELECT DISTINCT
        1 as sequence,
        product_variant_counts.vendor_id as name, 
        product_template.id as product_tmpl_id,
        product_product.id as product_id,
        NULL as product_name,
        product_template.default_code as product_code,
        %(currency_id)s as currency_id,
        product_template.mfr_name as mfr_name,
        product_template.mfr_num as mfr_num,
        %(company_id)s as company_id,
        0 as min_qty,
        ir_property.value_float as price,
        1 as delay
    FROM
        ({_select_product_variant_counts}) AS product_variant_counts
        JOIN product_product ON product_variant_counts.product_tmpl_id = product_product.product_tmpl_id
        LEFT JOIN product_template ON product_product.product_tmpl_id = product_template.id
        JOIN ir_property ON res_id = CONCAT('product.product,',product_product.id)
    WHERE num_variants > 1 AND ir_property.fields_id = %(field_id)s
'''

_queries = {
    'create_product_attribute_values': _create_product_attribute_values,
    'create_product_variants': _create_product_variants,
    'write_product_product_combination_indices': _write_product_product_combination_indices,
    'write_product_product_lst_price': _write_product_product_lst_price,
    'write_product_template_list_price': _write_product_template_list_price,
    'create_res_partner': _create_res_partner,
    'unlink_product_supplierinfo': _unlink_product_supplierinfo,
    'create_product_supplierinfo_single_variant': _create_product_supplierinfo_single_variant,
    'create_product_supplierinfo_multiple_variant': _create_product_supplierinfo_multiple_variant
}