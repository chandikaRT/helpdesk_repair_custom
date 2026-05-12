# RepairDesk — Technical Design

Module: `helpdesk_repair_custom`
Odoo version: 15.0
File: `custom-addons/helpdesk_repair_custom/`

---

## 1. Module Architecture

### 1.1 Dependency Graph

```
helpdesk_repair_custom
├── helpdesk              (base helpdesk.ticket, stages, teams, ticket types)
├── helpdesk_fsm          (FSM task integration: fsm_task_ids on ticket)
├── helpdesk_stock        (stock picking integration: picking_ids on ticket)
├── helpdesk_repair       (repair.order link on ticket, Repair Order button)
├── repair                (repair.order model)
├── sale_management       (sale.order link: sale_order_id on ticket)
└── stock                 (stock.location, stock.picking, stock.production.lot)
```

### 1.2 File Map

```
helpdesk_repair_custom/
├── __init__.py                     imports models sub-package; defines post_init_hook
├── __manifest__.py                 module declaration, depends, data load order
├── models/
│   ├── __init__.py                 imports all model files
│   ├── helpdesk_ticket.py          main extension — custom fields and computed methods
│   ├── helpdesk_ticket_type.py     repair-type flags and company scoping on ticket type
│   ├── helpdesk_team.py            stub (no new fields; kept for future use)
│   ├── repair_order.py             stub (no new fields; kept for future use)
│   ├── repair_reason_custom.py     new model x_repair_reason_custom
│   ├── stock_location.py           location classification and user-assignment fields
│   └── stock_picking.py            back-link to helpdesk ticket on stock picking
├── security/
│   └── ir_model_access.xml         ACL for x_repair_reason_custom
├── data/
│   ├── ir_sequence_data.xml        repair.seq and repair.serial.seq sequences
│   ├── repair_reason_data.xml      10 seed repair reason records (noupdate=1)
│   ├── server_actions.xml          standalone ir.actions.server records (button actions)
│   └── automation_rules.xml        base.automation + ir.actions.server for triggers
├── views/
│   ├── helpdesk_ticket_views.xml       form view inheritance (3 view records)
│   ├── helpdesk_ticket_type_views.xml  ticket type form override
│   └── repair_reason_custom_views.xml  list/form/action/menu for repair reasons
└── report/
    └── .gitkeep
```

### 1.3 Data Load Order (from manifest)

1. `security/ir_model_access.xml` — must be first so model records can be written
2. `data/ir_sequence_data.xml`
3. `data/repair_reason_data.xml`
4. `data/server_actions.xml` — server action records referenced by automation_rules.xml
5. `data/automation_rules.xml` — depends on server_actions.xml XIDs
6. `views/repair_reason_custom_views.xml`
7. `views/helpdesk_ticket_type_views.xml`
8. `views/helpdesk_ticket_views.xml`

---

## 2. Model Inheritance Chain

### 2.1 `helpdesk.ticket` (extended in `models/helpdesk_ticket.py`)

Base class: `models.Model` with `_inherit = 'helpdesk.ticket'`

All new fields use the `x_studio_` prefix (Studio convention retained for compatibility with existing data in the database).

#### Field Groups

**Repair type flags** (stored booleans, copied from ticket type on selection):
- `x_studio_rug_repair` — Boolean — device is under warranty
- `x_studio_rug_confirmed` — Boolean — warranty is confirmed (not just claimed)
- `x_studio_normal_repair_with_serial_no` — Boolean
- `x_studio_normal_repair_without_serial_no` — Boolean

**Job routing** (stored):
- `x_studio_job_location` — Selection `[Centre Repair, Factory Repair]`
- `x_studio_repair_location` — Many2one `stock.location` — auto-set from receipt location or factory location
- `x_studio_return_receipt_location` — Many2one `stock.location` — where the device was physically received

