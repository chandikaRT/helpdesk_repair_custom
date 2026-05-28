# Session Log: 27-05-2026 10:30 - dispatch-button-and-tested-ok

## Quick Reference (for AI scanning)
**Confidence keywords:** helpdesk_repair_custom, v15.0.1.23, v15.0.1.24, v15.0.1.25, v15.0.1.26, REPAIR/2026/02029, REPAIR/2026/02030, dispatch button, x_studio_so_fully_paid, x_studio_factory_repair, x_studio_ticket_received_at_sales, Received at Sales Centre, Tested OK, Quick Repair, x_studio_end_quick_repair, x_studio_quick_repair_status_1, x_studio_quick_repair_status, Update Serial, RUG ticket, serial number disappears, _sync_ticket_type_flags, _sync_serial_fields, skip_clear, action_tested_ok, _get_stage_by_name, Repair Completed, project_task.py, helpdesk_ticket.py, stock_picking.py, project_task_views.xml, stock_picking_views.xml, attrs field missing error, odoo_repair_fresh, db 2
**Projects:** helpdesk_repair_custom on Odoo 15, db 2 = odoo_repair_fresh; db 1 reference = odoo (production)
**Outcome:** Four sequential changes on db 2: (1) v15.0.1.23 fixed `x_studio_so_fully_paid` to compare total cash received vs SO total (was previously true if all invoices marked paid, even at 50% down-payment); (2) v15.0.1.24 added two new gate conditions for the Dispatch button — `x_studio_factory_repair=True` AND ticket stage = "Received at Sales Centre"; (3) v15.0.1.25 fixed RUG-ticket save bug where `_sync_ticket_type_flags` overwrote the serial back to False when both `ticket_type_id` and `x_studio_serial_no` were saved in the same write; (4) v15.0.1.26 ported the "Tested OK" Quick Repair fast-track button + server action from production to the module.

## Decisions Made
- **`so_fully_paid` semantics**: compare `sum(amount_total - amount_residual)` vs `so.amount_total - 0.01` (epsilon for float). Earlier "all invoices paid" check was wrong because a single 50% down-payment invoice fully paid satisfied it. New check requires the SO total to actually be collected.
- **Dispatch button extra gates**: invisible if `x_studio_factory_repair = False` OR ticket stage != "Received at Sales Centre". Joined with the existing 5 gates via the same `|` (OR) chain — the button only appears when ALL 7 conditions allow it.
- **Stage check by name**, not by ID. Used `ticket.stage_id.name == 'Received at Sales Centre'` (British spelling) instead of hardcoding stage ID — portable across db 1/db 2 which both use the same stage name but different IDs.
- **`x_studio_factory_repair` left as a plain Boolean** (not a related/computed field). Stays as direct flag set on the picking; matches existing module behaviour.
- **Fix RUG serial-loss bug via `skip_clear` parameter** on `_sync_ticket_type_flags`, not by re-ordering writes. Re-ordering would not work because `_sync_ticket_type_flags` calls `super().write({'x_studio_serial_no': False, ...})` which would then need to be re-written. The parameter approach is cleaner: the type flags still propagate (the actual purpose of the sync) but the serial-clearing side-effect is suppressed when the user explicitly set a serial.
- **Tested OK port**: used `_get_stage_by_name('Repair Completed')` instead of db-1's hardcoded `stage = 9 if company==1 else 28`. Both IDs in db 1 happen to be "Repair Completed" — name lookup is portable.
- **Skip `x_studio_cancelled` in Tested OK attrs**. Field exists on `project.task` in db 1 but NOT in db 2. Decided not to add it now; the `helpdesk_ticket_id` + `end_quick_repair` conditions are sufficient. Easy to add later if needed.
- **No diagnosis-validated gate on Tested OK**. db 1 doesn't require it; Quick Repair is meant to bypass the full diagnosis flow. Initially added the gate, then removed after re-reading db 1's attrs.

