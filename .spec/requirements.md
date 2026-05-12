# RepairDesk — Business Requirements

Module: `helpdesk_repair_custom`
Odoo version: 15.0
Status: Installed and live (as of 2026-05-08)

---

## 1. Purpose and Scope

RepairDesk extends the Odoo Helpdesk module to manage the full lifecycle of appliance and device repair jobs, including warranty claims (RUG), normal repairs with or without a serial number, and the extended factory-repair logistics route. The system is operated by a multi-branch service organisation where a Sales Centre team raises and tracks tickets while a separate Factory team handles bench repairs.

---

## 2. User Roles

| Role | Odoo Group | Primary Responsibilities |
|---|---|---|
| Service Agent | `helpdesk.group_helpdesk_user` | Create tickets, perform receipts, advance stage, cancel/reopen |
| Service Manager | `helpdesk.group_helpdesk_manager` | All agent actions + manage ticket types, repair reasons, team config |
| Technician (Factory) | `helpdesk.group_helpdesk_user` (factory team) | Receive at factory, log repair progress, send back to centre |
| Customer Care | `helpdesk.group_helpdesk_user` | View ticket status, confirm customer delivery |
| Stock User | `stock.group_stock_user` | Access receipt/picking buttons on the ticket form |
| System Admin | `base.group_system` | Configure locations, sequences, automation rules |

---

## 3. Repair Type Classification

Every repair ticket is classified along two independent dimensions:

### 3.1 Repair Type (set via Ticket Type record)

| Type | `x_studio_rug` | `x_studio_rug_confirmed` | `x_studio_with_serial_no` | `x_studio_without_serial_no` |
|---|---|---|---|---|
| RUG Confirmed (warranty approved) | True | True | True | False |
| RUG Not Confirmed (warranty pending) | True | False | True | False |
| Normal Repair — With Serial No | False | False | True | False |
| Normal Repair — Without Serial No | False | False | False | True |

When a ticket type is selected, four boolean flags are copied onto the ticket (`x_studio_rug_repair`, `x_studio_rug_confirmed`, `x_studio_normal_repair_with_serial_no`, `x_studio_normal_repair_without_serial_no`) via an on_change automation rule. These flags drive field visibility, mandatory validation, and button availability throughout the form.

### 3.2 Job Location (set manually on ticket)

| Value | Description |
|---|---|
| Centre Repair | Device is diagnosed and repaired entirely at the sales centre |
| Factory Repair | Device is shipped to the manufacturer/factory for repair; extended 4-step logistics route |

---

## 4. User Stories by Repair Flow

### Flow 1 — RUG Confirmed, Centre Repair

**As a Service Agent**, when a customer brings in a device for a confirmed warranty repair:
- I can create a ticket and select the "RUG Confirmed" ticket type.
- The system requires me to enter the device serial number and upload the warranty card document.
- The system automatically looks up the original sale order for that serial number from stock move history and populates the product, lot, and SO on the ticket.
- I click "Update Serial" to confirm the serial, then "Receipt" to record the physical intake of the device.
- The system creates a stock picking from the return receipt location.
- I set Job Location to "Centre Repair" and create the FSM task (work order) for the technician.
- After the technician marks the task done, the ticket automatically advances to "Repair Completed".
- I click "Deliver" / confirm handover; the ticket advances to "Handed Over to Customer".

### Flow 2 — RUG Confirmed, Factory Repair

**As a Service Agent**, when a warranty device must go to the factory:
- I follow steps 1–5 from Flow 1, but set Job Location to "Factory Repair".
- I click "Send to Factory": the system stamps shipped date/by, sets repair location to the factory stock location, and advances the stage to "Sent to Factory".
- A factory technician clicks "Receive at Factory": the system stamps received date/by and advances to "Received at Factory".
- The technician creates the FSM task and completes the repair.
- The factory technician clicks "Send to Sales Centre": stamps shipped date/by from factory side, advances to "Sent to Sales Centre".
- The Service Agent clicks "Receive at Sales Centre": stamps received date/by from centre side, advances to "Received at Sales Centre".
- Normal delivery follows.

### Flow 3 — RUG Not Confirmed, Centre Repair