**Serials and product** (mix of stored/computed):
- `x_studio_serial_no` — Many2one `stock.production.lot` — primary serial link (triggers automations)
- `x_studio_serial_number` — Many2one `stock.production.lot` — alternate display serial field
- `x_studio_sn_updated` — Boolean — True after "Update Serial" confirms the lookup
- `x_studio_tracking` — Selection `[serial, lot, none]` — computed from `product_id.tracking`, not stored
- `x_studio_repair_serial_created` — Boolean — True after a system serial is generated

**Stock picking references** (mix of stored integer/M2o):
- `x_studio_pick_id` — Integer — picking database id (used in button context, avoids M2o in domain)
- `x_studio_picking_id` — Many2one `stock.picking`
- `x_studio_source_location` — Many2one `stock.location` — company 1 source for outgoing move
- `x_studio_source_location_1` — Many2one `stock.location` — company 2+ source
- `x_studio_virtual_location` — Many2one `stock.location` — company 1 virtual/transit
- `x_studio_virtual_location_1` — Many2one `stock.location` — company 2+ virtual/transit
- `x_studio_virtual_location_id` — Integer — computed from `x_studio_virtual_location.id`, stored

**RUG approval** (computed, not stored):
- `x_studio_rug_approved` — Boolean — True if linked SO has `x_studio_rug_approved = True`
- `x_studio_rug_request_sent` — Boolean — True if RUG request was dispatched
- `x_studio_rug_approval_status` — Selection `[Pending, RUG Approved, RUG Rejected]` — computed from fsm_task linked SOs

**Factory routing flags** (stored booleans, set by server actions):
- `x_studio_send_to_factory` — set by "Send to Factory" action
- `x_studio_receive_at_factory` — set by "Receive at Factory" action
- `x_studio_send_to_centre` — set by "Send to Sales Centre" action
- `x_studio_receive_at_centre` — set by "Receive at Sales Centre" action

**Factory transfer audit** (stored Datetime/Many2one, set by server actions):
- `x_studio_s_shipped_date/by` — when centre shipped to factory
- `x_studio_s_received_date/by` — when centre received back from factory
- `x_studio_f_shipped_date/by` — when factory shipped back to centre
- `x_studio_f_received_date/by` — when factory received from centre

**Stage tracking** (stored):
- `x_studio_stage_date` — Datetime — last stage transition timestamp
- `x_studio_stage_name` — Char — related field from `stage_id.name`, stored (enables domain filtering)

**Stage transition guard flags** (stored booleans, prevent re-fire of computed stage advances):
- `x_studio_invoice_stage_updated`
- `x_studio_repair_complete_stage_updated`
- `x_studio_estimation_sent_stage_updated`
- `x_studio_estimation_approved_stage_updated`
- `x_studio_repair_started_stage_updated`

**Cancel / reopen** (mix of stored):
- `x_studio_cancelled` — Boolean — primary cancelled flag
- `x_studio_cancelled_2` — Boolean — secondary cancel (from Estimation Sent stage)
- `x_studio_cancelled_by` — Many2one `res.users`
- `x_studio_cancelled_date` — Datetime
- `x_studio_cancelled_stage_id` — Many2one `helpdesk.stage` — stage to restore on reopen
- `x_studio_cancel_reason` — Text
- `x_studio_cancel_status` — Selection `[None, Cancelled]`
- `x_studio_reopened` — Boolean
- `x_studio_reopened_by` — Many2one `res.users`
- `x_studio_reopened_date` — Datetime
- `x_studio_reopen_status` — Selection `[None, Reopened]`

**Repair reason** (stored Many2many):
- `x_studio_repair_reason` — Many2many `x_repair_reason_custom`

**SO / financial** (mix of computed/stored):
- `x_studio_sale_order` — Many2one `sale.order` — computed from fsm_task linked SOs, not stored
- `x_studio_balance_due` — Float — stored
- `x_studio_items` — Many2many `product.product` — populated at Repair Completed from SO lines
- `x_studio_qty` — Char — JSON-like string of quantities from SO lines
- `x_studio_sales_price` — Char — JSON-like string of prices from SO lines
- `x_studio_unit_price` — Char — computed, always False (placeholder)
- `x_studio_materials_used` — Many2one `product.product`
- `x_studio_quantity` — Float

