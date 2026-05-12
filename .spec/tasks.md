# RepairDesk — Implementation Tasks

Module: `helpdesk_repair_custom`
Odoo version: 15.0

Status legend: [DONE] = already implemented and live | [TODO] = not yet implemented | [IMPROVE] = implemented but needs improvement

---

## Phase 1: Foundation (Models, Security, Sequences)

### Task 1.1 — Module skeleton and manifest [DONE]
Files: `__manifest__.py`, `__init__.py`
- Declare all dependencies (`helpdesk`, `helpdesk_fsm`, `helpdesk_stock`, `helpdesk_repair`, `repair`, `sale_management`, `stock`)
- Register `post_init_hook` in `__init__.py`
- List all data files in correct load order (security first, then data, then views)

### Task 1.2 — `x_repair_reason_custom` model [DONE]
File: `models/repair_reason_custom.py`
- Define `_name`, `_description`, `_order`
- Fields: `x_name` (required Char), `x_active` (Boolean, default True), `x_studio_sequence` (Integer, default 10), `x_color` (Integer), `x_studio_company_id` (Many2one `res.company`)

### Task 1.3 — `helpdesk.ticket.type` extension [DONE]
File: `models/helpdesk_ticket_type.py`
- Add `x_studio_rug`, `x_studio_rug_confirmed`, `x_studio_with_serial_no`, `x_studio_without_serial_no` Boolean fields
- Add `x_studio_company_id` Many2one `res.company`

### Task 1.4 — `stock.location` extension [DONE]
File: `models/stock_location.py`
- Add classification flags: `x_studio_repair_factory_location`, `x_studio_repair_return_location`, `x_studio_finished_good_location`, `x_studio_temp_location`
- Add user assignment Many2many fields: `x_studio_many2many_field_7kpUe`, `x_studio_users_stock_location`, `x_studio_users_internal_transfer`
- Add `x_studio_return_receipt_location`, `x_studio_return_sequence`, `x_color`

### Task 1.5 — `stock.picking` extension [DONE]
File: `models/stock_picking.py`
- Add `x_studio_created_from_help_ticket` and `x_studio_helpdesk_ticket_id` (both Many2one `helpdesk.ticket`, ondelete='set null')
- Add `x_studio_factory_repair` Boolean

### Task 1.6 — `helpdesk.ticket` extension — all custom fields [DONE]
File: `models/helpdesk_ticket.py`
- All field groups as documented in design.md section 2.1
- Repair type flags (4 stored Booleans)
- Job routing (Selection + 2 Many2one locations)
- Serials and product (2 Many2one lots + Boolean sn_updated + computed tracking + Boolean serial_created)
- Stock picking references (Integer pick_id + Many2one picking_id + 4 location M2o + computed integer virtual_location_id)
- RUG approval (2 stored Booleans + computed Selection)
- Factory routing flags (4 stored Booleans)
- Factory transfer audit (8 Datetime/Many2one user fields)
- Stage tracking (Datetime stage_date + related Char stage_name)
- Stage guard flags (5 stored Booleans)
- Cancel/reopen (12 stored fields)
- Repair reason (Many2many)
- SO/financial (computed M2o SO + Float balance + Many2many items + 3 Char + M2o material + Float qty)
- All computed status flags (12 computed fields)
- User location validation (computed Boolean)
- Cancel stage gates (2 computed Booleans)
- Misc (2 Binary + 3 Char + 1 Selection quick_repair)
- Stage audit log (10 pairs Many2one user / Datetime)
- Stat button count (computed Integer)

### Task 1.7 — Security: model access control [DONE]
File: `security/ir_model_access.xml`
- `x_repair_reason_custom` read for `base.group_user`
- `x_repair_reason_custom` full CRUD for `helpdesk.group_helpdesk_manager`
- Use `search="[('model','=','x_repair_reason_custom')]"` on `model_id` field (not `ref=`) for portability