**As a Service Agent**, when the warranty status is not yet confirmed:
- I create a ticket with "RUG Not Confirmed" type and enter the serial number.
- The system populates the product and lot but does NOT automatically populate the sale order (pending warranty confirmation).
- After the diagnosis, if the factory approves the warranty claim (RUG approval received on the linked sale order), the `x_studio_rug_approval_status` computed field reflects "RUG Approved".
- The ticket may subsequently be changed to "RUG Confirmed" type using the "Change Repair Type To RUG" button (requires warranty card upload).

### Flow 4 — RUG Not Confirmed, Factory Repair

Same as Flow 3, combined with the factory logistics steps from Flow 2.

### Flow 5 — Normal Repair With Serial No, Centre Repair

**As a Service Agent**, when a customer brings a non-warranty device with a known serial:
- I select the "Normal Repair — With Serial No" ticket type.
- Serial number entry is required; the system looks up the sale order from stock history.
- "Update Serial" confirms the serial and re-populates product/lot.
- I perform "Receipt" to intake the device.
- The repair proceeds through Diagnosis → Estimation → Approval → Repair in Progress → Repair Completed.
- Stage transitions are driven by FSM task and sale order status (estimated, approved, delivered).

### Flow 6 — Normal Repair Without Serial No, Centre Repair

**As a Service Agent**, when a device has no readable serial number:
- I select "Normal Repair — Without Serial No" type.
- Serial number field is hidden; sale order reference is not required.
- I click "Create Repair Serial" to generate a system serial number (REP-SERIAL/YYYY/NNNNN) and auto-create the stock picking.
- Alternatively, I click "Create Repair Route" if the product uses no serial tracking.
- The repair proceeds as in Flow 5.

### Flow 7 — Quick Repair (fast-track)

**As a Service Agent**, when a device is tested-OK and returned immediately:
- The FSM task is marked with `x_studio_end_quick_repair = True` (set on the task).
- The computed fields `x_studio_fsm_task_done` and `x_studio_fully_paid_so` immediately reflect True.
- The ticket advances to "Repair Completed" without waiting for a full SO lifecycle.
- `x_studio_quick_repair_status` is set to "Tested OK" (stored on ticket).

---

## 5. Ticket Lifecycle

### 5.1 Full Stage Pipeline

```
New
 └─> Diagnosis
      └─> Estimation Sent to Customer
           ├─> [Cancel path 2: moves to Repair Completed with cancelled_2 flag]
           └─> Estimation Approval Received
                └─> Advance Received
                     └─> Repair Started
                          └─> [Factory Repair branch]
                               └─> Sent to Factory
                                    └─> Received at Factory
                                         └─> [Repair in Progress — FSM task]
                                              └─> Sent to Sales Centre
                                                   └─> Received at Sales Centre
                                                        └─> Repair Completed
                          └─> [Centre Repair branch]
                               └─> Repair in Progress (FSM task)
                                    └─> Repair Completed
                                         └─> Handed Over to Customer (Ready for Delivery)
                                              └─> Delivered / Closed

Cancelled (from: New, Diagnosis, Sent to Factory, Received at Factory)
```

### 5.2 Automatic Stage Transitions

The following transitions happen automatically via computed fields evaluated on every form open/save:

| Trigger | Destination Stage | Guard Flag |
|---|---|---|
| FSM task confirmed (SO delivered or task done) | Repair Completed | `x_studio_repair_complete_stage_updated` prevents re-fire |
| SO sent to customer (SO confirmed) | Estimation Sent to Customer | `x_studio_estimation_sent_stage_updated` |
| Customer approves estimate (SO confirmed level 2) | Estimation Approval Received | `x_studio_estimation_approved_stage_updated` |
| Advance/invoice received (non-credit SO invoiced) | Advance Received | `x_studio_invoice_stage_updated` |
| SO materials delivered (first delivery done) | Repair Started | `x_studio_repair_started_stage_updated` |
| More than 1 stock picking done | Handed Over to Customer | — |

### 5.3 Manual Stage Transitions (buttons)

| Button | Stage Reached | Available When |
|---|---|---|
| Send to Factory | Sent to Factory | Factory Repair, receipt done, not already sent |
| Receive at Factory | Received at Factory | Factory Repair, sent, not yet received |
| Send to Sales Centre | Sent to Sales Centre | Factory Repair, FSM task done, received at factory, not already sent back |
| Receive at Sales Centre | Received at Sales Centre | Factory Repair, sent to centre, not yet received |
| Cancel | Cancelled | Stage in: New, Diagnosis, Sent to Factory, Received at Factory |
| Cancel (path 2) | Repair Completed + cancelled_2=True | Stage = Estimation Sent to Customer |
| Reopen | Restores pre-cancel stage | Ticket is cancelled |

