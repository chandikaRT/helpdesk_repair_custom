# Session Log: 25-05-2026 12:00 - three-delivery-dispatch-return-flow

## Quick Reference (for AI scanning)
**Confidence keywords:** helpdesk_repair_custom, v15.0.1.13, Repair Completed, all outgoing pickings done, Mark as Done gate, Sent to Sales Centre, Received at Sales Centre, Dispatch button on picking, stock.return.picking wizard, create_returns override, x_studio_is_dispatch, action_dispatch_return, second return, Handed Over to Customer, _compute_x_studio_handed_over neutralized, project.task action_dispatch removed, fsm_task_ids, odoo_repair_fresh, db 2
**Projects:** helpdesk_repair_custom on Odoo 15, db 2 = odoo_repair_fresh
**Outcome:** Rewired the late-stage repair flow so "Repair Completed" fires only when ALL outgoing pickings on the SO are done; Dispatch moved from FSM task button to a button on the first return picking that opens the standard return wizard preloaded; the wizard-created second return carries `x_studio_is_dispatch=True` so validating it advances ticket to "Handed Over to Customer". Removed the legacy FSM Dispatch button + action_dispatch; neutralized stage auto-advance in _compute_x_studio_handed_over. v15.0.1.12 → v15.0.1.13.

## Decisions Made
- **"Repair Completed" gate is now `all(picking_type_code='outgoing' AND state='done')` across `sale_order.picking_ids`**, not "any done picking to customer location". Reason: user has 3 outgoing pickings on the SO and explicitly wants the stage to advance only when all three are validated.
- **Dispatch button on stock.picking, not on the FSM task.** Reason: user wants the dispatch action to come from "within the return" (the first customer→virtual incoming receipt). This also aligns with the wizard-driven flow.
- **Dispatch creates the second return via the standard `stock.return.picking` wizard, not via a custom direct-create.** Reason: the wizard already swaps src/dest (virtual → customer), copies moves with serial/lot lines, and `helpdesk_stock.create_returns` already adds the new picking to `ticket.picking_ids` + posts chatter. Reusing it avoids re-implementing those.
- **Flag the new (second) return as `x_studio_is_dispatch=True` via a new wizard field.** Reason: the existing `button_validate` post-validate loop already advances "Handed Over to Customer" when an `x_studio_is_dispatch` picking goes done. Reuse that mechanism instead of adding a new validate hook.
- **`_compute_x_studio_handed_over` stripped of stage-advance logic.** Reason: it advanced to "Handed Over" whenever ≥2 pickings on the ticket were done. Under the new flow (3 outgoing + 1 incoming return ≥ 2), it would fire prematurely, before the dispatch transfer even exists.
- **Use a `compute` (not `related`) for the picking-form gate fields.** Reason: traversing `x_studio_helpdesk_ticket_id.fsm_task_ids.x_studio_so_fully_paid` via `related` would aggregate over a One2many, which Odoo doesn't collapse cleanly to a Boolean. A compute with the same `@api.depends` chain is unambiguous (`any(...)` of task booleans).
- **Sales Centre buttons stay restricted to Factory Repair.** Confirmed by user — no scope change there.
- **Mark-as-Done is a pure UI gate.** Confirmed by user — no stage change on click. Existing `_compute_mark_as_done_buttons` already gates on all-outgoing-done, so it aligns with the new Repair Completed gate by construction.

