# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import pytz
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

import odoo
from odoo import models, fields, api, _


_intervalTypes = {
    'days': lambda interval: relativedelta(days=interval),
    'hours': lambda interval: relativedelta(hours=interval),
    'weeks': lambda interval: relativedelta(days=7*interval),
    'months': lambda interval: relativedelta(months=interval),
    'minutes': lambda interval: relativedelta(minutes=interval),
}

class ir_cron(models.Model):
    _inherit = 'ir.cron'

    @classmethod
    def _process_job(cls, job_cr, job, cron_cr):
        with api.Environment.manage():
            try:
                cron = api.Environment(job_cr, job['user_id'], {
                    'lastcall': fields.Datetime.from_string(job['lastcall'])
                })[cls._name]
                # Use the user's timezone to compare and compute datetimes,
                # otherwise unexpected results may appear. For instance, adding
                # 1 month in UTC to July 1st at midnight in GMT+2 gives July 30
                # instead of August 1st!
                now = fields.Datetime.context_timestamp(cron, datetime.now())
                nextcall = fields.Datetime.context_timestamp(cron, fields.Datetime.from_string(job['nextcall']))
                numbercall = job['numbercall']
                ok = False
                while nextcall < now and numbercall:
                    if numbercall > 0:
                        numbercall -= 1
                    if not ok or job['doall']:
                        cron._callback(job['cron_name'], job['ir_actions_server_id'], job['id'])
                    if numbercall:
                        nextcall += _intervalTypes[job['interval_type']](job['interval_number'])
                    ok = True
                addsql = ''
                if not numbercall:
                    addsql = ', active=False'
                if job['id'] == cron.env.ref('wds_product_importing.cron_import_product_documents', raise_if_not_found=False).id and len(cron.env.company.import_folder.document_ids):
                    # update next call to 3 minutes if documents still remain in import folder
                    nextcall = datetime.now() + timedelta(minutes=3)
                if job['id'] == cron.env.ref('wds_product_importing.cron_import_images', raise_if_not_found=False).id and cron.env['product.template'].search([('image_updated','=',True)], limit=1):
                    # update next call to 3 minutes if documents still remain in import folder
                    nextcall = datetime.now() + timedelta(minutes=3)
                cron_cr.execute("UPDATE ir_cron SET nextcall=%s, numbercall=%s, lastcall=%s"+addsql+" WHERE id=%s",(
                    fields.Datetime.to_string(nextcall.astimezone(pytz.UTC)),
                    numbercall,
                    fields.Datetime.to_string(now.astimezone(pytz.UTC)),
                    job['id']
                ))
                cron.flush()
                cron.invalidate_cache()

            finally:
                job_cr.commit()
                cron_cr.commit()