## Key Learnings
- **`payment_state == 'paid'` is per-invoice, not per-SO.** A 50% down-payment invoice for half the SO amount can be in `payment_state='paid'` while the SO is only half-collected. Checking "all invoices paid" is NOT the same as "SO fully paid". To gate behavior on full SO payment, sum `amount_total - amount_residual` across all posted out_invoices and compare against `so.amount_total`.
- **All fields referenced in `attrs` must be present in the view.** Either as a real form field, or declared `invisible="1"`. Missing the declaration causes view validation to fail with `ParseError: Field 'X' used in attrs ... must be present in view but is missing.` — and crashes the entire module update silently (no DB schema changes get applied).
- **A silent module-update failure can mask itself across many runs.** v1.24 introduced the broken view, which crashed the registry-load step on update. Subsequent updates for v1.25 and v1.26 also crashed at the same point — but `ir_module_module.latest_version` stayed at v1.23 throughout, and the DB schema never got the new columns. The only visible signal at the time was an `Exception` exit code that we lost by piping the command output through grep before checking `$?`.
- **`echo "EXIT: $?"` after a pipeline reports the LAST command's exit code, not the first.** `cmd | grep | tail; echo $?` gives tail's exit code. To capture odoo-bin's actual exit code through a pipe, use `${PIPESTATUS[0]}`.
- **Odoo's `write()` hooks fire in lexical order**, regardless of dependencies. When two `if 'key' in vals:` blocks both call write-style helpers, the second's `super().write({...})` overrides the first's even if logically the second's cleanup should not apply.
- **Stage IDs are duplicated per-company in db 1.** Helpdesk stage 9 and stage 28 are both "Repair Completed" because db 1 has multiple companies. Name-based lookup avoids the per-company branching that's hardcoded in the legacy server action.
- **`material_line_product_count` is a non-stored computed integer** from `industry_fsm_sale`. Usable in attrs without declaring as an invisible field, because it's already loaded when the form renders any related FSM logic.
- **Selection fields default to stored.** Adding `x_studio_quick_repair_status_1 = fields.Selection([...])` requires a schema update to add the column. If the update silently fails, the next time another method reads `fsm_task_ids` (which triggers an `active`-filter read of all task fields), Odoo SELECTs a column that doesn't exist → `UndefinedColumn` error.

## Solutions & Fixes

### 1. v15.0.1.23 — Fix `x_studio_so_fully_paid` computation
`models/project_task.py`:
```python
@api.depends(
    'sale_order_id', 'sale_order_id.amount_total',
    'sale_order_id.invoice_ids.state', 'sale_order_id.invoice_ids.move_type',
    'sale_order_id.invoice_ids.amount_total', 'sale_order_id.invoice_ids.amount_residual',
)
def _compute_x_studio_so_fully_paid(self):
    for task in self:
        so = task.sale_order_id
        if not so:
            task.x_studio_so_fully_paid = False
            continue
        invoices = so.invoice_ids.filtered(
            lambda i: i.state == 'posted' and i.move_type == 'out_invoice')
        total_paid = sum(i.amount_total - i.amount_residual for i in invoices)
        task.x_studio_so_fully_paid = bool(invoices) and total_paid >= so.amount_total - 0.01
```
Replaces the old `all(i.payment_state == 'paid' for i in invoices)` check.

### 2. v15.0.1.24 — Add factory-repair + ticket-stage gates on Dispatch button

**`models/stock_picking.py`** — new computed Boolean tied to existing dispatch-gate compute method:
```python
x_studio_ticket_received_at_sales = fields.Boolean(
    compute='_compute_x_studio_picking_dispatch_gate', store=False,
    string='Ticket Received at Sales Centre')

@api.depends(
    'x_studio_helpdesk_ticket_id',
    'x_studio_helpdesk_ticket_id.stage_id',
    'x_studio_helpdesk_ticket_id.stage_id.name',
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
        picking.x_studio_ticket_received_at_sales = bool(
            ticket and ticket.stage_id.name == 'Received at Sales Centre'
        )
```

**`views/stock_picking_views.xml`** — added invisible fields and extended attrs from 5 to 7 OR-conditions:
```xml
<field name="x_studio_dispatch_done" invisible="1"/>
<field name="x_studio_factory_repair" invisible="1"/>
<field name="x_studio_ticket_received_at_sales" invisible="1"/>
<button name="action_dispatch_return" type="object" string="Dispatch"
        class="btn-primary"
        attrs="{'invisible': ['|','|','|','|','|','|',
            ('state','!=','done'),
            ('x_studio_location_is_customer','=',False),
            ('x_studio_helpdesk_ticket_id','=',False),
            ('x_studio_so_fully_paid','=',False),
            ('x_studio_dispatch_done','=',True),
            ('x_studio_factory_repair','=',False),
            ('x_studio_ticket_received_at_sales','=',False)]}"/>
```
Note: `x_studio_factory_repair` declaration was initially MISSED, causing a silent update crash — see Errors & Workarounds.