## Key Learnings
- **In `helpdesk_repair_custom`, the ticket→tasks reverse relation is `fsm_task_ids` (not `task_ids`).** Used in existing `_compute_x_studio_valid_delivered_so` (`helpdesk_ticket.py:459`). Important when writing `@api.depends` chains from `stock.picking`.
- **`helpdesk_stock.stock.return.picking.create_returns` already does the ticket-linking work.** It does `ticket_id.picking_ids |= picking_id` and `message_post_with_view(...)` on the new picking. No need to duplicate this in the custom override — just call `super()` first, then add only the dispatch-specific flag propagation.
- **Standard wizard's `_create_returns` swaps src/dest when copying the source picking** via `_prepare_picking_default_values`. So returning from a customer→virtual picking automatically produces a virtual→customer picking. No manual location wiring needed.
- **`stock.return.picking` already has a `picking_id` domain `[('id', 'in', suitable_picking_ids)]` from `helpdesk_stock`'s `_compute_suitable_picking_ids`** (SO's `picking_ids` filtered to `state='done'`). Custom dispatch pickings (`action_dispatch` legacy) lacked `sale_id`/`group_id` so they wouldn't appear in this domain — irrelevant now since we no longer use that path.
- **The `_compute_x_studio_handed_over` "≥2 done pickings → advance stage" was a latent landmine.** It would have fired the moment the second outgoing got validated under the new flow. Important to neutralize *before* shipping the "all outgoing done → Repair Completed" change.

## Solutions & Fixes

### 1. New Repair Completed gate (all outgoing done)
`models/stock_picking.py` `button_validate()` post-validate loop:
```python
# ALL outgoing deliveries on this SO done → Repair Completed
if not ticket.x_studio_repair_complete_stage_updated:
    outgoing = so.picking_ids.filtered(
        lambda p: p.picking_type_code == 'outgoing')
    if outgoing and all(p.state == 'done' for p in outgoing):
        stage_id = ticket._get_stage_by_name('Repair Completed')
        if stage_id:
            ticket.write({
                'stage_id': stage_id,
                'x_studio_stage_date': datetime.datetime.now(),
                'x_studio_repair_complete_stage_updated': True,
            })
            task.x_studio_valid_delivered_so2 = True
```
Removed the prior `customer_loc` lookup + "any done picking to customer" branch.

### 2. Dispatch button on first return picking
`models/stock_picking.py` — added compute fields + action method:
```python
x_studio_location_is_customer = fields.Boolean(compute='_compute_x_studio_location_is_customer')
x_studio_so_fully_paid = fields.Boolean(compute='_compute_x_studio_picking_dispatch_gate', string='SO Fully Paid')
x_studio_dispatch_done = fields.Boolean(compute='_compute_x_studio_picking_dispatch_gate', string='Dispatch Done')

@api.depends('location_id', 'location_id.usage')
def _compute_x_studio_location_is_customer(self):
    for p in self:
        p.x_studio_location_is_customer = (p.location_id.usage == 'customer')

@api.depends(
    'x_studio_helpdesk_ticket_id',
    'x_studio_helpdesk_ticket_id.fsm_task_ids',
    'x_studio_helpdesk_ticket_id.fsm_task_ids.x_studio_so_fully_paid',
    'x_studio_helpdesk_ticket_id.fsm_task_ids.x_studio_dispatch_done',
)
def _compute_x_studio_picking_dispatch_gate(self):
    for picking in self:
        ticket = picking.x_studio_helpdesk_ticket_id
        tasks = ticket.fsm_task_ids if ticket else self.env['project.task']
        picking.x_studio_so_fully_paid = any(t.x_studio_so_fully_paid for t in tasks)
        picking.x_studio_dispatch_done = any(t.x_studio_dispatch_done for t in tasks)

def action_dispatch_return(self):
    self.ensure_one()
    ticket = self.x_studio_helpdesk_ticket_id
    if not ticket:
        raise UserError("This picking is not linked to a helpdesk ticket.")
    return {
        'name': 'Return Transfer',
        'type': 'ir.actions.act_window',
        'res_model': 'stock.return.picking',
        'view_mode': 'form',
        'target': 'new',
        'context': {
            'active_id': self.id,
            'active_ids': [self.id],
            'active_model': 'stock.picking',
            'default_picking_id': self.id,
            'default_ticket_id': ticket.id,
            'default_x_studio_is_dispatch': True,
        },
    }
```
View: `views/stock_picking_views.xml` — added invisible fields + Dispatch button before `button_validate` with attrs:
```xml
attrs="{'invisible': ['|','|','|','|',
    ('state','!=','done'),
    ('x_studio_location_is_customer','=',False),
    ('x_studio_helpdesk_ticket_id','=',False),
    ('x_studio_so_fully_paid','=',False),
    ('x_studio_dispatch_done','=',True)]}"
```

