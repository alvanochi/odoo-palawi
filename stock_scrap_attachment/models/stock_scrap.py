from odoo import _, api, fields, models
from odoo.exceptions import UserError


class StockScrap(models.Model):
    _inherit = 'stock.scrap'

    attachment_ids = fields.Many2many(
        'ir.attachment', 'stock_scrap_ir_attachment_rel', 'scrap_id', 'attachment_id',
        string='Lampiran', copy=False,
        help='Foto atau dokumen bukti scrap. Wajib diisi sebelum Validate.')

    @api.model_create_multi
    def create(self, vals_list):
        scraps = super().create(vals_list)
        scraps._link_attachments()
        return scraps

    def write(self, vals):
        res = super().write(vals)
        if 'attachment_ids' in vals:
            self._link_attachments()
        return res

    def _link_attachments(self):
        """Attach uploaded files to the scrap record.

        Files uploaded through the field start unlinked; linking them makes
        them appear in the chatter and follow the scrap's access rights.
        """
        for scrap in self:
            orphans = scrap.attachment_ids.filtered(
                lambda a: not a.res_model or (a.res_model == scrap._name and not a.res_id))
            if orphans:
                orphans.sudo().write({'res_model': scrap._name, 'res_id': scrap.id})

    def _has_scrap_attachment(self):
        self.ensure_one()
        if self.attachment_ids:
            return True
        # Files dropped in the chatter count as well.
        return bool(self.env['ir.attachment'].sudo().search_count([
            ('res_model', '=', self._name), ('res_id', '=', self.id)], limit=1))

    def _check_scrap_attachment(self):
        if self.env.context.get('skip_scrap_attachment_check'):
            return
        missing = self.filtered(lambda s: not s._has_scrap_attachment())
        if missing:
            raise UserError(_(
                "Lampiran wajib diisi sebelum scrap divalidasi: %s",
                ", ".join(missing.mapped('display_name'))))

    def action_validate(self):
        self._check_scrap_attachment()
        return super().action_validate()

    def do_scrap(self):
        self._check_scrap_attachment()
        return super().do_scrap()