### 3. v15.0.1.25 — Fix RUG ticket save wiping the serial

**`models/helpdesk_ticket.py`** — `_sync_ticket_type_flags` gains a `skip_clear` parameter:
```python
def _sync_ticket_type_flags(self, skip_clear=False):
    tt = self.ticket_type_id
    updates = {
        'x_studio_rug_repair': tt.x_studio_rug if tt else False,
        'x_studio_rug_confirmed': tt.x_studio_rug_confirmed if tt else False,
        'x_studio_normal_repair_with_serial_no': tt.x_studio_with_serial_no if tt else False,
        'x_studio_normal_repair_without_serial_no': tt.x_studio_without_serial_no if tt else False,
    }
    if not skip_clear:
        updates.update({
            'sale_order_id': False,
            'x_studio_picking_id': False,
            'x_studio_pick_id': 0,
            'lot_id': False,
            'x_studio_serial_no': False,
        })
        if not (tt and tt.x_studio_without_serial_no):
            updates['product_id'] = False
    super(HelpdeskTicket, self).write(updates)
```
And in `write()`:
```python
if 'ticket_type_id' in vals:
    serial_also_set = bool(vals.get('x_studio_serial_no'))
    for rec in self:
        rec._sync_ticket_type_flags(skip_clear=serial_also_set)
```

### 4. v15.0.1.26 — Port "Tested OK" Quick Repair button

**`models/project_task.py`** — new field + method:
```python
x_studio_quick_repair_status_1 = fields.Selection([
    ('None', 'None'),
    ('Quick Repair', 'Tested OK'),
], string='Quick Repair Status')

def action_tested_ok(self):
    self.ensure_one()
    self.write({
        'x_studio_end_quick_repair': True,
        'x_studio_quick_repair_status_1': 'Quick Repair',
    })
    ticket = self.helpdesk_ticket_id
    if ticket:
        stage_id = ticket._get_stage_by_name('Repair Completed')
        if stage_id:
            ticket.write({
                'stage_id': stage_id,
                'x_studio_stage_date': fields.Datetime.now(),
                'x_studio_repair_complete_stage_updated': True,
                'x_studio_quick_repair_status': 'Quick Repair',
            })
```

**`views/project_task_views.xml`** — button in form header:
```xml
<field name="x_studio_end_quick_repair" invisible="1"/>
...
<button name="action_tested_ok"
        string="Tested OK"
        type="object"
        class="btn-primary"
        attrs="{'invisible': ['|','|',
            ('material_line_product_count', '&gt;', 0),
            ('helpdesk_ticket_id', '=', False),
            ('x_studio_end_quick_repair', '=', True)]}"/>
```

### 5. Update + restart cycle (every version)
```
sudo -u odoo15 /opt/odoo15/myodoo15-venv/bin/python /opt/odoo15/odoo/odoo-bin \
  -c /etc/odoo15.conf -d odoo_repair_fresh \
  --update=helpdesk_repair_custom --stop-after-init 2>&1 | tail -5
echo "ODOO EXIT: ${PIPESTATUS[0]}"   # critical: use PIPESTATUS to capture odoo-bin's exit, not tail's
sudo systemctl restart odoo15 && sleep 5 && sudo systemctl is-active odoo15
```

### 6. Verification queries used
```sql
-- Verify so_fully_paid logic (ticket 02029, 50% paid)
SELECT ht.name, so.amount_total, inv.amount_total, inv.amount_residual,
       inv.payment_state
FROM helpdesk_ticket ht
JOIN project_task pt ON pt.helpdesk_ticket_id = ht.id
JOIN sale_order so ON so.id = pt.sale_order_id
JOIN account_move inv ON inv.invoice_origin = so.name
    AND inv.move_type = 'out_invoice' AND inv.state = 'posted'
WHERE ht.name = 'REPAIR/2026/02029';

-- Verify all dispatch gates for ticket 02030
SELECT ht.name, hs.name AS stage,
       hs.name = 'Received at Sales Centre' AS ticket_received_at_sales,
       sp.name, sp.state, sp.x_studio_factory_repair,
       sl.usage = 'customer' AS location_is_customer,
       SUM(inv.amount_total - inv.amount_residual) AS total_paid,
       so.amount_total
FROM helpdesk_ticket ht ...;

-- Verify column existence + module version after update
SELECT column_name FROM information_schema.columns
WHERE table_name = 'project_task' AND column_name = 'x_studio_quick_repair_status_1';
SELECT latest_version FROM ir_module_module WHERE name = 'helpdesk_repair_custom';
```

