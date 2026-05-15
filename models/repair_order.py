from odoo import fields, models


class RepairOrder(models.Model):
    _inherit = 'repair.order'

    x_studio_confirm_draft_quotation = fields.Boolean(
        string='Confirm Draft Quotation', default=False)