**Computed status flags** (not stored unless noted, all computed from fsm_task_ids and SO state):
- `x_studio_valid_return` — True if any linked picking is not cancelled
- `x_studio_valid_confirm_return` — True if any linked picking is done
- `x_studio_task_status` — True when FSM task done or SO fully delivered; side-effect: advances stage to Repair Completed (stored guard `x_studio_repair_complete_stage_updated`)
- `x_studio_fsm_task_done` — True when FSM task `fsm_done` or `x_studio_end_quick_repair`
- `x_studio_fully_paid_so` — True when FSM task `x_studio_fully_invoiced_so` or quick repair
- `x_studio_material_availability` — Selection from FSM task
- `x_studio_valid_invoiced_so` — True when SO is invoiced (non-credit); side-effect: advances to Advance Received
- `x_studio_valid_confirmed_so` — True when SO confirmed level 1; side-effect: advances to Estimation Sent
- `x_studio_valid_confirmed2_so` — True when SO confirmed level 2; side-effect: advances to Estimation Approval Received
- `x_studio_valid_delivered_so` — True when SO materials delivered; side-effect: advances to Repair Started then Repair Completed
- `x_studio_re_estimate_count` — Integer from SO
- `x_studio_re_estimate_status` — Selection
- `x_studio_handed_over` — True when 2+ pickings done; side-effect: advances to Handed Over to Customer

**User location validation** (computed, not stored):
- `x_studio_user_location_validation` — True when the current user is NOT in the `x_studio_users_stock_location` list of the receipt location (gate for location-restricted operations)

**Cancel stage gates** (computed, not stored):
- `x_studio_cancel_stage_ok` — True when `stage_id.name in {'New', 'Diagnosis', 'Sent to Factory', 'Received at Factory'}`
- `x_studio_cancel2_stage_ok` — True when `stage_id.name == 'Estimation Sent to Customer'`

**Misc** (stored):
- `x_studio_warranty_card` — Binary (image) — required for RUG Confirmed
- `x_studio_related_information` — Binary (image)
- `x_studio_driver_name` — Char — delivery driver
- `x_studio_vehicle_details` — Char — delivery vehicle
- `x_studio_sales_price_field` — Char (duplicate of `x_studio_sales_price`, legacy)
- `x_studio_quick_repair_status` — Selection `[None, Quick Repair/Tested OK]`

**Stage transition audit log** (10 pairs, stored):
- `x_studio_created_by_1` / `x_studio_created_on_1` — Sent to Factory
- `x_studio_created_by_2` / `x_studio_created_on_2` — Received at Factory
- `x_studio_created_by_3` / `x_studio_created_on_3` — (reserved)
- `x_studio_created_by_4` / `x_studio_created_on_4` — Estimation Sent to Customer
- `x_studio_created_by_5` / `x_studio_created_on_5` — Estimation Approval Received
- `x_studio_created_by_6` / `x_studio_created_on_6` — Advance Received
- `x_studio_created_by_7` / `x_studio_created_on_7` — Repair Started
- `x_studio_created_by_8` / `x_studio_created_on_8` — Repair Completed
- `x_studio_created_by_9` / `x_studio_created_on_9` — Sent to Sales Centre
- `x_studio_created_by_10` / `x_studio_created_on_10` — Received at Sales Centre

**Stat button count** (computed):
- `x_x_studio_created_from_help_ticket_stock_picking_count` — Integer — count of `stock.picking` records where `x_studio_created_from_help_ticket = self.id`

### 2.2 `helpdesk.ticket.type` (extended in `models/helpdesk_ticket_type.py`)

- `x_studio_rug` — Boolean — ticket type is a RUG (warranty) type
- `x_studio_rug_confirmed` — Boolean — warranty is confirmed (sub-flag of `x_studio_rug`)
- `x_studio_with_serial_no` — Boolean — serial number required
- `x_studio_without_serial_no` — Boolean — no serial number (mutually exclusive with above)
- `x_studio_company_id` — Many2one `res.company` — company scope

