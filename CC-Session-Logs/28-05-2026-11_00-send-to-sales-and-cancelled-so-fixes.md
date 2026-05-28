# Session Log: 28-05-2026 11:00 - send-to-sales-and-cancelled-so-fixes

## Quick Reference (for AI scanning)
**Confidence keywords:** helpdesk_repair_custom, v15.0.1.29, v15.0.1.30, v15.0.1.31, Tested OK, Mark as Done, Send to Sales Centre, Dispatch button, cancelled SO, _compute_x_studio_fsm_task_done, _compute_x_studio_task_status, _compute_mark_as_done_buttons, _compute_x_studio_so_fully_paid, x_studio_end_quick_repair, x_studio_so_fully_paid, REPAIR/2026/02043, WH/RET/00041, S00034 cancelled, project_task.py, helpdesk_ticket.py
**Projects:** helpdesk_repair_custom on Odoo 15, db 2 = odoo_repair_fresh
**Outcome:** Three sequential bumps fixing ordering and edge-case bugs after v1.28. v1.29 made Send to Sales Centre wait until Mark as Done is clicked (removed `x_studio_end_quick_repair` short-circuit from the two ticket-level gate computes that were making the button visible immediately after Tested OK). v1.30 fixed Mark as Done not appearing on tasks with a CANCELLED sale_order_id (cancelled SO has no outgoing pickings — previous check hid the button). v1.31 fixed Dispatch not appearing on customer-return pickings of tickets whose linked task has a CANCELLED SO (same root cause — `_compute_x_studio_so_fully_paid` returned False when there were no posted invoices).

## Decisions Made
- **Send to Sales Centre must wait for Mark as Done**, not Tested OK. User explicitly clarified the ordering: Tested OK only enables Mark as Done; clicking Mark as Done is what unlocks Send to Sales Centre. Removed the `or line.x_studio_end_quick_repair` from `_compute_x_studio_fsm_task_done` (line 289) and `_compute_x_studio_task_status` (line 366). The Tested OK button continues to set `x_studio_end_quick_repair=True` on the task and advance the ticket to "Repair Completed", but the Send-to-Sales-Centre gate now requires `fsm_done=True` on at least one task (i.e. Mark as Done was actually clicked).
- **Cancelled SO = "no payment required"** in both Mark as Done and Dispatch gates. Decided to short-circuit early when `so.state == 'cancel'` — same semantic as the existing Tested OK short-circuit. A cancelled SO means the customer is not being billed; the workflow should proceed exactly as if the repair were a Tested OK.
- **Fix at the task-level compute, not the picking aggregation.** For the dispatch fix, options were (A) modify `project_task._compute_x_studio_so_fully_paid` to return True on cancelled SO, or (B) OR `t.sale_order_id.state == 'cancel'` into the picking aggregation. Chose A — keeps the cancellation logic centralised in one compute, the picking aggregation stays clean, and any future downstream code reading the task-level `x_studio_so_fully_paid` field automatically benefits.
- **Did NOT touch the parallel ticket-level `_compute_x_studio_fully_paid_so`** at `helpdesk_ticket.py:293`. User reported only the dispatch button issue; that ticket-level compute is read by other gates. If a downstream gate is later found stuck on a cancelled-SO ticket, apply the same one-line short-circuit there.
- **Leave `x_studio_quick_repair_status_1` selection field unchanged** (still set by `action_tested_ok` though nothing reads it). It's a forward-compatibility hook documented in v1.26 — no reason to remove during a same-day patch series.