## Files Modified
- `/opt/odoo15/custom-addons/helpdesk_repair_custom/__manifest__.py` — version 15.0.1.22 → 15.0.1.23 → 15.0.1.24 → 15.0.1.25 → 15.0.1.26 (four bumps in this session).
- `/opt/odoo15/custom-addons/helpdesk_repair_custom/models/project_task.py`:
  - Rewrote `_compute_x_studio_so_fully_paid` to compare total cash collected vs SO total (v1.23).
  - Added `x_studio_quick_repair_status_1` Selection field and `action_tested_ok()` method (v1.26).
- `/opt/odoo15/custom-addons/helpdesk_repair_custom/models/stock_picking.py`:
  - Added `x_studio_ticket_received_at_sales` computed Boolean and extended `_compute_x_studio_picking_dispatch_gate` (v1.24).
- `/opt/odoo15/custom-addons/helpdesk_repair_custom/models/helpdesk_ticket.py`:
  - `_sync_ticket_type_flags` now accepts `skip_clear=False`; `write()` passes `skip_clear=True` when `x_studio_serial_no` is being set in the same vals (v1.25).
- `/opt/odoo15/custom-addons/helpdesk_repair_custom/views/stock_picking_views.xml`:
  - Added invisible field declarations for `x_studio_ticket_received_at_sales` AND `x_studio_factory_repair` (the latter added in a follow-up fix); extended Dispatch button attrs from 5 to 7 OR-conditions (v1.24, fixed in v1.26 cycle).
- `/opt/odoo15/custom-addons/helpdesk_repair_custom/views/project_task_views.xml`:
  - Added invisible `x_studio_end_quick_repair` field and "Tested OK" button in `//header` xpath, alongside the existing Validate Diagnosis button (v1.26).

## Setup & Config
- **DB updated:** db 2 (`odoo_repair_fresh`) only. db 1 (`odoo`, production) NOT touched in this session.
- **Service:** `odoo15.service` via systemd; active after each restart.
- **Test data on db 2**:
  - Ticket REPAIR/2026/02029 (id 30): SO S00027 total 100.00; one invoice INV/2026/00018 for 50.00 (paid). Used to validate the so_fully_paid fix.
  - Ticket REPAIR/2026/02030 (id 31): SO S00028 total 100.00; two invoices INV/2026/00020 (50.00 paid) + INV/2026/00021 (50.00 unpaid). Stage currently "Handed Over to Customer". Used to verify the new factory-repair + sales-centre gates.
- **Stage name reference**: helpdesk stage "Received at Sales Centre" exists on db 2 with id 14 (sequence 12). British spelling — code uses the name, not the ID.
- **db 1 reference data**: server action 2316 ("RR - End Quick Repair") bound to `helpdesk.ticket` (binding_model_id), executed via `name="2316"` action button in view 3019/4625. Hardcoded stage ids 9 and 28 in db 1 both resolve to "Repair Completed" per company.

## Pending Tasks
- **End-to-end UI verification on db 2** for v15.0.1.23–.26:
  - v1.23: open ticket 02029 → confirm Dispatch button no longer visible despite 50% paid.
  - v1.24: create a factory-repair ticket → confirm Dispatch button only shows on the Receipt-from-Customers picking AND only when ticket stage = "Received at Sales Centre" AND `x_studio_factory_repair=True`.
  - v1.25: create a new RUG ticket → fill ticket_type AND serial AND save → confirm serial number is preserved after save.
  - v1.26: open an FSM task linked to a helpdesk ticket with no materials → Tested OK button appears → click → ticket moves to "Repair Completed", task `end_quick_repair=True`, button hides.