---

## 6. Ticket Number / Sequence

- On ticket creation, the automation rule `RR - Repair Seq.No` replaces the default name with a value from the `repair.seq` sequence.
- Format: `REPAIR/YYYY/NNNNN` (prefix year + 5-digit zero-padded counter, starting at 2000).
- The sequence is per-company; Company 1 is pre-seeded.
- For Normal Repair Without Serial No, a repair serial sequence `repair.serial.seq` generates `REP-SERIAL/YYYY/NNNNN`.
- The ticket name field is rendered read-only in the form view.

---

## 7. Serial Number Tracking

- `x_studio_serial_no` (Many2one `stock.production.lot`) is the primary serial link.
- `x_studio_serial_number` is an alternate display field also linked to `stock.production.lot` (surfaced in the main ticket group).
- On ticket type selection (on_change): if a serial is already set and the type has a serial requirement, the system looks up the original sale order via `stock.move.line` (outgoing moves to customer location, matching product and lot).
- When the serial changes (on_change on `x_studio_serial_no`): product, lot, sale order, and picking references are cleared; `x_studio_sn_updated` is reset to False.
- "Update Serial" button: re-runs the sale order lookup without clearing; sets `x_studio_sn_updated = True`. Available until the serial is confirmed.
- `x_studio_tracking` (computed, not stored) reflects the product's tracking mode (`serial`, `lot`, `none`) for form visibility control.
- Serial required for: RUG Confirmed, RUG Not Confirmed, Normal With Serial No.
- Serial hidden for: Normal Without Serial No.

---

## 8. RUG Warranty Approval Flow

1. Agent creates ticket with RUG type and enters serial number; system links original SO.
2. Agent uploads warranty card (required for RUG Confirmed; also checked by "Change Repair Type To RUG").
3. A request is sent to the warranty approver (tracked by `x_studio_rug_request_sent = True`).
4. The approver records the decision on the linked sale order (`x_studio_rug_approved` or `x_studio_rug_rejected` field on `sale.order`).
5. The computed field `x_studio_rug_approval_status` reflects the status (Pending / RUG Approved / RUG Rejected).
6. Once RUG is approved or a request is sent, the following fields become read-only: `team_id`, `user_id`, `ticket_type_id`, `partner_id`, `x_studio_return_receipt_location`.
7. For RUG Confirmed repairs, the "Change Repair Type To RUG" button (from Normal With Serial No) zeroes out SO line prices (replacing with standard cost) and switches the ticket type to the RUG Confirmed type.

---

## 9. Factory Repair Logistics

For tickets with `x_studio_job_location = 'Factory Repair'`, the following additional steps are enforced:

1. "Send to Factory" button sets `x_studio_send_to_factory = True`, records `x_studio_s_shipped_date` and `x_studio_s_shipped_by`, finds a stock location flagged as `x_studio_repair_factory_location`, and updates `x_studio_repair_location` accordingly.
2. "Receive at Factory" button sets `x_studio_receive_at_factory = True`, records `x_studio_f_received_date` and `x_studio_f_received_by`.
3. FSM task creation is blocked until `x_studio_receive_at_factory = True`.
4. "Send to Sales Centre" (after FSM task is done) sets `x_studio_send_to_centre = True`, records `x_studio_f_shipped_date` and `x_studio_f_shipped_by`.
5. "Receive at Sales Centre" sets `x_studio_receive_at_centre = True`, records `x_studio_s_received_date` and `x_studio_s_received_by`.
6. All factory logistics audit fields are rendered read-only in the "Factory Repair Details" notebook tab, visible only when Job Location = Factory Repair.

---

## 10. Cancel / Reopen Workflow

### 10.1 Primary Cancel Path (stages: New, Diagnosis, Sent to Factory, Received at Factory)
- "Cancel" button is shown when `x_studio_cancel_stage_ok = True` (stage name in the `_CANCEL_STAGE_NAMES` set).
- A cancel reason (`x_studio_cancel_reason`) must be provided before cancellation is allowed.
- On cancel: current stage is saved to `x_studio_cancelled_stage_id`; ticket moves to the "Cancelled" stage; `x_studio_cancelled = True`; `x_studio_cancelled_by` and `x_studio_cancelled_date` are stamped.
- Cancelled tickets cannot be deleted (automation rule raises `UserError` on unlink).