### 3. Wizard propagates dispatch flag to the new picking
`models/stock_return_picking.py`:
```python
x_studio_is_dispatch = fields.Boolean(string='Is Dispatch Return')

def create_returns(self):
    result = super().create_returns()
    if not self.x_studio_is_dispatch:
        return result
    new_picking = self.env['stock.picking'].browse(result.get('res_id'))
    if new_picking:
        new_picking.x_studio_is_dispatch = True
        ticket = self.ticket_id
        if ticket:
            new_picking.x_studio_helpdesk_ticket_id = ticket.id
            task = self.env['project.task'].search(
                [('helpdesk_ticket_id', '=', ticket.id)], limit=1)
            if task:
                task.x_studio_dispatch_done = True
    return result
```

### 4. Neutralized legacy auto-Handed-Over compute
`models/helpdesk_ticket.py` `_compute_x_studio_handed_over` shrunk to:
```python
def _compute_x_studio_handed_over(self):
    for rec in self:
        c = sum(1 for line in rec.picking_ids if line.state == 'done')
        rec.x_studio_handed_over = c > 1
```
No more `stage_id` writes inside this compute. The only authoritative path to "Handed Over to Customer" is now the `x_studio_is_dispatch` branch in `button_validate`.

### 5. Removed legacy FSM Dispatch path
- `models/project_task.py`: deleted entire `action_dispatch()` method (lines 62-135 in the old file); removed unused `datetime` import; removed `UserError` import.
- `views/project_task_views.xml`: emptied to just `<odoo></odoo>` (the only record was the Dispatch button xpath).

### 6. Update + restart commands
```
sudo -u odoo15 /opt/odoo15/myodoo15-venv/bin/python /opt/odoo15/odoo/odoo-bin \
  -c /etc/odoo15.conf -d odoo_repair_fresh \
  --update=helpdesk_repair_custom --stop-after-init
# exit 0, clean
sudo systemctl restart odoo15 && sleep 5 && sudo systemctl is-active odoo15
# active
```

## Files Modified
- `/opt/odoo15/custom-addons/helpdesk_repair_custom/__manifest__.py` — version 15.0.1.12 → 15.0.1.13.
- `/opt/odoo15/custom-addons/helpdesk_repair_custom/models/stock_picking.py` — Repair Completed gate changed to all-outgoing-done; added 3 compute gate fields (`x_studio_location_is_customer`, `x_studio_so_fully_paid`, `x_studio_dispatch_done`) for picking form button visibility; added `action_dispatch_return()` method that opens the return wizard preloaded with `default_x_studio_is_dispatch=True`.
- `/opt/odoo15/custom-addons/helpdesk_repair_custom/models/stock_return_picking.py` — added `x_studio_is_dispatch` Boolean field; added `create_returns()` override that flags the new picking, links it to the ticket, and sets `task.x_studio_dispatch_done=True`.
- `/opt/odoo15/custom-addons/helpdesk_repair_custom/models/helpdesk_ticket.py` — `_compute_x_studio_handed_over` stripped of stage-advance branch (no longer auto-advances to "Handed Over to Customer" when ≥2 pickings are done).
- `/opt/odoo15/custom-addons/helpdesk_repair_custom/models/project_task.py` — removed `action_dispatch()` method and `datetime` + `UserError` imports.
- `/opt/odoo15/custom-addons/helpdesk_repair_custom/views/stock_picking_views.xml` — added 3 invisible gate fields and the Dispatch button before `button_validate`.
- `/opt/odoo15/custom-addons/helpdesk_repair_custom/views/project_task_views.xml` — emptied to no-op (removed the FSM-task Dispatch button record).
- `/root/.claude/plans/there-is-a-flow-happy-breeze.md` — plan file written during planning phase (kept for reference).

## Setup & Config
- **DB:** db 2 = `odoo_repair_fresh` (the changes were updated against it). db 1 (production) NOT yet touched — mirror after verification.
- **Service:** `odoo15.service` via systemd.
- **Module update command:**
  ```
  sudo -u odoo15 /opt/odoo15/myodoo15-venv/bin/python /opt/odoo15/odoo/odoo-bin \
    -c /etc/odoo15.conf -d odoo_repair_fresh --update=helpdesk_repair_custom --stop-after-init
  ```
