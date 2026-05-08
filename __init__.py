from . import models


def post_init_hook(cr, registry):
    """Deactivate old Studio-created automation rules superseded by this module."""
    from odoo import api, SUPERUSER_ID
    env = api.Environment(cr, SUPERUSER_ID, {})

    # External IDs owned by our module — never touch these
    our_xmlids = {
        'helpdesk_repair_custom.automation_repair_seq',
        'helpdesk_repair_custom.automation_auto_product_from_serial',
        'helpdesk_repair_custom.automation_populate_repair_location',
        'helpdesk_repair_custom.automation_clear_on_serial_change',
        'helpdesk_repair_custom.automation_validate_cancelled_delete',
        'helpdesk_repair_custom.automation_stage_company',
    }
    our_ids = set()
    for xmlid in our_xmlids:
        rec = env.ref(xmlid, raise_if_not_found=False)
        if rec:
            our_ids.add(rec.id)

    # Names of rules that our module replaces
    superseded_names = {
        'RR - Repair Seq.No',
        'RR - Auto Select Product for RUG Repairs',
        'RR - Auto Select Product for RUG Repairs-33',
        'RR - Auto Populate Repair Location',
        'RR - Validate Cancelled Tickets',
        'JIN - Company Id in Helpdesk Stage',
    }
    old_rules = env['base.automation'].search([
        ('action_server_id.name', 'in', list(superseded_names)),
        ('id', 'not in', list(our_ids)),
    ])
    if old_rules:
        old_rules.write({'active': False})
