from odoo import api, fields, models


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    x_studio_rug_confirmed = fields.Boolean(
        related='order_id.x_studio_rug_confirmed', store=True,
        string='RUG Confirmed')
    x_studio_price_unit_original = fields.Float(
        string='Original Price Unit', digits='Product Price')

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        for line in lines:
            if (line.order_id.x_studio_rug_confirmed
                    and line.order_id.x_studio_is_repair_order
                    and not line.x_studio_price_unit_original
                    and line.product_id):
                line.write({
                    'x_studio_price_unit_original': line.price_unit,
                    'price_unit': line.product_id.standard_price,
                })
        return lines
