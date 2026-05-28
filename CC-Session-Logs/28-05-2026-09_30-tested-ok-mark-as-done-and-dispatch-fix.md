# Session Log: 28-05-2026 09:30 - tested-ok-mark-as-done-and-dispatch-fix

## Quick Reference (for AI scanning)
**Confidence keywords:** helpdesk_repair_custom, v15.0.1.27, v15.0.1.28, Tested OK, Mark as Done, Send to Sales Centre, Dispatch button, x_studio_end_quick_repair, x_studio_factory_repair, x_studio_ticket_factory_repair, x_studio_job_location, Factory Repair, Centre Repair, _compute_mark_as_done_buttons, _compute_x_studio_picking_dispatch_gate, REPAIR/2026/02040, WH/RET/00036, project_task.py, stock_picking.py, stock_picking_views.xml, Studio automation gap, odoo_repair_fresh, db 2
**Projects:** helpdesk_repair_custom on Odoo 15, db 2 = odoo_repair_fresh
**Outcome:** Two follow-ups to the v1.26 Tested OK port. v1.27 made Mark as Done appear on the task after Tested OK (Centre Repair flow) and let the dispatch return treat Tested OK as fully paid. v1.28 fixed the latent bug where Dispatch was already blocked for ALL Factory Repair tickets on db 2 — the stored Boolean `stock.picking.x_studio_factory_repair` is set by a Studio automation that exists only in db 1, so on db 2 every picking has the flag False. Replaced the gate with a new non-stored computed field `x_studio_ticket_factory_repair` that reads `ticket.x_studio_job_location == 'Factory Repair'` directly.

