# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import base64
import itertools
import logging
import csv
import io
import mimetypes
from odoo import api, fields, models, _

try:
    import xlrd
    try:
        from xlrd import xlsx
    except ImportError:
        xlsx = None
except ImportError:
    xlrd = xlsx = None

_logger = logging.getLogger(__name__)

class XlsxIterator:
    def __init__(self, sheet):
        self.sheet = sheet
        self.nrows = sheet.nrows
        self.current_row = 0

    def __iter__(self):
        return self

    def __next__(self):
        if self.current_row >= self.nrows:
            raise StopIteration
        row = self.sheet.row_values(self.current_row)
        self.current_row += 1
        return row


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



class Document(models.Model):
    _inherit = 'documents.document'

    def _get_spreadsheet_iterator(self):
        self.ensure_one()
        filetype = mimetypes.guess_extension(self.mimetype)
        data = base64.b64decode(self.datas)
        if filetype == '.csv':
            return csv.reader(io.StringIO(data.decode('utf-8')))
        elif filetype == '.xlsx':
            sheet = xlrd.open_workbook(file_contents=data).sheet_by_index(0)
            return XlsxIterator(sheet)
        else:
            raise NotImplemented(_("Cannot handle files that are not csv or xlsx!"))

    def _split_document(self, rows = 10000):
        for document in self:
            try:
                row_iterator = document._get_spreadsheet_iterator()
                document._split_rows(row_iterator, rows=rows)
            except Exception as e:
                _logger.error(f'Failed reading file data for {document.name}\nError: {e}')

    def _split_rows(self, row_iterator, rows = 10000):
        for document in self:
            company = document.company_id or self.env.company
            headers = next(row_iterator)
            batch = 1
            current_row = 0
            for row in row_iterator:
                if current_row == 0:
                    output = io.StringIO()
                    writer = csv.writer(output)
                    writer.writerow(headers)
                writer.writerow(row)
                current_row += 1
                if current_row >= rows:
                    part_data = base64.b64encode(output.getvalue().encode('utf-8'))
                    self.env['documents.document'].create({
                        "name": f"{document.attachment_name.split('.')[0]}_Part_{batch}.csv",
                        "datas": part_data,
                        "folder_id": document.folder_id.id
                    })
                    current_row = 0
                    batch += 1
            document.folder_id = company.complete_import_folder.id
        return True