### 2.3 `x_repair_reason_custom` (new model in `models/repair_reason_custom.py`)

- `_name = 'x_repair_reason_custom'`
- `_description = 'Repair Reason'`
- `_order = 'x_studio_sequence, id'`
- `x_name` — Char — required
- `x_active` — Boolean — default True (supports archiving)
- `x_studio_sequence` — Integer — display order, default 10; handle widget in list
- `x_color` — Integer — colour index for many2many_tags widget; edited with color_picker widget
- `x_studio_company_id` — Many2one `res.company`

### 2.4 `stock.location` (extended in `models/stock_location.py`)

- `x_studio_repair_factory_location` — Boolean — marks the factory repair location
- `x_studio_repair_return_location` — Boolean — marks valid return receipt locations
- `x_studio_finished_good_location` — Boolean
- `x_studio_temp_location` — Boolean
- `x_studio_many2many_field_7kpUe` — Many2many `res.users` — cell visibility (legacy Studio name, cannot be renamed without data migration)
- `x_studio_users_stock_location` — Many2many `res.users` via `stock_location_users_rel` — stock location ownership
- `x_studio_users_internal_transfer` — Many2many `res.users` via `stock_location_internal_transfer_rel`
- `x_studio_return_receipt_location` — Many2one `stock.location`
- `x_studio_return_sequence` — Many2one `ir.sequence`
- `x_color` — Integer

### 2.5 `stock.picking` (extended in `models/stock_picking.py`)

- `x_studio_created_from_help_ticket` — Many2one `helpdesk.ticket`, ondelete='set null'
- `x_studio_helpdesk_ticket_id` — Many2one `helpdesk.ticket`, ondelete='set null'
- `x_studio_factory_repair` — Boolean

### 2.6 `repair.order` (stub in `models/repair_order.py`)

No additional fields. The file exists to allow future extension.

### 2.7 `helpdesk.team` (stub in `models/helpdesk_team.py`)

No additional fields. The file exists to allow future extension.

---

## 3. Automation Rules Design

All rules are owned by this module (external IDs prefixed `helpdesk_repair_custom.automation_*`).

### Rule 1: `automation_repair_seq` — RR - Repair Seq.No

- Model: `helpdesk.ticket`
- Trigger: `on_create`
- Action (pseudocode):
  ```
  if record.name is not empty:
      record.name = env['ir.sequence'].next_by_code('repair.seq')
  ```
- Effect: Replaces the default ticket name with a formatted sequence number on every new ticket.

### Rule 2: `automation_auto_product_from_serial` — RR - Auto Select Product for RUG Repairs

- Model: `helpdesk.ticket`
- Trigger: `on_change`
- Watched field: `ticket_type_id`
- Action (pseudocode):
  ```
  if record.x_studio_serial_no:
      company = active_company_from_context
      cust_location = first stock.location where usage == 'customer'
      trans_line = first stock.move.line where (
          product_id == serial.product_id AND
          lot_id == serial AND
          picking_code == 'outgoing' AND
          location_dest_id == cust_location AND
          company_id == company
      )
      if trans_line:
          so = first sale.order where name == trans_line.origin AND company_id == company
          if so:
              record.sale_order_id = so
              record.x_studio_picking_id = trans_line.picking_id
              record.x_studio_pick_id = trans_line.picking_id.id
      record.product_id = serial.product_id
      record.lot_id = serial
      if record.x_studio_normal_repair_without_serial_no:
          record.sale_order_id = False
  else:
      if record.x_studio_normal_repair_without_serial_no:
          clear: sale_order_id, picking_id, pick_id, lot_id
      else:
          clear: sale_order_id, picking_id, pick_id, product_id, lot_id
  ```
- Note: The trigger field `ticket_type_id` means this fires when the type is selected. The rule effectively re-evaluates the serial-to-SO lookup after the type is chosen, allowing the type selection to set the "without serial" flag first.

### Rule 3: `automation_clear_on_serial_change` — RR - Auto Select Product for RUG Repairs-33

