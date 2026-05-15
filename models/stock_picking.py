from odoo import fields, models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    x_studio_created_from_help_ticket = fields.Many2one(
        'helpdesk.ticket', string='Created from Help Ticket', ondelete='set null')
    x_studio_helpdesk_ticket_id = fields.Many2one(
        'helpdesk.ticket', string='Helpdesk Ticket Id', ondelete='set null')
    x_studio_factory_repair = fields.Boolean(string='Factory Repair')
    x_studio_rug_repair = fields.Boolean(
        related='x_studio_helpdesk_ticket_id.x_studio_rug_repair',
        string='RUG Repair', store=False)