- **Production (db 1) mirror DEFERRED** for v15.0.1.13 through v15.0.1.26. Studio collision strategy still undecided (overwrite Studio / use noupdate / migrate Studio records to claim module xml_ids).
- **Carry-over from earlier sessions** (unchanged): UI walkthroughs for v15.0.1.13–.22 still outstanding.

## Errors & Workarounds
- **Silent module update failure (v1.24-v1.26 stuck at v1.23)**. The Dispatch button's new attrs referenced `x_studio_factory_repair`, but that field was never declared as an invisible field in the xpath block. Odoo's view validator failed with `ParseError: Field 'x_studio_factory_repair' used in attrs ... must be present in view but is missing.` This crashed the registry-load phase BEFORE any DB schema changes were applied. The next three updates (v1.25, v1.26) all hit the same crash and silently bailed out — `latest_version` stayed at v1.23, the new `x_studio_quick_repair_status_1` column was never created, and reading `fsm_task_ids` on the ticket (which triggers an `active`-filter read on all task fields) hit `psycopg2.errors.UndefinedColumn: column project_task.x_studio_quick_repair_status_1 does not exist`. **Fix:** added `<field name="x_studio_factory_repair" invisible="1"/>` to the xpath block.
- **Lost exit code through grep pipeline**. We were using `... | grep -E "ERROR|..." | tail -10; echo "EXIT: $?"` to check update results. `$?` after a pipeline = exit code of the LAST command (tail), not odoo-bin. So we kept seeing `EXIT: 0` while odoo-bin was actually crashing with exit 255. **Fix:** `echo "ODOO EXIT: ${PIPESTATUS[0]}"` to capture the first command's exit code.
- **CacheMiss + UndefinedColumn cascade**. The visible symptom in the browser was a long Python traceback: `CacheMiss: 'helpdesk.ticket(39,).x_studio_rug_approval_status'` → `CacheMiss: 'project.task(24,).active'` → `psycopg2.errors.UndefinedColumn: column project_task.x_studio_quick_repair_status_1 does not exist`. The chain: helpdesk_ticket compute reads `fsm_task_ids` → ORM filters by `active` → SELECTs all stored fields → hits the missing column. Confirms that any stored field referenced anywhere in the model must exist in the DB even if no code path *intentionally* reads it; ORM operations like `active`-filtering read EVERYTHING.
- **Odoo log location**: `/var/log/odoo15/odoo.log`. When `odoo-bin --stop-after-init` produces no stdout output but exits non-zero, the actual `CRITICAL Failed to initialize database` traceback is in the log — `sudo tail -50 /var/log/odoo15/odoo.log` is the fastest path to the root cause.
- **`psql cwd warning` (recurring)**: `cd /tmp` before any `sudo -u postgres psql` to suppress "could not change directory" noise.

## Key Exchanges
- User opened with `/resume`, loaded MEMORY.md + last 3 session logs.
- Ticket REPAIR/2026/02029 dispatch-button-still-visible-at-50% bug → traced to `_compute_x_studio_so_fully_paid` checking `all(payment_state='paid')` instead of total paid vs SO total → v1.23 fix.
- User asked "why is Dispatch button NOT visible on ticket 02030?" — verified data: 50/100 paid, partial second invoice not paid. Confirmed v1.23 fix was working correctly.
- User asked to add two more conditions: factory_repair=True AND ticket at "Received at Sales Centre" stage → v1.24.
- User asked what the "Update Serial" button does on the ticket form → explained the auto-populate-from-serial logic (find outgoing delivery → resolve SO/picking/product/lot).
- User reported "serial number disappears when saving a new RUG ticket" → traced to `_sync_ticket_type_flags` overwriting after `_sync_serial_fields` → v1.25 fix via `skip_clear` parameter.
- User asked to investigate db 1 for "Tested OK" button on project.task → found server action 2316 ("RR - End Quick Repair"); explained Quick Repair flow.
- User asked to port "Tested OK" to db 2 → v1.26 implementation (field + method + button).
- User pasted the production CacheMiss/UndefinedColumn traceback → revealed that the previous 3 updates had been silently failing for 4 hours because of the missing `x_studio_factory_repair` field declaration. Added the field, re-ran the update, confirmed column creation and `latest_version` advance to 15.0.1.26.

## Custom Notes
None

---