- Model: `helpdesk.ticket`
- Trigger: `on_change`
- Watched field: (not specified in record — applies to any field change, effectively fires broadly)
- Action (pseudocode):
  ```
  record.sale_order_id = False
  record.x_studio_picking_id = False
  record.x_studio_pick_id = False
  record.product_id = False
  record.lot_id = False
  record.x_studio_sn_updated = False
  ```
- Note: This is the "clear before re-populate" rule. It fires before Rule 2 to ensure stale data is wiped. The lack of a specific `on_change_field_ids` means it may fire more broadly than intended — this is a known side-effect of the Studio origin.

### Rule 4: `automation_populate_repair_location` — RR - Auto Populate Repair Location

- Model: `helpdesk.ticket`
- Trigger: `on_change`
- Watched field: (not specified in record)
- Action (pseudocode):
  ```
  if record.x_studio_return_receipt_location:
      record.x_studio_repair_location = record.x_studio_return_receipt_location
  else:
      record.x_studio_repair_location = False
  ```
- Effect: Keeps the repair location in sync with the receipt location for non-factory repairs.

### Rule 5: `automation_validate_cancelled_delete` — RR - Validate Cancelled Tickets

- Model: `helpdesk.ticket`
- Trigger: `on_unlink`
- Filter domain: `[["x_studio_cancelled","=",True]]`
- Action (pseudocode):
  ```
  if record.x_studio_cancelled:
      raise UserError('Cancelled tickets can not be deleted.')
  ```
- Effect: Prevents permanent deletion of cancelled tickets, preserving audit history.

### Rule 6: `automation_stage_company` — JIN - Company Id in Helpdesk Stage

- Model: `helpdesk.stage` (not `helpdesk.ticket`)
- Trigger: `on_create`
- Action (pseudocode):
  ```
  company = first id from allowed_company_ids context, fallback to user company
  record.x_studio_company_id = company
  ```
- Effect: Every new helpdesk stage created in the UI is automatically tagged with the current user's active company.

---

## 4. Server Actions (Button Actions)

Defined in `data/server_actions.xml` as `ir.actions.server` with `binding_model_id` set so they appear as button actions.

### `action_create_repair_route` — RR - Auto Create Repair Route

Used by: "Create Repair Route" button (Normal Without Serial No, product tracking = none)

Pseudocode:
```
validate virtual_location and source_location are set (company-branched)
record.x_studio_repair_serial_created = True
find customer stock.location
find outgoing picking.type from return receipt location
create stock.picking (done state) from source_loc to customer
create stock.move + stock.move.line (qty=1, done)
mark picking state='done'
record.x_studio_picking_id = picking.id
record.x_studio_pick_id = picking.id
```

### `action_create_repair_serial` — RR - Auto Create Repair Serial Nos

Used by: "Create Repair Serial" button (Normal Without Serial No, product tracking = serial)

Pseudocode:
```
validate virtual_location and source_location are set (company-branched)
seq = next_by_code('repair.serial.seq')
create stock.production.lot with seq name, record.product_id, company
record.x_studio_serial_no = new lot
record.lot_id = new lot
record.x_studio_repair_serial_created = True
create stock.picking (done) + stock.move + stock.move.line with lot_id
record.x_studio_picking_id = picking.id
```

### `action_send_to_factory` — RR - Send to Factory

Pseudocode:
```
find stock.location where x_studio_repair_factory_location = True (raise if not found)
record.x_studio_repair_location = factory_location
record.x_studio_send_to_factory = True
record.x_studio_s_shipped_date = now
record.x_studio_s_shipped_by = current_user
find stage 'Sent to Factory' (team-scoped first, then global)
record.stage_id = found stage
record.x_studio_stage_date = now
record.x_studio_created_by_1 = current_user
record.x_studio_created_on_1 = now
```

### `action_receive_at_factory` — RR - Receive at Factory

Pseudocode:
```
record.x_studio_receive_at_factory = True
record.x_studio_f_received_date = now
record.x_studio_f_received_by = current_user
find stage 'Received at Factory' and advance
record.x_studio_created_by_2 / created_on_2 = now/user
```