- **Restart only (no schema):** `sudo systemctl restart odoo15 && sleep 4 && sudo systemctl is-active odoo15`

## Pending Tasks
- **End-to-end UI verification on db 2 (Factory Repair ticket):**
  1. Confirm SO with 3 outgoing pickings.
  2. Validate pickings one by one — confirm "Repair Completed" only fires when all 3 are done (not after the first or second).
  3. Confirm Mark-as-Done button appears on the FSM task only after step 2; clicking it has no stage effect.
  4. On the helpdesk ticket header, confirm "Send to Sales Centre" then "Receive at Sales Centre" buttons advance the ticket.
  5. Complete invoicing to 100% paid.
  6. Open the first return picking (customer→virtual, state=done) — confirm Dispatch button now visible.
  7. Click Dispatch → wizard opens preloaded → click standard "Return" → new picking created with virtual→customer locations.
  8. Inspect new picking: `x_studio_is_dispatch=True`, `x_studio_helpdesk_ticket_id` set, appears under ticket's transfers.
  9. Validate new picking → ticket → "Handed Over to Customer".
  10. Confirm Dispatch button now hidden on the original first return (`x_studio_dispatch_done=True`).
- **Regression check on Centre Repair (non-Factory) ticket:** Sales Centre buttons stay hidden; Repair Completed → Dispatch → Handed Over still works.
- **Regression check:** `_compute_x_studio_handed_over` no longer prematurely advances when many pickings done.
- **Mirror to db 1 (production)** once db 2 verification passes. Production may already have Studio versions of some computes — check before duplicating.

## Errors & Workarounds
None during this session. Module update was clean (exit 0), service restart healthy.

Caveats to watch in verification:
- The legacy `_compute_x_studio_valid_delivered_so` fallback Repair Completed branch is intentionally left in place. With the new `task.x_studio_valid_delivered_so2` only being set when all outgoing are done, this fallback is now effectively guarded — but if a Studio user manually sets `valid_delivered_so2=True` somewhere, the compute could still fire. Low risk; intentionally not removed for safety.
- `fsm_task_ids` was confirmed to exist on `helpdesk.ticket` (used in existing computes). The new compute on `stock.picking` depends on this path — if a future refactor renames it, the picking gate fields silently stop updating.

## Key Exchanges
- User stated the new flow in prose; I asked four clarifying questions before designing: (1) what "3 deliveries" means, (2) whether Dispatch moves to the return form or stays on the FSM task, (3) whether Sales Centre buttons should be opened beyond Factory Repair, (4) whether Mark-as-Done should change stage.
- Answers received: "All outgoing pickings on the SO" / "On the first return picking, remove from FSM task" / "Keep Factory Repair only" / "Pure UI gate, no stage change". These directly drove the design.
- Plan file written to `/root/.claude/plans/there-is-a-flow-happy-breeze.md`, approved via ExitPlanMode.
- Implementation completed in 7 edits across 6 files + 1 manifest version bump. Module update + restart both clean.

## Custom Notes
None

---

## Quick Resume Context
On `helpdesk_repair_custom` v15.0.1.13 on db 2 (`odoo_repair_fresh`). This session restructured the late-stage repair flow so "Repair Completed" fires only when ALL outgoing pickings on the SO are validated (was: any one to customer location); moved the Dispatch button from the FSM task form to the first return picking form, where clicking it opens the standard `stock.return.picking` wizard preloaded; the wizard's `create_returns()` was overridden to flag the new (second) return with `x_studio_is_dispatch=True` so the existing button_validate hook still advances "Handed Over to Customer" when that second return is validated. Legacy `_compute_x_studio_handed_over` was neutralized (no more auto-advance on ≥2 done pickings), and the now-unused `project.task.action_dispatch` was removed along with its FSM-task button. Module updated and service restarted cleanly. Next: user does the full end-to-end UI walkthrough on db 2, then mirror to production db 1.