## Quick Resume Context
On `helpdesk_repair_custom` v15.0.1.26 on db 2 (`odoo_repair_fresh`). This session shipped four versions: (1) v1.23 fixed `x_studio_so_fully_paid` on `project.task` to compare total cash collected vs SO total — the old "all invoices paid" check returned True for a single 50% down-payment invoice fully paid; (2) v1.24 added two more conditions to the Dispatch button — `x_studio_factory_repair=True` AND ticket stage = "Received at Sales Centre" — via a new computed Boolean on `stock.picking`; (3) v1.25 fixed RUG-ticket-save serial loss by adding `skip_clear=False` to `_sync_ticket_type_flags` (called with `skip_clear=True` when `x_studio_serial_no` is in the same vals); (4) v1.26 ported the "Tested OK" Quick Repair button + `action_tested_ok` method to `project.task`, using `_get_stage_by_name('Repair Completed')` instead of db-1's hardcoded stage IDs. A serious side-issue: v1.24's button attrs referenced `x_studio_factory_repair` without declaring it as an invisible field, which crashed the registry-load on update and silently bailed out — `latest_version` was stuck at 1.23 for three update cycles until the missing field declaration was added. UI walkthrough on db 2 still pending; production mirror still deferred for v1.13–.26.

---

## Raw Session Log

### User: /clear, then /resume

System loaded MEMORY.md + last 3 session logs (27-05 lock-diagnosis-tab-dropdowns, 27-05 repair-diagnosis-menu-port, 26-05 so-confirm-stock-and-repair-trans). Resume summary surfaced v15.0.1.22 state.

### User: In this ticket REPAIR/2026/02029 the dispatch button in the return is visible even though only 50% of the payment is received. The button should only be visible when 100% of the payment is registered.

Assistant investigated the dispatch button visibility logic in `views/stock_picking_views.xml` and traced it to `x_studio_so_fully_paid` on `project.task`. Verified via psql:
```
ticket REPAIR/2026/02029 — SO S00027 total 100.00, INV/2026/00018 50.00 paid (payment_state='paid')
```
Root cause: old check `all(i.payment_state == 'paid' for i in invoices)` returns True when a single 50%-of-SO invoice is fully paid. Fix: compute total paid (sum of `amount_total - amount_residual`) and compare to `so.amount_total - 0.01`. Bumped to v15.0.1.23, updated, restarted. EXIT 0, service active.

### User: check why the dispatch button isn't visible in this ticket REPAIR/2026/02030 (#31)

Investigated ticket 31. SO S00028 total 100.00; two invoices: INV/2026/00020 (50.00 paid) and INV/2026/00021 (50.00 not paid). Total collected: 50/100 = 50%. With v1.23 fix, `so_fully_paid` correctly returns False. Identified WH/RET/00028 as the candidate picking (source=Customers/state=done) — would show the button if SO were fully paid. Explained: pay the second invoice (50.00 residual) and the button will appear.

### User: There should be two additional conditions for the dispatch button to appear. If the job location is Factory Repair and the ticket is at Received at Sales Center

Queried helpdesk_stage on db 2 — found stage id 14 = "Received at Sales Centre" (British spelling). Implementation:
- Added `x_studio_ticket_received_at_sales` computed Boolean to `stock.picking`, extended `_compute_x_studio_picking_dispatch_gate` to compute it via `ticket.stage_id.name == 'Received at Sales Centre'`. Added `stage_id`/`stage_id.name` to `@api.depends`.
- Updated the Dispatch button attrs in `views/stock_picking_views.xml` from 5 to 7 OR-conditions: added `('x_studio_factory_repair','=',False)` and `('x_studio_ticket_received_at_sales','=',False)`. Added `<field name="x_studio_ticket_received_at_sales" invisible="1"/>` declaration.
- **MISSED**: did NOT add a `<field name="x_studio_factory_repair" invisible="1"/>` declaration. This caused the next 3 updates to silently fail.
- Bumped to v15.0.1.24, updated (apparent EXIT 0), restarted. Service "active".
- Verification psql showed: ticket 02030 stage = "Handed Over to Customer", factory_repair=False — both new conditions fail, button correctly hidden.

### User: When a ticket is added as RUG, update serial button appears. What does that button do?