### Task 1.8 — Sequences [DONE]
File: `data/ir_sequence_data.xml`
- `repair.seq`: prefix `REPAIR/%(year)s/`, padding 5, start 2000, company = base.main_company
- `repair.serial.seq`: prefix `REP-SERIAL/%(year)s/`, padding 5, start 2000, company = base.main_company
- Both wrapped in `<data noupdate="1">` to prevent sequence reset on module upgrade

### Task 1.9 — Repair reason seed data [DONE]
File: `data/repair_reason_data.xml`
- 10 pump/motor repair reason records under `noupdate="1"`
- Each record: `x_name`, `x_active=True`, `x_studio_sequence=10`

### Task 1.10 — post_init_hook [DONE]
File: `__init__.py`
- On install: search for `base.automation` records whose `action_server_id.name` matches the 6 superseded Studio rule names
- Exclude records owned by this module's own XML IDs
- Set `active = False` on found records

---

## Phase 2: Automation Rules and Server Actions

### Task 2.1 — Server actions for automation rules [DONE]
File: `data/automation_rules.xml` (ir.actions.server section)
- `act_automation_repair_seq`: on_create, assigns `repair.seq` next value to `record.name`
- `act_automation_auto_product_from_serial`: on_change ticket_type_id, full serial-to-SO lookup with company scoping
- `act_automation_clear_on_serial_change`: on_change, clears product/lot/SO/sn_updated
- `act_automation_populate_repair_location`: on_change, mirrors receipt location to repair location
- `act_automation_validate_cancelled_delete`: on_unlink, raises UserError if cancelled
- `act_automation_stage_company`: on_create on helpdesk.stage, stamps company_id

### Task 2.2 — base.automation records [DONE]
File: `data/automation_rules.xml` (base.automation section)
- Wrap each server action in a `base.automation` record with correct trigger
- Rule 2 (`automation_auto_product_from_serial`): set `on_change_field_ids` to `helpdesk.field_helpdesk_ticket__ticket_type_id`
- Rule 5 (`automation_validate_cancelled_delete`): set `filter_domain` to `[["x_studio_cancelled","=",True]]`

### Task 2.3 — Button server actions [DONE]
File: `data/server_actions.xml`
- `action_repair_order_form`: window action to `repair.order` with `default_ticket_id` context
- `action_repair_trans`: window action to `stock.picking` filtered by `x_studio_created_from_help_ticket`
- `action_create_repair_route`: creates done stock picking without serial for without-serial flow
- `action_create_repair_serial`: generates `repair.serial.seq` lot + done picking for without-serial/serial-tracked flow
- `action_send_to_factory`: validates factory location, stamps audit, advances stage
- `action_receive_at_factory`: stamps audit, advances stage
- `action_send_to_sales_centre`: stamps audit, advances stage
- `action_receive_at_sales_centre`: stamps audit, advances stage
- `action_change_type_to_rug`: validates warranty card, zeroes SO line prices, switches ticket type
- `action_cancel_repair`: validates cancel reason, saves stage, moves to Cancelled, stamps audit
- `action_reopen_repair`: restores saved stage, clears cancel flags, stamps reopen audit
- `action_cancel_repair_2`: second cancel path, moves to Repair Completed with cancelled_2=True
- `action_update_serial`: re-runs serial-to-SO lookup, sets sn_updated=True

### Task 2.4 — Improve: company branching in Create Repair Route/Serial [IMPROVE]
Files: `data/server_actions.xml`
Current state: Hard-coded `if company.id == 1:` branch selects between `x_studio_virtual_location` and `x_studio_virtual_location_1`.
Improvement: Replace with a proper per-user or per-company configuration lookup. Options:
- Add a `x_studio_default_virtual_location` field to `res.company` (or `res.users`) and read it dynamically.
- Remove the dual-field approach and use a single `x_studio_virtual_location` field populated per-company via user defaults.
This requires a schema migration for existing data.

### Task 2.5 — Improve: on_change field list for automation rules [IMPROVE]
Files: `data/automation_rules.xml`
Current state: Rules 3 (`clear_on_serial_change`) and 4 (`populate_repair_location`) have no `on_change_field_ids`, causing them to fire on all field changes.
Improvement: Add explicit `on_change_field_ids` pointing to `x_studio_serial_no` (for rule 3) and `x_studio_return_receipt_location` (for rule 4).