---

## Raw Session Log

### User
/resume

### Assistant
Loaded MEMORY.md and the last 3 session summaries (payment-dispatch-stage-automation, fsm-task-and-so-stage-flow, receipt-flow-fixes). Reported current state: v15.0.1.12 on db 2, financial/dispatch automation wired but not yet end-to-end tested.

### User
"There is a flow change required within the sales order attached to the task there are three deliveries generated. when all three deliveries are marked as done the ticket should change to repair completed. Then the button mark as done should be visible in the task. When that button is clicked the ticket will be able to move to the next two stages (sent to sales center and received at sales center) via the buttons in the ticket. The invoice for the sales order will be 100% completed, then within the return there should be a button called dispatch. When dispatch button is clicked the reverse return form is opened which will then create a second return from the destination in the first return to the customer. Then the second return will be validated at which point the ticket will move to Handed over to customer stage."

### Assistant
[Plan mode active] Launched 2 parallel Explore agents:
- Agent 1: mapped current stage-transition triggers (Repair Started, Repair Completed, Sent/Received Sales Centre, Handed Over, Mark-as-Done gate, Dispatch button, x_studio_is_dispatch field, guard flags, helper methods)
- Agent 2: explored SO deliveries and return wizard (what 3 pickings make up the SO, the return wizard model/view, standard create_returns, helpdesk_stock override)

Reports came back with full code traces. Key findings:
- Current "Repair Completed" fires on first done picking to customer location
- Dispatch button on FSM task, calls action_dispatch which directly creates virtual→customer picking
- helpdesk_stock.create_returns already links new pickings to ticket.picking_ids
- standard wizard swaps src/dest when reversing
- _compute_x_studio_handed_over has a latent "≥2 done pickings → advance stage" that would fire prematurely under new flow

Then asked 4 clarifying questions via AskUserQuestion:
1. What are the 3 deliveries? → "All outgoing pickings on the SO"
2. Dispatch button placement? → "On the first return picking, remove from FSM task"
3. Sales Centre scope? → "Keep Factory Repair only"
4. Mark-as-Done effect? → "Pure UI gate, no stage change"

### Assistant
Wrote plan to `/root/.claude/plans/there-is-a-flow-happy-breeze.md` covering 8 file changes:
1. stock_picking.py: Repair Completed gate → all-outgoing-done; compute gate fields; action_dispatch_return method
2. helpdesk_ticket.py: neutralize _compute_x_studio_handed_over
3. stock_return_picking.py: add x_studio_is_dispatch field + create_returns override
4. views/stock_picking_views.xml: Dispatch button before button_validate
5. views/project_task_views.xml: remove FSM Dispatch button
6. project_task.py: remove action_dispatch()
7. __manifest__.py: 15.0.1.12 → 15.0.1.13
8. Verification steps

Called ExitPlanMode. User approved.

### User
[Plan approved]

### Assistant
Implemented all changes in order:
- stock_picking.py: added compute fields x_studio_location_is_customer, x_studio_so_fully_paid, x_studio_dispatch_done with proper @api.depends chains; changed Repair Completed condition to `outgoing and all(p.state=='done' for p in outgoing)`; added action_dispatch_return that opens stock.return.picking wizard with default_x_studio_is_dispatch=True context
- stock_return_picking.py: added x_studio_is_dispatch Boolean; added create_returns() override that flags new picking + links to ticket + sets task.x_studio_dispatch_done
- helpdesk_ticket.py: shrunk _compute_x_studio_handed_over to just compute the field (no stage write)
- views/stock_picking_views.xml: added 3 invisible gate fields + Dispatch button with the 5-condition invisible attrs
- views/project_task_views.xml: emptied to `<odoo></odoo>`
- project_task.py: removed action_dispatch() + unused datetime/UserError imports
- __manifest__.py: bumped to 15.0.1.13

Ran module update on db 2 — exit 0 clean. Restarted systemctl odoo15 — active. Final summary delivered to user.

### User
/compress

### Assistant
[Current step — preserving session]