### 10.2 Secondary Cancel Path (stage: Estimation Sent to Customer)
- "Cancel" button variant shown when `x_studio_cancel2_stage_ok = True` (stage name = "Estimation Sent to Customer").
- On cancel: `x_studio_cancelled_2 = True`; `x_studio_repair_complete_stage_updated = True`; ticket moves to "Repair Completed" (not "Cancelled" stage).
- This path does NOT set `x_studio_cancelled`, so the primary Reopen button does not apply.

### 10.3 Reopen Path
- "Reopen" button is visible when `x_studio_cancelled = True`.
- On reopen: stage is restored from `x_studio_cancelled_stage_id`; `x_studio_cancelled = False`; `x_studio_reopened = True`; `x_studio_reopened_by` and `x_studio_reopened_date` are stamped; `x_studio_cancelled_stage_id` is cleared.
- Cancel/Reopen history is visible in the "Cancel / Reopen Log" notebook tab.

---

## 11. Repair Reason Codes

- A dedicated master data model `x_repair_reason_custom` holds customer-visible repair reason descriptions.
- Each reason has: name (`x_name`), active flag (`x_active`), display sequence (`x_studio_sequence`), colour code (`x_color`), and optional company (`x_studio_company_id`).
- A ticket can have multiple reasons (Many2many); displayed as colour-coded tags in the form.
- Repair reason is required once a user is assigned to the ticket.
- Repair reason is read-only once the stage has moved past "New" or when the ticket is cancelled.
- Managers maintain reason codes via a dedicated menu under Helpdesk Configuration.
- 10 seed records are provided (pump/motor failure codes).

---

## 12. Multi-Company / Multi-Branch Requirements

- The module is installed in a multi-company Odoo database with at least two companies (main company id=1, and at least one branch/subsidiary).
- Sequences (`repair.seq`, `repair.serial.seq`) are scoped to company 1 and must be replicated for each additional company.
- The "Create Repair Route" and "Create Repair Serial" server actions branch on `company.id == 1` to select `x_studio_virtual_location` vs `x_studio_virtual_location_1` and `x_studio_source_location` vs `x_studio_source_location_1`. This is a known hard-coded workaround (see design.md).
- The automation rule `JIN - Company Id in Helpdesk Stage` stamps the active company on every new helpdesk stage record.
- Ticket type records carry `x_studio_company_id` for filtering.
- The `post_init_hook` deactivates superseded Studio automation rules safely across all companies on fresh install.

---

## 13. Stock Location Configuration Requirements

The following custom flags on `stock.location` are required by the system and must be configured by the System Admin before tickets can be processed:

| Field | Purpose |
|---|---|
| `x_studio_repair_factory_location` | Marks the factory repair stock location (used by "Send to Factory") |
| `x_studio_repair_return_location` | Marks valid return/receipt locations |
| `x_studio_many2many_field_7kpUe` | Users allowed to see a given location cell in the kanban |
| `x_studio_users_stock_location` | Users assigned to a stock location (used in user location validation) |
| `x_studio_users_internal_transfer` | Users permitted to perform internal transfers from a location |

---

## 14. Reporting and Visibility Needs

- The kanban view is inherited from the standard Helpdesk kanban; stage columns reflect the full pipeline.
- The "Repair Trans." stat button (smart button) on the ticket form shows the count of stock pickings linked to the ticket via `x_studio_created_from_help_ticket`.
- Clicking it opens the linked stock pickings in tree/form.
- The "Factory Repair Details" notebook tab shows all four transfer audit fields (shipped/received date and by for both centre and factory sides) for factory-routed tickets.
- The "Cancel / Reopen Log" notebook tab is always visible and shows who cancelled or reopened the ticket and when.
- The "Warranty Details" tab (hidden for Normal Without Serial No) holds warranty card and related document images.
- Stage transition audit is tracked via 10 pairs of `x_studio_created_by_N` / `x_studio_created_on_N` fields (one pair per significant stage transition).
- The `x_studio_stage_date` field records the datetime of the last stage transition.
- Service Managers can view and administer Repair Reason codes from the Helpdesk menu.