---

## Phase 3: Views and UI

### Task 3.1 — Repair Reason views [DONE]
File: `views/repair_reason_custom_views.xml`
- List view: handle sequence widget, name, active
- Form view: name, active, sequence (integer), x_color (color_picker widget)
- Window action: tree + form
- Menu item: under `helpdesk.menu_helpdesk_root`, visible to manager group only, sequence 50

### Task 3.2 — Ticket Type form view [DONE]
File: `views/helpdesk_ticket_type_views.xml`
- Form view showing: name, x_studio_rug, x_studio_rug_confirmed (invisible when rug=False), x_studio_with_serial_no, x_studio_without_serial_no

### Task 3.3 — Ticket form: stat button [DONE]
File: `views/helpdesk_ticket_views.xml` (Record 1: `helpdesk_ticket_view_form_repair_trans`)
- XPath: after `button[@name='action_view_fsm_tasks']`
- Stat button with `fa-folder-open` icon, `oe_stat_button` class
- Invisible when count = 0
- `statinfo` widget on `x_x_studio_created_from_help_ticket_stock_picking_count`

### Task 3.4 — Ticket form: structural field additions [DONE]
File: `views/helpdesk_ticket_views.xml` (Record 2: `helpdesk_ticket_view_form_studio_main`)
- ticket name readonly + sequence placeholder
- stage_id: non-clickable
- team_id, user_id: readonly when RUG in progress
- ticket_type_id: readonly conditions, cleared domain
- After ticket_type_id: repair type indicator booleans (conditional visibility) + receipt location (required when user assigned; readonly when receipt confirmed) + repair location (readonly) + job location (readonly once FSM task created)
- After company_id: 14 invisible computed/guard fields with force_save
- After email_cc: `x_studio_serial_number` (required for serial-based types) + moved `sale_order_id`
- product_id: modified attrs (readonly for serial-tracked types)
- After product_id: 12 invisible status/routing fields + tracking display + source/virtual locations
- After lot_id: `x_studio_serial_no` with same attrs as serial_number
- lot_id: modified visibility (hidden for serial-tracked and RUG types)
- After main sheet group: Factory Repair Details notebook (visible only for Factory Repair)
- After description: `x_studio_repair_reason` (many2many_tags, required when assigned, readonly past New) + `x_studio_cancel_reason`
- After sla_deadline: 15+ invisible status/audit fields
- First notebook page, first group: Delivery Details sub-group (driver, vehicle)
- Second notebook: Warranty Details page (hidden for without-serial) with image widgets
- Second notebook: Cancel/Reopen Log page with readonly audit fields

### Task 3.5 — Ticket form: header buttons [DONE]
File: `views/helpdesk_ticket_views.xml` (Record 3: `helpdesk_ticket_view_form_studio_buttons`, priority 50000)
- Modify base Repair Order button visibility
- Modify base Receipt button visibility + context
- Modify FSM task generation button visibility
- Add "Change Repair Type To RUG" button
- Add "Receipt" button (instance 1: RUG and with-serial normal types)
- Add "Receipt" button (instance 2: without-serial normal before serial created)
- Add "Create Repair Route" button
- Add "Create Repair Serial" button
- Add "Receipt" button (instance 3: without-serial after serial created)
- Add "Update Serial" button
- Add "Send to Factory" button
- Add "Receive at Factory" button
- Add "Send to Sales Centre" button
- Add "Receive at Sales Centre" button
- Add "Cancel" button (primary path)
- Add "Cancel" button (path 2, Estimation Sent stage)
- Add "Reopen" button
- All buttons: confirm dialogs where appropriate, correct `attrs` visibility expressions

### Task 3.6 — Improve: duplicate Serial Number fields [IMPROVE]
Files: `models/helpdesk_ticket.py`, `views/helpdesk_ticket_views.xml`
Current state: Both `x_studio_serial_no` and `x_studio_serial_number` are Many2one fields to `stock.production.lot`. Both appear in the form. The `x_studio_serial_no` is used by server actions; `x_studio_serial_number` appears in the top section of the form.
Improvement: Consolidate to a single field. The form should show only one serial number input. Both fields currently reference the same lot. A migration script should copy values from the less-used field to the primary one before removing it. This reduces confusion for users and simplifies automation logic.

