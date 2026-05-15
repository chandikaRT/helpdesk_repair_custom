from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    from odoo.addons.helpdesk_repair_custom import _ensure_stages
    _ensure_stages(env)