### `action_send_to_sales_centre` — RR - Send to Sales Centre

Pseudocode:
```
record.x_studio_send_to_centre = True
record.x_studio_f_shipped_date = now
record.x_studio_f_shipped_by = current_user
find stage 'Sent to Sales Centre' and advance
record.x_studio_created_by_9 / created_on_9 = now/user
```

### `action_receive_at_sales_centre` — RR - Receive at Sales Centre

Pseudocode:
```
record.x_studio_receive_at_centre = True
record.x_studio_s_received_date = now
record.x_studio_s_received_by = current_user
find stage 'Received at Sales Centre' and advance
record.x_studio_created_by_10 / created_on_10 = now/user
```

### `action_change_type_to_rug` — RR - Change Repair Type to RUG

Pseudocode:
```
if warranty card not uploaded: raise UserError
for each FSM task:
    so = linked sale.order
    for each SO line:
        save original price_unit to x_studio_price_unit_original
        set price_unit = product standard_price
find ticket.type where x_studio_rug=True AND x_studio_rug_confirmed=True
record.ticket_type_id = that type
```

### `action_cancel_repair` — RR - Cancel Repair (primary path)

Pseudocode:
```
if cancel reason is empty: raise UserError
save current stage to x_studio_cancelled_stage_id
find stage 'Cancelled' (team-scoped first)
record.stage_id = Cancelled stage
record.x_studio_cancelled = True
record.x_studio_reopened = False
record.x_studio_cancelled_by = current_user
record.x_studio_cancelled_date = now
record.x_studio_cancel_status = 'Cancelled'
```

### `action_reopen_repair` — RR - Reopen Repair

Pseudocode:
```
record.stage_id = x_studio_cancelled_stage_id (restore)
record.x_studio_cancelled = False
record.x_studio_reopened = True
record.x_studio_cancelled_stage_id = False
record.x_studio_reopened_by = current_user
record.x_studio_reopened_date = now
record.x_studio_reopen_status = 'Reopened'
```

### `action_cancel_repair_2` — RR - Cancel Repair-2 (Estimation Sent path)

Pseudocode:
```
if cancel reason is empty: raise UserError
record.x_studio_repair_complete_stage_updated = True
find stage 'Repair Completed' and advance
record.x_studio_cancelled_2 = True
record.x_studio_cancel_status = 'Cancelled'
(does NOT set x_studio_cancelled)
```

### `action_update_serial` — RR - Auto Select Product for RUG Repairs-22

Same lookup logic as automation Rule 2 but bound to the "Update Serial" button and also sets `record.x_studio_sn_updated = True` unconditionally at the end.

---

## 5. View Architecture

### 5.1 `helpdesk_ticket_views.xml` — Three View Records

**Record 1: `helpdesk_ticket_view_form_repair_trans`** (priority 99)
- Inherits: `helpdesk.helpdesk_ticket_view_form`
- Adds the "Repair Trans." stat button after the FSM task button
- Stat button: shows `x_x_studio_created_from_help_ticket_stock_picking_count`, launches `action_repair_trans`

**Record 2: `helpdesk_ticket_view_form_studio_main`** (priority 99)
- Inherits: `helpdesk.helpdesk_ticket_view_form`
- Major structural additions via XPath:
  - Ticket name: forced read-only, placeholder "New"
  - Stage bar: `clickable: False` (controlled by buttons only)
  - `team_id`, `user_id`, `ticket_type_id`, `partner_id`: conditionally read-only when RUG flow started
  - After `ticket_type_id`: repair type indicator booleans + receipt location + repair location + job location
  - After `company_id`: invisible computed/status fields (force_save, read-only)
  - After `email_cc`: `x_studio_serial_number` + moved `sale_order_id`
  - `product_id`: modified attrs (readonly when serial-tracked type; required for without-serial)
  - After `product_id`: factory routing flags, validity booleans, tracking, location fields (mostly invisible)
  - After `lot_id`: `x_studio_serial_no` field
  - After main sheet group: "Factory Repair Details" notebook tab (visible only when Factory Repair)
  - After `description`: `x_studio_repair_reason` (many2many_tags) + `x_studio_cancel_reason`
  - After `sla_deadline`: invisible status/audit fields
  - Inside first notebook page group: "Delivery Details" sub-group (driver name, vehicle)
  - Inside second notebook: "Warranty Details" page (hidden for without-serial) with warranty card images
  - Inside second notebook: "Cancel / Reopen Log" page with audit fields