## Key Learnings
- **Cancelled SO is a third "no billing required" path** alongside Tested OK and fully-paid SO. The existing dispatch gate had a `x_studio_so_fully_paid OR x_studio_end_quick_repair` aggregation but no cancelled-SO clause. Once you have an OR-chain of "ways to allow this without payment", cancelled-SO almost always belongs in the set — it has the same semantic as Tested OK ("there will never be money on this") but arrives via a completely different user action (SO cancel from the Sales tab, vs Tested OK button).
- **`_compute_x_studio_so_fully_paid` short-circuits cleanly on cancel.** `bool(invoices) and total_paid >= so.amount_total - 0.01` returns False for any cancelled SO (because the invoice filter is `state == 'posted'`, and most cancelled-SO journeys leave no posted invoices). Adding `if so.state == 'cancel': return True` before the invoice math is one of the cleanest fixes possible — no edge cases, no changes to amount tolerance, no view changes.
- **`@api.depends` chains must include `sale_order_id.state`** for any compute that branches on SO cancellation. Without it, the field doesn't refresh when an admin cancels the SO mid-flow. Both v1.30 (Mark as Done) and v1.31 (Dispatch) added this dependency.
- **Ticket-level computes layer above task-level computes.** When you change ordering semantics ("Send to Sales Centre needs Mark as Done"), you find the matching ticket-level gate and remove the task-level Tested-OK short-circuit there. The Tested OK button still fires its own logic on the task; the ticket-level gate just doesn't promote that state to "task complete" until Mark as Done is actually clicked.
- **Postgres column naming quirks in db 2**: `project_task.is_fsm` does not exist as a stored column (compute-only); `stock_picking.picking_type_code` doesn't exist (it's `picking_type_id` with `code` on `stock_picking_type`); `display_mark_as_done_primary/secondary` are not stored. Always introspect columns before assuming.

## Solutions & Fixes

### 1. v15.0.1.29 — Send to Sales Centre waits for Mark as Done

`models/helpdesk_ticket.py` — two parallel one-line changes:

```python
def _compute_x_studio_fsm_task_done(self):
    for rec in self:
        task_status = False
        for line in rec.fsm_task_ids:
            if line.fsm_done:                            # was: if line.fsm_done or line.x_studio_end_quick_repair:
                task_status = True
        rec.x_studio_fsm_task_done = task_status

def _compute_x_studio_task_status(self):
    for rec in self:
        task_status = False
        for line in rec.fsm_task_ids:
            if line.fsm_done:                            # was: if line.fsm_done or line.x_studio_end_quick_repair:
                task_status = True
        if not task_status and rec.x_studio_sale_order:
            ...
```

Both fields gate the "Send to Sales Centre" button at `views/helpdesk_ticket_views.xml:447-453`. With the OR-clauses removed, the button only appears after `fsm_done=True` (Mark as Done clicked).

### 2. v15.0.1.30 — Mark as Done appears on cancelled-SO tasks

`models/project_task.py` — `_compute_mark_as_done_buttons`:

```python
@api.depends(
    'fsm_done', 'is_fsm', 'timer_start',
    'display_enabled_conditions_count', 'display_satisfied_conditions_count',
    'sale_order_id', 'sale_order_id.state',                    # ← added
    'sale_order_id.picking_ids', 'sale_order_id.picking_ids.state',
    'helpdesk_ticket_id', 'x_studio_end_quick_repair',
)
def _compute_mark_as_done_buttons(self):
    super()._compute_mark_as_done_buttons()
    for task in self:
        if task.x_studio_end_quick_repair:
            continue
        hide = False
        if task.sale_order_id:
            so = task.sale_order_id
            if so.state != 'cancel':                            # ← guard added
                outgoing = so.picking_ids.filtered(lambda p: p.picking_type_code == 'outgoing')
                if not outgoing or not all(p.state == 'done' for p in outgoing):
                    hide = True
        elif task.helpdesk_ticket_id:
            hide = True
        if hide:
            task.update({
                'display_mark_as_done_primary': False,
                'display_mark_as_done_secondary': False,
            })
```

A cancelled SO has no outgoing pickings → previous check `if not outgoing or ...` evaluated True and hid the button. Guard skips the outgoing-pickings check entirely on cancelled SOs.

### 3. v15.0.1.31 — Dispatch button visible on cancelled-SO return pickings