---

## Phase 4: Testing and Validation

### Task 4.1 — Unit tests: model field defaults and constraints [TODO]
File: `tests/test_helpdesk_ticket.py` (new)
- Test that ticket creation assigns a sequence number via the automation rule
- Test that `x_studio_cancel_stage_ok` returns True only for the correct stage names
- Test that `x_studio_cancel2_stage_ok` returns True only for Estimation Sent stage
- Test that `_compute_x_studio_tracking` returns the correct tracking value from product

### Task 4.2 — Unit tests: automation rule logic [TODO]
File: `tests/test_automation_rules.py` (new)
- Test `act_automation_auto_product_from_serial`: create a ticket with a known serial and type, trigger on_change, verify product/lot/SO populated correctly
- Test that the clear rule wipes fields when serial is changed
- Test that `act_automation_populate_repair_location` copies receipt location to repair location
- Test that delete of a cancelled ticket raises UserError

### Task 4.3 — Unit tests: cancel/reopen workflow [TODO]
File: `tests/test_cancel_reopen.py` (new)
- Create ticket, advance to "Diagnosis" stage
- Verify Cancel button gate (`x_studio_cancel_stage_ok = True`)
- Call cancel action without cancel reason — verify UserError raised
- Set cancel reason, call cancel action — verify `x_studio_cancelled = True`, stage = Cancelled, audit fields stamped
- Verify that attempting to unlink the cancelled ticket raises UserError
- Call reopen action — verify stage restored, `x_studio_cancelled = False`, reopen audit stamped
- Test cancel path 2 from Estimation Sent stage

### Task 4.4 — Unit tests: factory repair flow [TODO]
File: `tests/test_factory_flow.py` (new)
- Create ticket with `x_studio_job_location = 'Factory Repair'`
- Call `action_send_to_factory` — verify stage = Sent to Factory, audit fields set
- Call `action_receive_at_factory` — verify stage = Received at Factory
- Mark FSM task as done
- Call `action_send_to_sales_centre` — verify stage = Sent to Sales Centre
- Call `action_receive_at_sales_centre` — verify stage = Received at Sales Centre
- Verify Factory Repair Details tab shows correct values

### Task 4.5 — Unit tests: serial number flows [TODO]
File: `tests/test_serial_flows.py` (new)
- Test "Create Repair Serial" action: verify `repair.serial.seq` is consumed, lot is created, picking created in done state
- Test "Create Repair Route" action: verify picking created in done state without lot
- Test "Update Serial" action: verify product/lot/SO repopulated, `x_studio_sn_updated = True`

### Task 4.6 — Unit tests: RUG type change [TODO]
File: `tests/test_rug_flow.py` (new)
- Create Normal With Serial No ticket with an FSM task and SO
- Attempt "Change Repair Type To RUG" without warranty card — verify UserError
- Upload warranty card, call action — verify SO line prices zeroed to standard cost, ticket_type changed to RUG Confirmed type

### Task 4.7 — Integration test: full Centre Repair lifecycle [TODO]
File: `tests/test_full_lifecycle_centre.py` (new)
- Create partner, product with serial tracking, create serial lot
- Create sale order and delivery to populate stock move history
- Create helpdesk ticket, assign type, serial, receipt location
- Run receipt (stock picking creation)
- Create FSM task, mark done
- Verify automatic stage advancement to Repair Completed
- Verify stat button count reflects the picking

### Task 4.8 — Integration test: full Factory Repair lifecycle [TODO]
File: `tests/test_full_lifecycle_factory.py` (new)
- As above for Centre Repair, but set Job Location = Factory Repair
- Execute all factory routing buttons in sequence
- Verify all audit trail fields populated at each step
- Verify Factory Repair Details tab shows correct dates and users