**Record 3: `helpdesk_ticket_view_form_studio_buttons`** (priority 50000)
- Inherits: `helpdesk.helpdesk_ticket_view_form`
- High priority (50000) ensures button modifications are applied last, overriding any other inheritance
- Modifies visibility of existing buttons:
  - Repair Order button: hidden if cancelled or no pickings or repairs disabled
  - Receipt button (base): restricted to specific repair types and states
- Adds new header buttons in order (all are `type="action"` pointing to server actions):
  1. "Change Repair Type To RUG" — before `assign_ticket_to_self`
  2. "Receipt" (first instance, RUG/with-serial) — after `assign_ticket_to_self`
  3. "Receipt" (second instance, without-serial normal) — after first Receipt
  4. "Create Repair Route" — before Create Repair Serial
  5. "Create Repair Serial" — before third Receipt
  6. "Receipt" (third instance, without-serial after serial created)
  7. "Update Serial" — before Receipt
  8. "Send to Factory" — before `action_generate_fsm_task`
  9. "Receive at Factory" — after Send to Factory
  10. "Send to Sales Centre" — before Receive at Factory
  11. "Receive at Sales Centre" — after Send to Sales Centre
  12. "Cancel" (path 2) — before Reopen
  13. "Reopen" — before Cancel
  14. "Cancel" (primary) — before Receive at Sales Centre

### 5.2 `helpdesk_ticket_type_views.xml`

- Single form view for `helpdesk.ticket.type` (not inheriting, replacing or overriding Studio-created view)
- Fields: `name`, `x_studio_rug`, `x_studio_rug_confirmed` (visible only when RUG=True), `x_studio_with_serial_no`, `x_studio_without_serial_no`

### 5.3 `repair_reason_custom_views.xml`

- List view: handle widget on sequence, name, active columns
- Form view: name, active, sequence, color_picker for `x_color`
- Window action: tree+form
- Menu item: "Repair Reasons" under Helpdesk root, visible only to `helpdesk.group_helpdesk_manager`, sequence 50

---

## 6. Security Matrix

### 6.1 Model Access Control (`ir_model_access.xml`)

| Rule ID | Model | Group | Read | Write | Create | Delete |
|---|---|---|---|---|---|---|
| `access_repair_reason_custom_user` | `x_repair_reason_custom` | `base.group_user` | Yes | No | No | No |
| `access_repair_reason_custom_manager` | `x_repair_reason_custom` | `helpdesk.group_helpdesk_manager` | Yes | Yes | Yes | Yes |

Note: The `model_id` is resolved by `search="[('model','=','x_repair_reason_custom')]"` rather than by external ID. This is because the model was originally created by Studio and has a UUID-based external ID that is not portable across database instances.

### 6.2 Field-Level Access

No explicit `ir.rule` record rules are defined in this module. Access to `helpdesk.ticket` records is governed by the base `helpdesk` module rules (team membership, assigned user).

### 6.3 Button Visibility (functional security)

Buttons are shown/hidden using `attrs` expressions based on field values, not OWL access rights. This is a UI-layer guard only; the underlying server actions do not perform explicit user group checks beyond Odoo's standard `binding_model_id` mechanism.

### 6.4 Repair Reasons Menu

Accessible only to `helpdesk.group_helpdesk_manager` via the menu `groups=` attribute.

---

## 7. Stage Gate Logic

### 7.1 Name-Based Stage Resolution

All stage lookups (in server actions and computed methods) use the helper `_get_stage_by_name`:

