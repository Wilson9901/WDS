# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import base64
import logging
import csv
import io
import mimetypes
from odoo import api, fields, models

try:
    import xlrd
    try:
        from xlrd import xlsx
    except ImportError:
        xlsx = None
except ImportError:
    xlrd = xlsx = None

_logger = logging.getLogger(__name__)


def _convert_sheet_to_list_dict(sheet):
    vals = []
    cols = sheet.row_values(0)
    for row_index in range(1, sheet.nrows):
        row_data = sheet.row_values(row_index)
        vals.append(dict(zip(cols, row_data)))
    return vals

class IrAttachment(models.Model):
    _inherit = 'ir.attachment'

    batch = fields.Integer(default=0)

    def _read_as_dict_list(self):
        self.ensure_one()
        filetype = mimetypes.guess_extension(self.mimetype)
        data = base64.b64decode(self.datas)
        try:
            if filetype == '.xlsx':
                sheet = xlrd.open_workbook(file_contents=data).sheet_by_index(0)
                return _convert_sheet_to_list_dict(sheet)
            elif filetype == '.csv':
                return list(csv.DictReader(io.StringIO(data.decode('utf-8'))))
            else:
                _logger.error(f'Cannot import from {self.name} since it is not the right filetype.')
                return []
        except:
            _logger.error(f'Failed reading file data for {self.name}')