Investigated server action `action_update_serial` ("RR - Auto Select Product for RUG Repairs-22"). Explained:
1. Finds outgoing delivery for the serial (move_line where lot_id=serial, picking_code=outgoing, location_dest_id=customer location)
2. Pulls original SO from `trans_line.origin`, writes `sale_order_id`, `x_studio_picking_id`, `x_studio_pick_id` on ticket
3. Sets `product_id` and `lot_id` from serial's product
4. Sets `x_studio_sn_updated = True` (hides the button)

Summary: it's a serial-to-original-sale lookup. For RUG tickets where the customer brings in a previously-sold product, this auto-fills the ticket without manual SO lookup.

### User: When adding a RUG type ticket after adding the serial and other details when the save button is clicked the serial number disappears

Read the `write` override + `_sync_ticket_type_flags` and `_sync_serial_fields` in `helpdesk_ticket.py`. Identified root cause:
- `write()` calls `_sync_serial_fields()` first (correctly populates product/lot/SO from serial)
- Then calls `_sync_ticket_type_flags()` which writes `x_studio_serial_no = False` to DB — wiping the serial.

Fix: added `skip_clear=False` parameter to `_sync_ticket_type_flags`. In `write()`, set `serial_also_set = bool(vals.get('x_studio_serial_no'))` and pass `skip_clear=serial_also_set`. When both fields are saved in the same vals (new ticket save), type flags still propagate but the serial-clearing side-effect is suppressed.

Bumped to v15.0.1.25, ran update (apparent EXIT 0), restarted. Service active.

### User: Check db 1 for a button called tested ok in the task

Queried db 1 server actions and views. Found:
- Server action id 2316: "RR - End Quick Repair" on `project.task` (mode=code). Sets `x_studio_end_quick_repair=True`, `x_studio_quick_repair_status_1='Quick Repair'` on the task; then on the linked ticket sets `stage_id` to Repair Completed (id 9 for company 1, id 28 for others — both resolve to "Repair Completed"), `x_studio_repair_complete_stage_updated=True`, `x_studio_stage_date=now()`, `x_studio_quick_repair_status='Quick Repair'`.
- Button visibility: hidden if `material_line_product_count > 0` OR `x_studio_cancelled=True` OR `helpdesk_ticket_id=False` OR `x_studio_end_quick_repair=True`.

Summary: Quick Repair fast-track — for repairs with no materials, technician clicks "Tested OK" and ticket jumps straight to "Repair Completed".

### User: implement the same on db 2 custom app

- Added `x_studio_quick_repair_status_1` Selection field to `project.task`.
- Added `action_tested_ok()` method (writes task flags, then ticket stage via `_get_stage_by_name('Repair Completed')` + status fields).
- Added button + invisible `x_studio_end_quick_repair` field to `views/project_task_views.xml` in the `//header` xpath. Initially included a `('x_studio_diagnosis_validated', '=', False)` gate; removed after rechecking db 1's attrs.
- Skipped `x_studio_cancelled` gate (field doesn't exist on db 2's project.task).
- Bumped to v15.0.1.26, ran update (apparent EXIT 0), restarted. Service active.

### User: pasted long CacheMiss/UndefinedColumn traceback ending in psycopg2.errors.UndefinedColumn: column project_task.x_studio_quick_repair_status_1 does not exist

Verified column missing in db 2 via psql. Found `ir_module_module.latest_version = 15.0.1.23` — last three updates had NOT actually advanced the DB. Re-ran the update with `${PIPESTATUS[0]}` to capture odoo-bin's actual exit code → got `255`. Tailed `/var/log/odoo15/odoo.log` → found the real error:
```
ParseError: while parsing /opt/odoo15/custom-addons/helpdesk_repair_custom/views/stock_picking_views.xml:3
Field 'x_studio_factory_repair' used in attrs ... must be present in view but is missing.
```
The v1.24 button change referenced `x_studio_factory_repair` in attrs without declaring it as an invisible field. Every subsequent update crashed at the registry-load phase before any schema changes were applied.

Fix: added `<field name="x_studio_factory_repair" invisible="1"/>` to the xpath block in `stock_picking_views.xml`. Re-ran update — clean (EXIT 0). Verified `x_studio_quick_repair_status_1` column now exists; `latest_version = 15.0.1.26`. Restarted service.

### User: /compress

(Current step.)