```python
def _get_stage_by_name(self, name):
    stage = self.env['helpdesk.stage'].search(
        [('name', '=', name), ('team_ids', 'in', self.team_id.id)], limit=1)
    if not stage:
        stage = self.env['helpdesk.stage'].search([('name', '=', name)], limit=1)
    return stage.id if stage else False
```

Rationale: Stage IDs are not stable across Odoo installations (new database = new IDs). Using stage names (which are consistent by business convention) makes the module portable. Team-scoped search is attempted first to support multi-team / multi-company setups where the same stage name may exist per team.

### 7.2 Cancel Button Gate

```python
_CANCEL_STAGE_NAMES = frozenset({'New', 'Diagnosis', 'Sent to Factory', 'Received at Factory'})
_CANCEL2_STAGE_NAMES = frozenset({'Estimation Sent to Customer'})

def _compute_x_studio_cancel_stage_ok(self):
    for rec in self:
        rec.x_studio_cancel_stage_ok = rec.stage_id.name in self._CANCEL_STAGE_NAMES

def _compute_x_studio_cancel2_stage_ok(self):
    for rec in self:
        rec.x_studio_cancel2_stage_ok = rec.stage_id.name in self._CANCEL2_STAGE_NAMES
```

These computed fields are surfaced as invisible fields in the view and used in `attrs` expressions on the Cancel buttons. This pattern avoids hardcoded stage IDs in the XML.

### 7.3 Side-Effect Computed Methods

Several computed methods (`_compute_x_studio_task_status`, `_compute_x_studio_valid_invoiced_so`, etc.) perform `write()` calls on `self` inside the compute loop. This is an intentional (though non-standard) pattern carried over from Studio automation rules, enabling automatic stage advancement when the form is opened or saved. Guard boolean fields prevent the write from firing more than once.

---

## 8. Multi-Company Portability

### 8.1 Known Hard-Coded Workaround

The "Create Repair Route" and "Create Repair Serial" server actions contain an explicit `if company.id == 1:` branch to select between `x_studio_virtual_location` / `x_studio_source_location` (company 1) and `x_studio_virtual_location_1` / `x_studio_source_location_1` (all other companies). This is a technical debt item. A proper solution would use a per-company configuration model or use the user's default locations.

### 8.2 Stage Company Stamping

The `automation_stage_company` rule fires on new `helpdesk.stage` creation and stamps the active company ID. This supports per-company stage filtering.

### 8.3 Sequence Company Scoping

Sequences `repair.seq` and `repair.serial.seq` are created with `company_id = base.main_company`. Separate sequences must be created manually (or via data fixture) for additional companies.

### 8.4 post_init_hook

On module install, the hook deactivates any pre-existing Studio automation rules with matching names (from the original Studio export). This ensures clean migration from Studio-only to module-based deployment without duplicate rule execution.

---

## 9. Known Technical Constraints and Workarounds

| Constraint | Workaround Applied |
|---|---|
| Stage IDs not portable across installs | Name-based stage lookup with `_get_stage_by_name` |
| `x_repair_reason_custom` has Studio UUID as external ID | `ir_model_access.xml` uses `search=` attribute instead of `ref=` |
| Multi-company virtual location branching | Hard-coded `company.id == 1` branch in two server actions |
| `x_studio_many2many_field_7kpUe` legacy field name | Cannot be renamed without data migration; documented but preserved |
| Computed methods with side-effects (write in compute) | Guard boolean flags prevent repeated firing; this pattern is not ORM-compliant but is stable for Odoo 15 |
| `on_change` automation rules without explicit field list | Rules fire on any field change; ordering between rules 2, 3, 4 is not strictly guaranteed |
| `x_studio_pick_id` is Integer not Many2one | Required because the Receipt button context passes it as a default value to a wizard that expects an integer; converting to Many2one would require changing the wizard context |
| Stage bar is non-clickable | Enforced by `options: {'clickable': False}` in view — all stage transitions must go through header buttons to maintain audit trail integrity |
