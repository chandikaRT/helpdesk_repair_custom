from odoo import api, models


class StockReturnPicking(models.TransientModel):
    _inherit = 'stock.return.picking'

    @api.onchange('picking_id')
    def _onchange_picking_id_ticket_location(self):
        """After base onchange computes location_id from the picking, override it with
        the ticket's virtual repair location (which the Return action validates against)."""
        ticket_id = self.env.context.get('default_ticket_id')
        if not ticket_id or not self.picking_id:
            return
        ticket = self.env['helpdesk.ticket'].browse(ticket_id)
        company_id = self.env.context.get('allowed_company_ids', [self.env.user.company_id.id])[0]
        if company_id == 1:
            virtual_loc = ticket.x_studio_virtual_location
        else:
            virtual_loc = ticket.x_studio_virtual_location_1
        if virtual_loc:
            self.location_id = virtual_loc