`models/project_task.py` — `_compute_x_studio_so_fully_paid`:

```python
@api.depends(
    'sale_order_id', 'sale_order_id.state',                    # ← added .state
    'sale_order_id.amount_total',
    'sale_order_id.invoice_ids.state', 'sale_order_id.invoice_ids.move_type',
    'sale_order_id.invoice_ids.amount_total', 'sale_order_id.invoice_ids.amount_residual',
)
def _compute_x_studio_so_fully_paid(self):
    for task in self:
        so = task.sale_order_id
        if not so:
            task.x_studio_so_fully_paid = False
            continue
        if so.state == 'cancel':                                # ← short-circuit added
            task.x_studio_so_fully_paid = True
            continue
        invoices = so.invoice_ids.filtered(
            lambda i: i.state == 'posted' and i.move_type == 'out_invoice')
        total_paid = sum(i.amount_total - i.amount_residual for i in invoices)
        task.x_studio_so_fully_paid = bool(invoices) and total_paid >= so.amount_total - 0.01
```

The picking-level aggregation at `stock_picking.py:69-70` `any(t.x_studio_so_fully_paid or t.x_studio_end_quick_repair for t in tasks)` now returns True for cancelled-SO tasks, unblocking Dispatch.

### 4. Update + restart cycle (each version, EXIT 0)
```bash
sudo -u odoo15 /opt/odoo15/myodoo15-venv/bin/python /opt/odoo15/odoo/odoo-bin \
  -c /etc/odoo15.conf -d odoo_repair_fresh \
  --update=helpdesk_repair_custom --stop-after-init 2>&1 | tail -5
echo "ODOO EXIT: ${PIPESTATUS[0]}"
sudo systemctl restart odoo15 && sleep 5 && sudo systemctl is-active odoo15
```

### 5. Diagnostic SQL queries used
```sql
-- Inspect ticket state + flags
SELECT ht.id, ht.name AS ticket, hs.name AS stage, ht.x_studio_job_location,
       ht.x_studio_send_to_centre, ht.x_studio_receive_at_centre,
       ht.x_studio_quick_repair_status
FROM helpdesk_ticket ht JOIN helpdesk_stage hs ON hs.id = ht.stage_id
WHERE ht.name = 'REPAIR/2026/02043';

-- Inspect linked task gate fields
SELECT pt.id, pt.fsm_done, pt.x_studio_end_quick_repair,
       pt.x_studio_dispatch_done, pt.sale_order_id
FROM project_task pt WHERE pt.helpdesk_ticket_id = 44;

-- Confirm cancelled SO with no invoices
SELECT name, state, invoice_status, amount_total FROM sale_order WHERE id = 34;
SELECT name, state, move_type, amount_total FROM account_move WHERE invoice_origin = 'S00034';
```

## Files Modified
- `/opt/odoo15/custom-addons/helpdesk_repair_custom/models/helpdesk_ticket.py` — removed `or line.x_studio_end_quick_repair` from `_compute_x_studio_fsm_task_done` (line 289) and `_compute_x_studio_task_status` (line 366). v1.29.
- `/opt/odoo15/custom-addons/helpdesk_repair_custom/models/project_task.py` — `_compute_mark_as_done_buttons` (lines 91–115): added `sale_order_id.state` to `@api.depends`, added `if so.state != 'cancel':` guard around the outgoing-pickings check. `_compute_x_studio_so_fully_paid` (lines 45–62): added `sale_order_id.state` to `@api.depends`, added `if so.state == 'cancel': task.x_studio_so_fully_paid = True; continue` short-circuit. v1.30 + v1.31.
- `/opt/odoo15/custom-addons/helpdesk_repair_custom/__manifest__.py` — `version` bumped 15.0.1.28 → 15.0.1.29 → 15.0.1.30 → 15.0.1.31.
- `/root/.claude/plans/in-task-there-is-lexical-avalanche.md` — rewritten in re-entered plan mode to scope the v1.31 cancelled-SO dispatch fix.