## Decisions Made
- **Mark as Done after Tested OK** — extend `_compute_mark_as_done_buttons` rather than touching the upstream FSM compute. Added `x_studio_end_quick_repair` to `@api.depends` and an early `continue` so the hide logic is bypassed for Tested OK tasks. Lets the standard `is_fsm`/`fsm_done` upstream behaviour drive the button.
- **Send to Sales Centre needs no XML change** — confirmed by tracing: `x_studio_fsm_task_done` and `x_studio_task_status` both compute True when `x_studio_end_quick_repair=True` (already-existing computes at `helpdesk_ticket.py:289, 366`). `x_studio_receive_at_factory` was already required for the technician to test in the first place. The button gates already align.
- **Dispatch gate treats Tested OK as paid** — mirror the precedent at `helpdesk_ticket.py:297` (`_compute_x_studio_fully_paid_so` already uses `or x_studio_end_quick_repair`). Single edit in `_compute_x_studio_picking_dispatch_gate` to OR the `end_quick_repair` flag into the `so_fully_paid` aggregation.
- **`x_studio_factory_repair` → replace with computed field** — once we discovered db 2 has the flag False on every picking (it's set by a Studio rule that only exists in db 1), keeping the stored field as the gate would break for everyone. Decision: add a new non-stored computed `x_studio_ticket_factory_repair` that derives directly from `ticket.x_studio_job_location`. Same naming pattern as the existing `x_studio_ticket_received_at_sales` computed field — keeps the module self-contained, no Studio automation needed.
- **Leave the legacy `x_studio_factory_repair` stored field alone** — don't remove it because it still has the invisible field declaration in the view (used elsewhere potentially) and the db column. Just stop gating on it. Pure additive change.
- **Branch axis confirmed as `x_studio_job_location`** — user picked it (over `company_id != 1` or new is_branch flag on helpdesk.team). "Factory Repair" = branch, "Centre Repair" = HO/local. Matches every other Sales Centre button in the module.

## Key Learnings
- **`x_studio_factory_repair` on stock.picking is Studio-automation-driven, NOT module-driven.** The field exists as a plain stored Boolean (`models/stock_picking.py:14`) but no module code ever writes it. A Studio automation rule in db 1 sets it (presumably from the ticket's `x_studio_job_location` on picking create). The module never ported that automation, so on db 2 every ticket-linked picking has `x_studio_factory_repair = False`. This silently broke the Dispatch button for ALL Factory Repair tickets on db 2 starting from v1.24, not just Tested OK ones. Lesson: any time the module references a stored field that no module code writes, suspect a Studio automation gap. Verify with `SELECT name, x_studio_factory_repair FROM stock_picking WHERE x_studio_helpdesk_ticket_id IS NOT NULL` early.
- **Computed gate fields scale to more conditions trivially.** The `_compute_x_studio_picking_dispatch_gate` method already aggregated three booleans onto the picking from the ticket/tasks. Adding a fourth (`x_studio_ticket_factory_repair`) was one extra assignment + one extra `@api.depends` line. Cheaper than relying on a stored field set elsewhere.
- **Pattern reuse beats inventing a new mechanism.** The existing `helpdesk_ticket.py:297` already showed that `x_studio_end_quick_repair` is an established equivalent of "fully paid/invoiced". Mirroring that pattern in the picking-level gate was a 1-line change rather than introducing a new field.
- **`x_studio_job_location` is the canonical branch discriminator in this module.** Every Sales Centre button (Send to Sales Centre, Receive at Sales Centre, etc.) already gates on `x_studio_job_location == 'Factory Repair'`. Using anything else (company_id, team flag, location flag) would diverge from established practice.

## Solutions & Fixes

### 1. v15.0.1.27 — Mark as Done after Tested OK + Dispatch treats Tested OK as paid

**`models/project_task.py`** — extended `_compute_mark_as_done_buttons`:
```python
@api.depends(
    'fsm_done', 'is_fsm', 'timer_start',
    'display_enabled_conditions_count', 'display_satisfied_conditions_count',
    'sale_order_id', 'sale_order_id.picking_ids', 'sale_order_id.picking_ids.state',
    'helpdesk_ticket_id', 'x_studio_end_quick_repair',     # ← added
)
def _compute_mark_as_done_buttons(self):
    super()._compute_mark_as_done_buttons()
    for task in self:
        if task.x_studio_end_quick_repair:                  # ← new early-exit
            continue
        hide = False
        if task.sale_order_id:
            so = task.sale_order_id
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

**`models/stock_picking.py`** — extended dispatch gate to treat Tested OK as fully paid:
```python
@api.depends(
    ...,
    'x_studio_helpdesk_ticket_id.fsm_task_ids.x_studio_end_quick_repair',  # ← added
)
def _compute_x_studio_picking_dispatch_gate(self):
    for picking in self:
        ticket = picking.x_studio_helpdesk_ticket_id
        tasks = ticket.fsm_task_ids if ticket else self.env['project.task']
        picking.x_studio_so_fully_paid = any(
            t.x_studio_so_fully_paid or t.x_studio_end_quick_repair  # ← OR clause added
            for t in tasks)
        ...
```

### 2. v15.0.1.28 — Replace broken `x_studio_factory_repair` gate with computed field

**Root-cause diagnosis** — SQL on db 2:
```sql
SELECT sp.id, sp.name, sp.x_studio_factory_repair, ht.x_studio_job_location
FROM stock_picking sp
LEFT JOIN helpdesk_ticket ht ON ht.id = sp.x_studio_helpdesk_ticket_id
WHERE sp.x_studio_helpdesk_ticket_id IS NOT NULL;
-- All 35 return pickings have x_studio_factory_repair = f or NULL,
-- but ticket.x_studio_job_location = 'Factory Repair' on most of them.
```

**`models/stock_picking.py`** — new computed field + compute branch:
```python
x_studio_ticket_factory_repair = fields.Boolean(
    compute='_compute_x_studio_picking_dispatch_gate', store=False,
    string='Ticket is Factory Repair')

# @api.depends gains:
#   'x_studio_helpdesk_ticket_id.x_studio_job_location',
# and in the method body:
picking.x_studio_ticket_factory_repair = bool(
    ticket and ticket.x_studio_job_location == 'Factory Repair'
)
```

**`views/stock_picking_views.xml`** — added invisible field declaration and swapped attrs entry:
```xml
<field name="x_studio_factory_repair" invisible="1"/>           <!-- legacy, kept -->
<field name="x_studio_ticket_received_at_sales" invisible="1"/>
<field name="x_studio_ticket_factory_repair" invisible="1"/>    <!-- new -->
<button name="action_dispatch_return" ...
        attrs="{'invisible': ['|','|','|','|','|','|',
            ('state','!=','done'),
            ('x_studio_location_is_customer','=',False),
            ('x_studio_helpdesk_ticket_id','=',False),
            ('x_studio_so_fully_paid','=',False),
            ('x_studio_dispatch_done','=',True),
            ('x_studio_ticket_factory_repair','=',False),       <!-- was x_studio_factory_repair -->
            ('x_studio_ticket_received_at_sales','=',False)]}"/>
