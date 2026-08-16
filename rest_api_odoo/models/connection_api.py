# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ConnectionApi(models.Model):
    _name = "connection.api"
    _description = "REST API Config"
    _rec_name = "model_id"

    model_id = fields.Many2one(
        "ir.model",
        string="Model",
        required=True,
        ondelete="cascade",
    )

    is_get = fields.Boolean(default=True)
    is_post = fields.Boolean(default=False)
    is_put = fields.Boolean(default=False)
    is_delete = fields.Boolean(default=False)

    get_field_ids = fields.Many2many(
        "ir.model.fields",
        "connection_api_get_field_rel",
        "api_id",
        "field_id",
        string="GET Fields",
        domain="[('model_id', '=', model_id)]",
    )

    post_field_ids = fields.Many2many(
        "ir.model.fields",
        "connection_api_post_field_rel",
        "api_id",
        "field_id",
        string="POST/PUT Fields",
        domain="[('model_id', '=', model_id)]",
    )

    param_ids = fields.One2many(
        "connection.api.param",
        "api_id",
        string="Query Params",
    )

    required_field_ids = fields.Many2many(
        "ir.model.fields",
        string="Required Fields (from model)",
        compute="_compute_required_field_ids",
        readonly=True,
    )

    @api.depends("model_id")
    def _compute_required_field_ids(self):
        for rec in self:
            rec.required_field_ids = rec._get_required_fields_for_model()

    @api.onchange("model_id")
    def _onchange_model_id_set_required_post_fields(self):
        """
        Saat model diganti:
        - kosongkan pilihan fields lama
        - auto-isi post_field_ids dengan field required dari model (non related & non compute)
        """
        for rec in self:
            if not rec.model_id:
                rec.get_field_ids = False
                rec.post_field_ids = False
                return

            required_fields = rec._get_required_fields_for_model()

            # reset selection
            rec.get_field_ids = [(5, 0, 0)]
            rec.post_field_ids = [(5, 0, 0)]

            # auto include required fields for POST/PUT
            rec.post_field_ids |= required_fields

    @api.constrains("post_field_ids", "model_id")
    def _constrains_required_post_fields(self):
        """
        Pastikan POST/PUT Fields selalu mengandung field required dari model.
        """
        for rec in self:
            if not rec.model_id:
                continue

            required_fields = rec._get_required_fields_for_model()
            if not required_fields:
                continue

            missing = required_fields - rec.post_field_ids
            if missing:
                raise ValidationError(_(
                    "POST/PUT Fields must include all required fields.\n"
                    "Missing: %s"
                ) % ", ".join(missing.mapped("name")))

    def _get_required_fields_for_model(self):
        """
        Ambil field required di model yang dipilih.
        Exclude compute & related supaya tidak memaksa field yang tidak perlu di POST/PUT.
        """
        self.ensure_one()
        if not self.model_id:
            return self.env["ir.model.fields"]

        return self.env["ir.model.fields"].search([
            ("model_id", "=", self.model_id.id),
            ("required", "=", True),
            ("store", "=", True),
            ("related", "=", False),
            ("compute", "=", False),
        ])


class ConnectionApiParam(models.Model):
    _name = "connection.api.param"
    _description = "REST API Query Param"

    api_id = fields.Many2one(
        "connection.api",
        required=True,
        ondelete="cascade",
    )

    # Nama model teknis dari parent, contoh: 'hkr.todo.task'
    api_model_name = fields.Char(
        string="API Model Name",
        related="api_id.model_id.model",
        store=False,
        readonly=True,
    )

    name = fields.Char(
        string="Param Name",
        required=True,
        help="Nama parameter di URL, misal: assignment_user",
    )

    # --- FIELD PERTAMA (MODEL UTAMA) ---
    field_id = fields.Many2one(
        "ir.model.fields",
        string="Odoo Field",
        domain="[('model', '=', api_model_name)]",
        help="Field pertama (di model utama).",
    )

    # Nama model relasi dari field pertama, contoh: 'res.users'
    relation_model_name = fields.Char(
        string="Relation Model Name",
        related="field_id.relation",
        store=False,
        readonly=True,
    )

    # --- FIELD DI MODEL RELASI (OPSIONAL) ---
    related_field_id = fields.Many2one(
        "ir.model.fields",
        string="Related Field (optional)",
        domain="[('model', '=', relation_model_name)]",
        help="Field di model relasi (kalau field pertama adalah many2one/x2many).",
    )

    # Path domain yang dipakai controller (contoh: user_id / partner_id.name / line_ids.product_id)
    field_name = fields.Char(
        string="Odoo Field Path",
        help="Nama field di domain, misal: user_id atau task_line_ids.user_id",
    )

    operator = fields.Selection(
        [
            ("=", "="),
            ("!=", "!="),
            ("ilike", "contains"),
            (">=", ">="),
            ("<=", "<="),
            (">", ">"),
            ("<", "<"),
            ("in", "in"),
        ],
        default="=",
        required=True,
    )

    # DISAMAKAN dengan parsing controller kamu: char/int/float/bool
    value_type = fields.Selection(
        [
            ("char", "String"),
            ("int", "Integer"),
            ("float", "Float"),
            ("bool", "Boolean"),
        ],
        default="char",
        required=True,
    )

    method = fields.Selection(
        [
            ("GET", "GET"),
            ("POST", "POST"),
            ("PUT", "PUT"),
            ("DELETE", "DELETE"),
        ],
        default="GET",
        required=True,
    )

    @api.onchange("field_id", "related_field_id")
    def _onchange_field_ids(self):
        """
        Auto-generate field_name:
        - field_id saja: field_id.name
        - field_id + related_field_id: field_id.name.related_field_id.name
        """
        for rec in self:
            if rec.field_id and rec.related_field_id:
                rec.field_name = f"{rec.field_id.name}.{rec.related_field_id.name}"
            elif rec.field_id:
                rec.field_name = rec.field_id.name
            else:
                rec.field_name = False

    @api.constrains("field_name")
    def _check_field_name_required(self):
        """
        Field_name harus terisi (karena dipakai langsung di controller untuk domain).
        """
        for rec in self:
            if not rec.field_name:
                raise ValidationError(_("Odoo Field Path (field_name) is required."))