## Setup & Config
- **DB**: db 2 (`odoo_repair_fresh`) only. db 1 (`odoo`, production) NOT touched.
- **Service**: `odoo15.service` via systemd, active after each of the three restarts.
- **No new data files, security entries, or dependencies.**
- **No migration scripts needed** — all changes are computed-field semantics + `@api.depends` updates.

## Pending Tasks
- **End-to-end UI verification on db 2** for the full corrected flow:
  - Centre Repair (HO) Tested OK path: ticket → Repair Completed → task shows Mark as Done → click → task closes. Send to Sales Centre should NOT appear (job_location = Centre Repair).
  - Factory Repair (branch) Tested OK path: ticket → Repair Completed → task shows Mark as Done → click → Send to Sales Centre appears on the ticket → continue normal flow.
  - Cancelled SO + Factory Repair: task shows Mark as Done despite no outgoing pickings; later Dispatch button on return picking is visible.
  - Regression: normal Factory Repair tickets with paid SO still dispatch correctly.
- **Production mirror (db 1)** of v1.13–.31 still deferred. Most v1.27–.31 fixes are equally valid in db 1 (no Studio collision risk), but mirror strategy unresolved for the diagnosis-menu work (v1.20–.22).
- **Ticket-level `_compute_x_studio_fully_paid_so`** at `helpdesk_ticket.py:293` — has parallel structure (`x_studio_fully_invoiced_so or x_studio_end_quick_repair`) but no cancelled-SO short-circuit. Apply same one-liner if a downstream stuck-state is later reported.
- **Carry-over** from prior sessions: UI walkthroughs of v1.13–.26 still outstanding.

## Errors & Workarounds
- **psql column-name surprises** — `helpdesk_ticket.x_studio_factory_repair` (does not exist; field is on stock.picking only — but `x_studio_job_location` is the helpdesk_ticket-side analogue), `project_task.is_fsm` (compute-only, not stored), `project_task.display_mark_as_done_primary/secondary` (not stored), `project_task.material_line_product_count` (compute, not stored), `stock_picking.picking_type_code` (not stored — code lives on `stock_picking_type` joined via `picking_type_id`). Standard pattern: `\d <table>` before guessing columns.
- **No module-update errors** — three sequential module updates exited 0; service active after each.

## Key Exchanges
- User: "Send to sales center button should only be visible after the mark as done is clicked in the task" — clarified the intended ordering. Diagnosed: two ticket-level computes (`_compute_x_studio_fsm_task_done`, `_compute_x_studio_task_status`) had `OR x_studio_end_quick_repair` clauses that made the gate True immediately after Tested OK. Removed those OR clauses. v1.29.
- User: "check why the mark as done button isn't available in this tickets task REPAIR/2026/02043 (#44)" — diagnosed via psql: SO 34 is cancelled with no invoices, no outgoing pickings. `_compute_mark_as_done_buttons` was hiding the button because `not outgoing` evaluated True. Added cancelled-SO guard. v1.30.
- User: "Check why the dispatch button isn't available in the return of the same ticket" — re-entered plan mode (system reminder). Diagnosed: picking-level `x_studio_so_fully_paid` was False because the task-level compute returned False for the cancelled SO (no posted invoices). Wrote plan to overwrite the existing plan file with the new task. Applied parallel fix to `_compute_x_studio_so_fully_paid`. v1.31.

## Custom Notes
None

---