```

### 3. Update + restart cycle (both versions, EXIT 0 each time)
```bash
sudo -u odoo15 /opt/odoo15/myodoo15-venv/bin/python /opt/odoo15/odoo/odoo-bin \
  -c /etc/odoo15.conf -d odoo_repair_fresh \
  --update=helpdesk_repair_custom --stop-after-init 2>&1 | tail -5
echo "ODOO EXIT: ${PIPESTATUS[0]}"
sudo systemctl restart odoo15 && sleep 5 && sudo systemctl is-active odoo15
```

## Files Modified
- `/opt/odoo15/custom-addons/helpdesk_repair_custom/models/project_task.py` — extended `_compute_mark_as_done_buttons` (lines 91–114): added `x_studio_end_quick_repair` to `@api.depends`, added `if task.x_studio_end_quick_repair: continue` early-exit, removed stale 2-line comment.
- `/opt/odoo15/custom-addons/helpdesk_repair_custom/models/stock_picking.py` — extended `_compute_x_studio_picking_dispatch_gate` (lines 39–78): added new field `x_studio_ticket_factory_repair`, added `x_studio_job_location` and `fsm_task_ids.x_studio_end_quick_repair` to `@api.depends`, OR'd `t.x_studio_end_quick_repair` into the `x_studio_so_fully_paid` aggregation, added compute branch for new field.
- `/opt/odoo15/custom-addons/helpdesk_repair_custom/views/stock_picking_views.xml` — added `<field name="x_studio_ticket_factory_repair" invisible="1"/>` declaration, swapped the 6th OR condition in the Dispatch button attrs from `x_studio_factory_repair` to `x_studio_ticket_factory_repair`.
- `/opt/odoo15/custom-addons/helpdesk_repair_custom/__manifest__.py` — `version` bumped 15.0.1.26 → 15.0.1.27 → 15.0.1.28.
- `/root/.claude/plans/in-task-there-is-lexical-avalanche.md` — plan file documenting v1.27 changes (created during plan mode).

## Setup & Config
- **DB**: db 2 (`odoo_repair_fresh`) only. db 1 (`odoo`, production) NOT touched.
- **Service**: `odoo15.service` via systemd, active after both restarts.
- **No new data files, security entries, or dependencies.**
- **No migration script needed** — the stored `x_studio_factory_repair` field is left in place (still declared, still in db schema); the dispatch gate just doesn't use it anymore.

## Pending Tasks
- **End-to-end UI verification on db 2** for the Tested OK → Send to Sales Centre → Receive at Sales Centre → Dispatch → Handed Over to Customer flow on a Factory Repair ticket. Ticket `REPAIR/2026/02040` (#41) is staged at "Received at Sales Centre" — clicking the now-visible Dispatch button on `WH/RET/00036` should open the return wizard.
- **Centre Repair Tested OK path** verification (Mark as Done button appears, click closes the task).
- **Production mirror (db 1)** of v1.13–.28 still deferred. In db 1 the Studio automation that sets `x_studio_factory_repair` on picking exists — so the v1.28 swap to a computed gate is harmless there too (computed field returns True for Factory Repair tickets, same as the Studio-set stored field). Could be considered a forward-compatible improvement.
- **Verify nothing else gates on the stored `x_studio_factory_repair`** before considering removing it. Quick grep showed only the Dispatch button attrs referenced it on the view side; model code never wrote it.
- **Carry-over** from prior sessions: UI walkthroughs of v1.13–.26 still outstanding.

## Errors & Workarounds
- **`x_studio_factory_repair` always False on db 2** — the field exists on `stock.picking` but no module code writes it; a Studio automation in db 1 (not migrated) sets it on picking create. This was a hidden coupling that broke Dispatch for every Factory Repair ticket on db 2 since v1.24, masked by the fact that v1.24's session focused on the new gate conditions not the existing one. Fix: replace with computed field derived from ticket's `x_studio_job_location`. **Lesson recorded in memory** — see Custom Notes.
- **psql column name surprises** — `helpdesk_ticket.x_studio_factory_repair` doesn't exist (was a guess; the field lives on stock.picking only); `stock_picking.picking_type_code` doesn't exist (it's `picking_type_id`, with `code` on `stock_picking_type`). Standard pattern: introspect with `\d stock_picking` before assuming column names.
- **No module-update errors** — both v1.27 and v1.28 module updates exited cleanly; service active after both restarts.

## Key Exchanges
- User: "in task there is a button called tested ok. If this button is clicked then the mark as done button should appear to complete the task. if its from a branch then sent to sales center button should appear and that flow continues. Tested ok means that there was no repair required so the customer won't be billed for it. This needs to be considered in the dispatch button in the return."
- Planning workflow: 3 Explore agents in parallel mapped Tested OK + Mark as Done + Send to Sales Centre buttons, dispatch gate + computed fields, and branch-vs-HO discrimination respectively. 3 clarifying questions confirmed branch = Factory Repair, Send button stays on ticket form, Tested OK only after Receive at Factory. Plan written, ExitPlanMode approved.
- v1.27 shipped 2 minimal edits + manifest bump, EXIT 0.
- User: "The dispatch button is not appearing when gone through repair ok REPAIR/2026/02040 (#41)"
- Diagnosed via psql: ticket #41 stage = "Received at Sales Centre", `x_studio_job_location = 'Factory Repair'`, but `WH/RET/00036.x_studio_factory_repair = f`. Cross-checked all 35 ticket-linked return pickings on db 2 → all have the flag False. Identified Studio-automation gap as root cause.
- v1.28 added computed `x_studio_ticket_factory_repair`, swapped the attrs entry, kept legacy stored field intact. EXIT 0.

## Custom Notes
None

---

## Quick Resume Context
On `helpdesk_repair_custom` v15.0.1.28 on db 2 (`odoo_repair_fresh`). This session extended the v1.26 Tested OK port with two follow-ups: (1) v1.27 made Mark as Done appear on the task after Tested OK (early-exit in `_compute_mark_as_done_buttons`) and made the dispatch return treat Tested OK as fully paid (OR'd `x_studio_end_quick_repair` into the existing `x_studio_so_fully_paid` aggregation, mirroring `helpdesk_ticket.py:297`). (2) v1.28 fixed a latent bug introduced in v1.24: the dispatch button gated on the stored `x_studio_factory_repair` Boolean on `stock.picking`, but that field is set by a Studio automation that only exists in db 1 — on db 2 the flag is always False, so Dispatch was hidden for ALL Factory Repair tickets since v1.24, not just Tested OK ones. Fix: new non-stored computed field `x_studio_ticket_factory_repair` on `stock.picking` reading directly from `ticket.x_studio_job_location == 'Factory Repair'`, swapped into the dispatch attrs. Legacy stored field left in place. Ticket `REPAIR/2026/02040` (#41) is the validation case at "Received at Sales Centre" stage. UI walkthroughs still pending; production mirror still deferred but v1.28 is forward-compatible with db 1 (Studio rule still sets the stored field; module gate now derives from the ticket directly).

---

## Raw Session Log

### User: /resume
Loaded MEMORY.md (already in context) + 3 most recent session logs: 27-05 10:30 dispatch-button-and-tested-ok (v1.23–.26), 27-05 05:01 lock-diagnosis-tab-dropdowns (v1.22), 27-05 04:50 repair-diagnosis-menu-port (v1.20/.21). Reported module state v15.0.1.26 on db 2, no project-level CLAUDE.md found, pending UI verification and production mirror still outstanding.

### User: In task there is a button called tested ok. If this button is clicked then the mark as done button should appear to complete the task. if its from a branch then sent to sales center button should appear and that flow continues Tested ok means that there was no repair required so the customer won't be billed for it. This needs to be considered in the dispatch button in the return.
Entered plan mode. Launched 3 Explore agents in parallel:
1. Tested OK + Mark as Done + Send to Sales Centre flow — found `action_tested_ok` at `project_task.py:74-89`, `_compute_mark_as_done_buttons` Python-only gate at `project_task.py:91-114`, "Send to Sales Centre" button at `helpdesk_ticket_views.xml:447-453` with attrs gating on `x_studio_fsm_task_done`, `x_studio_task_status`, `x_studio_receive_at_factory`, `x_studio_send_to_centre=False`, `x_studio_job_location='Factory Repair'`. Server actions `action_send_to_sales_centre`/`action_receive_at_sales_centre` at `data/server_actions.xml:312-360`. No branch-vs-HO flag exists; `x_studio_job_location` is the de facto discriminator.
2. Dispatch button + SO-paid gating — full 7-condition `attrs` quoted, `_compute_x_studio_picking_dispatch_gate` and source-of-truth `_compute_x_studio_so_fully_paid`. Strong precedent at `helpdesk_ticket.py:297` where `x_studio_end_quick_repair` is already used as equivalent to fully invoiced.
3. Stage flow + branch routing — confirmed 13 stages defined in `__init__.py:5-19`, including "Sent to Sales Centre" and "Received at Sales Centre" as distinct stages. `_get_stage_by_name` does team-scoped then global lookup. `x_studio_factory_repair` on `stock.picking` declared but NEVER written by module code (set by Studio in db 1).

Asked 3 clarifying questions via AskUserQuestion:
1. Branch field → `x_studio_job_location = 'Factory Repair'` (chosen)
2. Send to Sales Centre placement → on helpdesk ticket form (existing, no XML change)
3. Tested OK timing → only after Receive at Factory (no relax-attrs needed)

Wrote plan to `/root/.claude/plans/in-task-there-is-lexical-avalanche.md`. ExitPlanMode approved.

### Implementation v15.0.1.27
1. Edited `models/project_task.py` — added `x_studio_end_quick_repair` to `@api.depends`, added `if task.x_studio_end_quick_repair: continue` early-exit in `_compute_mark_as_done_buttons`, removed inline comment.
2. Edited `models/stock_picking.py` — added `fsm_task_ids.x_studio_end_quick_repair` to `@api.depends`, OR'd `t.x_studio_end_quick_repair` into the `x_studio_so_fully_paid` aggregation.
3. Bumped `__manifest__.py` 15.0.1.26 → 15.0.1.27.
4. Update + restart cycle, EXIT 0, service active.

Reported back: 3 changes summarised, no view changes needed for Send to Sales Centre (existing computes flip it visible naturally).

### User: The dispatch button is not appearing when gone through repair ok REPAIR/2026/02040 (#41)
Diagnosed via psql on db 2:
- Ticket #41 stage = "Received at Sales Centre", `x_studio_job_location = 'Factory Repair'`, `x_studio_send_to_centre = t`, `x_studio_receive_at_centre = t`, `x_studio_quick_repair_status = 'Quick Repair'`. ✓
- Two pickings linked: `WH/OUT/00035` (outgoing, done) and `WH/RET/00036` (incoming customer return, done, src=customer).
- Critical finding: `WH/RET/00036.x_studio_factory_repair = f`. Cross-checked all 35 ticket-linked return pickings on db 2 → every single one has `x_studio_factory_repair = f` or NULL, despite tickets being Factory Repair.

Root cause: `x_studio_factory_repair` on `stock.picking` is a stored Boolean that the module declares but never writes. The flag is set by a Studio automation rule that exists in db 1 (production) but was never migrated to the module. This silently broke Dispatch for ALL Factory Repair tickets on db 2 since v1.24.

### Implementation v15.0.1.28
1. Edited `models/stock_picking.py`:
   - New field declaration `x_studio_ticket_factory_repair = fields.Boolean(compute=..., store=False, string='Ticket is Factory Repair')`.
   - Added `x_studio_helpdesk_ticket_id.x_studio_job_location` to `@api.depends`.
   - Added compute branch: `picking.x_studio_ticket_factory_repair = bool(ticket and ticket.x_studio_job_location == 'Factory Repair')`.
2. Edited `views/stock_picking_views.xml`:
   - Added `<field name="x_studio_ticket_factory_repair" invisible="1"/>` after `x_studio_ticket_received_at_sales`.
   - Swapped the 6th OR condition in the Dispatch button attrs from `('x_studio_factory_repair','=',False)` to `('x_studio_ticket_factory_repair','=',False)`.
3. Bumped manifest 15.0.1.27 → 15.0.1.28.
4. Update + restart cycle, EXIT 0, service active.

Reported back: root cause (Studio automation gap), one-line fix, no view-level removal (legacy field kept), Dispatch should now be visible on `WH/RET/00036`.

### User: /compress
Session save workflow.