### Task 4.9 — Data validation: sequence configuration [TODO]
Manual verification checklist:
- Confirm `repair.seq` exists and is active for each company in the database
- Confirm `repair.serial.seq` exists and is active for each company
- Confirm at least one `stock.location` has `x_studio_repair_factory_location = True`
- Confirm stage names exactly match the strings in `_CANCEL_STAGE_NAMES` and `_CANCEL2_STAGE_NAMES`

### Task 4.10 — Data validation: ticket type configuration [TODO]
Manual verification checklist:
- Confirm at least one ticket type has `x_studio_rug = True` AND `x_studio_rug_confirmed = True` (required by "Change Repair Type To RUG")
- Confirm each ticket type has exactly one of `x_studio_with_serial_no` or `x_studio_without_serial_no` set to True (mutual exclusion not enforced by code)
- Confirm ticket types are assigned to the correct company

---

## Phase 5: Improvements and Technical Debt

### Task 5.1 — Eliminate company.id == 1 hard-coding [IMPROVE]
Priority: Medium
Files: `data/server_actions.xml` (action_create_repair_route, action_create_repair_serial)
Approach: Add `x_studio_virtual_location_id` and `x_studio_source_location_id` fields to `res.company` (new file `models/res_company.py`). Update server actions to read `company.x_studio_virtual_location_id` instead of branching on `company.id`. Requires data migration to populate the new company fields from existing ticket field values.

### Task 5.2 — Consolidate duplicate serial number fields [IMPROVE]
Priority: Low
Files: `models/helpdesk_ticket.py`, `views/helpdesk_ticket_views.xml`
Approach: Deprecate `x_studio_serial_number`. Write a one-time migration script that sets `x_studio_serial_no = x_studio_serial_number` for all records where `x_studio_serial_no` is empty. Remove `x_studio_serial_number` field and its view reference. Update all server actions and automation rules that reference `x_studio_serial_number`.

### Task 5.3 — Add explicit on_change_field_ids to automation rules [IMPROVE]
Priority: High (performance)
Files: `data/automation_rules.xml`
Approach: For `automation_clear_on_serial_change`, add:
```xml
<field name="on_change_field_ids" eval="[(4, ref('helpdesk.field_helpdesk_ticket__x_studio_serial_no'))]"/>
```
For `automation_populate_repair_location`, add the `x_studio_return_receipt_location` field reference. This prevents the rules from firing on every form save, improving UI responsiveness.

### Task 5.4 — Add per-company sequences for multi-company databases [TODO]
Priority: High (data integrity)
Files: `data/ir_sequence_data.xml`
Approach: Add sequence records for each company in the database (not only `base.main_company`). Consider whether sequences should use `noupdate="0"` to allow number_next updates on upgrade, or keep `noupdate="1"` and manage them in configuration.

### Task 5.5 — Replace write() calls in compute methods with proper patterns [IMPROVE]
Priority: Medium (ORM correctness)
Files: `models/helpdesk_ticket.py`
Current state: `_compute_x_studio_task_status`, `_compute_x_studio_valid_invoiced_so`, `_compute_x_studio_valid_confirmed_so`, `_compute_x_studio_valid_confirmed2_so`, `_compute_x_studio_valid_delivered_so`, `_compute_x_studio_handed_over` all call `rec['field'] = value` inside the compute loop.
Improvement: Move stage advancement logic to `write()` overrides or `_onchange_` methods that trigger when the source SO/task fields change. This aligns with Odoo ORM best practices and prevents unexpected behaviour during batch operations or imports.

### Task 5.6 — Add `@api.constrains` for mutual exclusion of serial type flags [TODO]
Priority: Low
Files: `models/helpdesk_ticket_type.py`
Approach: Add a constraint that prevents a ticket type from having both `x_studio_with_serial_no = True` and `x_studio_without_serial_no = True` simultaneously.

### Task 5.7 — Add kanban view customizations [TODO]
Priority: Low
Files: `views/helpdesk_ticket_views.xml` (new view record)
Approach: Inherit the standard helpdesk kanban view to show `x_studio_job_location`, `x_studio_cancelled` (as a badge), and the serial number on kanban cards, helping agents identify tickets at a glance.