## Quick Resume Context
On `helpdesk_repair_custom` v15.0.1.31 on db 2 (`odoo_repair_fresh`). Three follow-ups after v1.28 corrected the Tested OK / Mark as Done / Send to Sales Centre / Dispatch button gating logic. v1.29 enforced ordering: Tested OK only enables Mark as Done; clicking Mark as Done is what unlocks Send to Sales Centre (removed `OR x_studio_end_quick_repair` from `_compute_x_studio_fsm_task_done` and `_compute_x_studio_task_status` in helpdesk_ticket.py). v1.30 + v1.31 fixed Mark as Done and Dispatch both being hidden when the linked SO is cancelled — added `so.state == 'cancel'` short-circuits in `_compute_mark_as_done_buttons` and `_compute_x_studio_so_fully_paid` on project.task. Cancelled SO is now treated as a third "no billing required" path alongside Tested OK and fully-paid. Validation case is ticket `REPAIR/2026/02043` (#44) with cancelled SO `S00034`. UI walkthroughs still pending; production mirror still deferred.

---

## Raw Session Log

### User: /compress (previous session end @ v1.28)
Session-save workflow ran; log written to `/opt/odoo15/CC-Session-Logs/28-05-2026-09_30-tested-ok-mark-as-done-and-dispatch-fix.md`.

### User: Send to sales center button should only be visible after the mark as done is clicked in the task
Read `helpdesk_ticket.py:285-300` and `helpdesk_ticket.py:362-402`. Confirmed both `_compute_x_studio_fsm_task_done` and `_compute_x_studio_task_status` short-circuited on `x_studio_end_quick_repair` (the Tested OK flag). Both fields gate the Send to Sales Centre button (`views/helpdesk_ticket_views.xml:447-453`).

Removed `or line.x_studio_end_quick_repair` from both compute methods. Bumped manifest 15.0.1.28 → 15.0.1.29. Update EXIT 0, service active. Reported: Send to Sales Centre now waits for actual Mark as Done click (fsm_done=True).

### User: check why the mark as done button isn't available in this tickets task REPAIR/2026/02043 (#44)
Diagnostic via psql on db 2:
- Ticket 44 stage = "Repair Completed", `x_studio_job_location = Factory Repair`.
- Task 29: `fsm_done = NULL`, `x_studio_end_quick_repair = NULL`, `sale_order_id = 34`.
- SO 34: state = `cancel`, invoice_status = `no`, amount_total = 100, 0 invoices, 0 pickings.

Root cause: `_compute_mark_as_done_buttons` checked `so.picking_ids.filtered(outgoing)` which returns empty for cancelled SOs; `not outgoing` then evaluated True and hid the button.

Edited `project_task.py:91-115`:
- Added `sale_order_id.state` to `@api.depends`.
- Wrapped the outgoing-pickings check in `if so.state != 'cancel':`.

Bumped manifest 15.0.1.29 → 15.0.1.30. Update EXIT 0, service active.

### User: (system reminder) Re-entering Plan Mode + new request: Check why the dispatch button isn't available in the return of the same ticket
Read existing plan file (Tested OK / Mark as Done plan from v1.27 — no longer relevant to the new task).

Diagnostic via psql:
- Pickings for ticket 44: WH/OUT/00038 (done), WH/RET/00041 (done, src=customer, state=done).
- Ticket: stage `Received at Sales Centre`, `send_to_centre=t`, `receive_at_centre=t`.
- Task 29: now `fsm_done=t` (user clicked Mark as Done from v1.30 fix), still cancelled SO.

Root cause: picking-level `x_studio_so_fully_paid` gate (condition #4 of 7 in dispatch attrs) computed False because task-level `_compute_x_studio_so_fully_paid` returns False for cancelled SOs (no posted invoices).

Wrote new plan to `/root/.claude/plans/in-task-there-is-lexical-avalanche.md` describing the single one-line fix in `_compute_x_studio_so_fully_paid` on project.task. Called ExitPlanMode, plan approved.

Implementation:
- Edited `project_task.py:45-62`: added `sale_order_id.state` to `@api.depends`, added `if so.state == 'cancel': task.x_studio_so_fully_paid = True; continue` short-circuit.

Bumped manifest 15.0.1.30 → 15.0.1.31. Update EXIT 0, service active. Reported: WH/RET/00041 should now show Dispatch button.

### User: /compress
Session save workflow.
