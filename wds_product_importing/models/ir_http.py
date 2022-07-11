from odoo import models


class Http(models.AbstractModel):
    _inherit = 'ir.http'

    def binary_content(self, xmlid=None, model='ir.attachment', id=None, field='datas',
                       unique=False, filename=None, filename_field='name', download=False,
                       mimetype=None, default_mimetype='application/octet-stream',
                       access_token=None):
        if model in ['product.template','product.product']:
            obj = None
            if xmlid:
                obj = self._xmlid_to_obj(self.env, xmlid)
            elif id and model in self.env:
                obj = self.env[model].browse(int(id))
            if obj.image_updated or (not obj[field] and obj.image_url):
                obj = obj.with_context(active_test=False, prefetch_fields=False, mail_notrack=True, tracking_disable=True, mail_activity_quick_update=False).sudo()
                if obj._name == 'product.product':
                    obj = obj.product_tmpl_id
                obj._import_single_image()
                # try:
                #     obj.image_1920 = obj._import_image_cached(obj.image_url, obj.id)
                #     obj.image_updated = False
                #     obj.image_failed = False
                # except Exception as e:
                #     obj.image_1920 = self.env.company.logo
                #     obj.image_failed = True

        return super().binary_content(
            xmlid=xmlid, model=model, id=id, field=field, unique=unique, filename=filename,
            filename_field=filename_field, download=download, mimetype=mimetype,
            default_mimetype=default_mimetype, access_token=access_token)