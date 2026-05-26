# Session Log: 26-05-2026 07:58 - project-task-repair-tabs

## Quick Reference (for AI scanning)
**Confidence keywords:** helpdesk_repair_custom, project.task, x_studio_dispatch_done, CacheMiss, UndefinedColumn, x_task_diagnosis, Repair Image, Warranty Details, Repair Diagnosis, x_studio_repair_image_01, x_studio_warranty_card, x_studio_diagnosis_ids, Studio model port, module upgrade, db 1 odoo (production), db 2 odoo_repair_fresh, v15.0.1.12 → v15.0.1.13 → v15.0.1.14, ir_model_access ACLs, project.view_task_form2, material_line_product_count, helpdesk_ticket_id, attrs view validation
**Projects:** helpdesk_repair_custom (Odoo 15 custom addon at /opt/odoo15/custom-addons/helpdesk_repair_custom)
**Outcome:** Fixed UndefinedColumn crash on db 1 by upgrading module to v1.13 (creating missing x_studio_dispatch_done column); then ported 10 Studio models + 3 form tabs (Repair Image, Warranty Details, Repair Diagnosis) from db 1 into module code at v1.14 and upgraded db 2 successfully.

## Decisions Made
- Upgrade module on db 1 to create missing column (rather than ALTER TABLE manually) — proper Odoo path; lets ir_model_fields registry stay consistent with schema.
- Use venv Python (`/opt/odoo15/myodoo15-venv/bin/python3`) when invoking odoo-bin manually — system `python3` lacks PIL/site-packages.
- Define ported Studio models with the same `x_` prefix names (`x_task_diagnosis`, `x_diagnosis_areas`, ...) and `_rec_name = 'x_name'`, `_active_name = 'x_active'` for compatibility with db 1's Studio-created schema.
- Use `attachment=True` on the four Binary image fields on project.task — best practice for binary blobs.
- Drop the `readonly` attrs condition on `x_studio_diagnosis_ids` that referenced `material_line_product_count` — that compute field from `industry_fsm_sale` failed view validation when our inherit-of-`project.view_task_form2` was composed. Trade-off: diagnosis list is fully editable in db 2 even when FSM materials exist. All other Studio attrs (`helpdesk_ticket_id` invisible/required) were preserved.
- Inherit `project.view_task_form2` (matches what Studio view 3019 does) rather than the FSM enterprise overlays.
- Made `x_task_diagnosis` ACL writable for `base.group_user` (technicians create rows) while keeping the 9 reference/lookup models read-only for users and full-CRUD for `helpdesk.group_helpdesk_manager`.

## Key Learnings
- Odoo's `CacheMiss` + `UndefinedColumn` cascade: the visible top-level traceback (here, `_compute_x_studio_rug_approval_status` for `helpdesk.ticket`) can be triggered deep down by a foreign relation read — the One2many `fsm_task_ids` lookup tries to filter by `Comodel._active_name`, which builds a SELECT including ALL stored fields of `project.task`, and a single missing column blows up the whole compute.
- A stored field defined in module code but never migrated leaves the model registry advertising a column the DB doesn't have — every read of `project.task` then crashes regardless of which field the caller asked for.
- View validation for an inherited view sees the *composed* view, but only fields present in the Python `_fields` of the model can be referenced in `attrs`. A field defined in an enterprise overlay module's view (not its model) won't satisfy the validator if our view is the one declaring the attrs.
- Studio-created models use `x_name` as their primary name field and `x_active` (not `active`) for archive support. Porting them to code requires setting `_rec_name` and `_active_name` explicitly.
- Binary fields with `attachment=True` do NOT create a database column — they store the blob in `ir.attachment`. `information_schema.columns` will not show them; check `ir_model_fields` instead.

## Solutions & Fixes
- **Crash fix (db 1):** `systemctl stop odoo15 && su - odoo15 -s /bin/bash -c "/opt/odoo15/myodoo15-venv/bin/python3 /opt/odoo15/odoo/odoo-bin -c /etc/odoo15.conf -u helpdesk_repair_custom -d odoo --stop-after-init"` then `systemctl start odoo15`. Created the `project_task.x_studio_dispatch_done boolean` column and moved installed version 15.0.1.12 → 15.0.1.13.
- **Feature add (db 2):** Created new model file `models/task_diagnosis.py` defining 10 Studio-equivalent models, added 4 Binary fields + 1 One2many to `project_task.py`, wrote a single inherit view `view_task_form_repair_tabs` adding the 3 notebook pages, added 11 ACL pairs (user read / manager CRUD; user CRUD for `x_task_diagnosis`), bumped manifest to 15.0.1.14, then ran the upgrade on `odoo_repair_fresh`.
- **View validation fix:** First attempt failed on `helpdesk_ticket_id` "must be present in view" — added it as an invisible field via `<xpath expr="//sheet" position="inside">`. Second attempt failed on `material_line_product_count` "does not exist in model" — fixed by removing that field's `readonly` attrs from the diagnosis One2many.

## Files Modified
- `/opt/odoo15/custom-addons/helpdesk_repair_custom/models/task_diagnosis.py`: NEW — defines `x_repair_reason`, `x_conditions`, `x_diagnosis_areas`, `x_diagnosis_codes`, `x_repair_stages`, `x_repair_sub_reason`, `x_resolutions`, `x_symptom_areas`, `x_symptom_codes`, `x_task_diagnosis`. All use `_rec_name='x_name'`, `_active_name='x_active'`, `_order='x_studio_sequence, x_name'` (or `, id` for diagnosis lines). `x_studio_task_id` on `x_task_diagnosis` has `ondelete='cascade'`.
- `/opt/odoo15/custom-addons/helpdesk_repair_custom/models/__init__.py`: added `from . import task_diagnosis` at top of file.
- `/opt/odoo15/custom-addons/helpdesk_repair_custom/models/project_task.py`: after `x_studio_dispatch_done`, added `x_studio_repair_image_01`, `x_studio_repair_image_02`, `x_studio_warranty_card`, `x_studio_related_information` (all `Binary, attachment=True`) and `x_studio_diagnosis_ids = fields.One2many('x_task_diagnosis', 'x_studio_task_id', ...)`.
- `/opt/odoo15/custom-addons/helpdesk_repair_custom/views/project_task_views.xml`: was empty stub; now declares `view_task_form_repair_tabs` inheriting `project.view_task_form2`. Adds invisible `helpdesk_ticket_id` via `//sheet` xpath, then 3 pages (Repair Image, Warranty Details, Repair Diagnosis) inside `//notebook`. Diagnosis tab still has `attrs="{'invisible': [['helpdesk_ticket_id', '=', False]]}"`. The `x_studio_diagnosis_ids` editable tree has fields: x_studio_sequence (handle), x_name (inv), x_studio_condition (inv), x_studio_symptom_area (inv), x_studio_symptom_code (inv), x_studio_description, x_studio_diagnosis_area (req), x_studio_diagnosis_code (req, domain on diagnosis_area_1), x_studio_reason (req), x_studio_sub_reason (req, domain on reason_code), x_studio_resolution (req), x_studio_repair_stage (req), x_studio_task_id (inv).
- `/opt/odoo15/custom-addons/helpdesk_repair_custom/security/ir_model_access.xml`: added 22 access records (user + manager pair for each of 10 new models; `x_task_diagnosis` user record grants CRUD instead of read-only).
- `/opt/odoo15/custom-addons/helpdesk_repair_custom/__manifest__.py`: version 15.0.1.13 → 15.0.1.14.

## Setup & Config
- Production DB ("db 1") = PostgreSQL database `odoo`. Fresh/dev DB ("db 2") = `odoo_repair_fresh`.
- DB user for manual psql: `su - odoo15 -s /bin/bash -c "psql <dbname> -c '...'"` (system user matches PG role).
- Manual odoo-bin invocation **must** use venv Python: `/opt/odoo15/myodoo15-venv/bin/python3 /opt/odoo15/odoo/odoo-bin -c /etc/odoo15.conf -u helpdesk_repair_custom -d <dbname> --stop-after-init`. System `/usr/bin/python3` will crash with `ModuleNotFoundError: No module named 'PIL'`.
- Standard restart pattern: `systemctl stop odoo15` → run upgrade → `systemctl start odoo15`. Log at `/var/log/odoo15/odoo.log`.
- Odoo config: `/etc/odoo15.conf` (db_user=odoo15, addons_path=/opt/odoo15/odoo/addons,/opt/odoo15/custom-addons).

## Pending Tasks
- **db 1 has NOT been upgraded to v15.0.1.14** — the new tabs and 10 ported models only exist in db 2. db 1 was only taken to v15.0.1.13 (the crash fix). If/when the user wants the same code-defined models in db 1, expect collisions: db 1 already has Studio-defined versions of `x_task_diagnosis` and the 9 lookup models (`_custom=True` in `ir_model`). A direct upgrade would either fail or require a migration script to convert Studio rows to module-owned rows. Approach not yet decided.
- The diagnosis One2many in db 2 no longer goes readonly when FSM materials exist (the `material_line_product_count >= 1` guard was dropped). If this UX guard matters, find a different inherit point that has that field already in scope, or add a server-side write constraint.
- No demo data for the 10 lookup models in db 2 — `x_diagnosis_areas`, `x_diagnosis_codes`, etc. are all empty tables. Users must populate them before the diagnosis tab is usable.

## Errors & Workarounds
- **Error 1:** Top-level traceback was `CacheMiss: 'helpdesk.ticket(978,).x_studio_rug_approval_status'` → `CacheMiss: 'project.task(7170,).active'` → `psycopg2.errors.UndefinedColumn: column project_task.x_studio_dispatch_done does not exist`. **Workaround:** upgrade module so the stored field's column gets created. Root cause: code at v1.13, DB at v1.12.
- **Error 2:** `ModuleNotFoundError: No module named 'PIL'` when running odoo-bin via `su - odoo15 -s /bin/bash -c "/opt/odoo15/odoo/odoo-bin ..."`. **Workaround:** invoke through venv: `/opt/odoo15/myodoo15-venv/bin/python3 /opt/odoo15/odoo/odoo-bin ...`. (The systemd unit already has the PATH fix from a prior session; only manual invocations need the explicit venv path.)
- **Error 3:** `Field 'helpdesk_ticket_id' used in attrs ... must be present in view but is missing`. **Workaround:** added `<field name="helpdesk_ticket_id" invisible="1"/>` inside the sheet.
- **Error 4:** `Field "material_line_product_count" does not exist in model "project.task"` — but it does exist (defined in `enterprise/industry_fsm_sale/models/project_task.py:19` as a compute field). The composed view chain validating our inherit couldn't see it from the perspective of our inherit_id. **Workaround:** removed the `readonly` attrs condition from `x_studio_diagnosis_ids` that referenced it. Did not try alternative inherits.

## Key Exchanges
- User pasted the production traceback. I traced from the visible compute back through `fsm_task_ids` One2many → `_active_name` filter → SELECT building, identified `x_studio_dispatch_done` defined in module v1.13 but DB at v1.12, ran the targeted module upgrade.
- User asked to inspect Studio tabs in db 1 and port them to db 2. I extracted view 3019's `//notebook` xpath verbatim (3 pages: Repair Image, Warranty Details, Repair Diagnosis), enumerated the 5 project.task fields and the `x_task_diagnosis` model + its 9 lookup-model relations, then wrote the model/view/security/manifest changes in one pass and resolved two view-validation errors during upgrade.

## Custom Notes
None

---

## Quick Resume Context
The `helpdesk_repair_custom` module on db 2 (`odoo_repair_fresh`) is now at v15.0.1.14 with three new project.task tabs (Repair Image, Warranty Details, Repair Diagnosis) and 10 ported Studio models in `models/task_diagnosis.py`. db 1 (`odoo`) production is at v15.0.1.13 — it has the crash fix but NOT the new tabs/models, and porting them there will conflict with the existing Studio-owned versions of those same models. Next likely work: populate seed data for the 10 lookup tables in db 2, or design a migration path for db 1.

---

## Raw Session Log

### User: fix error in db 1 — psycopg2 UndefinedColumn

Traceback chained CacheMiss → CacheMiss → UndefinedColumn `project_task.x_studio_dispatch_done`. Originated in `helpdesk_repair_custom/models/helpdesk_ticket.py:257` (`_compute_x_studio_rug_approval_status` iterating `rec.fsm_task_ids`).

### Assistant: diagnosis + fix

- Read `helpdesk_ticket.py:245-283`; confirmed the compute iterates `fsm_task_ids` (project.task), which Odoo filters by `Comodel._active_name`, triggering a `_read` on project.task that SELECTs all stored fields including the missing `x_studio_dispatch_done`.
- `grep "x_studio_dispatch_done"` → defined in `models/project_task.py:19` as `fields.Boolean(... store=True)`. Also stored field on stock_picking (compute, not stored — no column needed).
- Production DB = `odoo`; psql verified the column is absent and field is absent from `ir_model_fields`.
- `ir_module_module.latest_version` for `helpdesk_repair_custom` = `15.0.1.12`; `__manifest__.py` = `15.0.1.13`. Mismatch confirmed.
- Stopped odoo15, hit PIL crash with system python, retried with venv python `/opt/odoo15/myodoo15-venv/bin/python3`. Upgrade succeeded (EXIT 0). Verified column `x_studio_dispatch_done boolean` exists, version now `15.0.1.13`. Started service.

### User: add Repair Image, Warranty Details, Repair Diagnosis tabs from db 1 into the helpdesk_repair app for db 2

### Assistant: scope + implementation

- Inspected `ir_ui_view` for `project.task` in db 1, located Studio view id 3019 (`Odoo Studio: project.task.form customization`, inherits `project.view_task_form2`).
- Extracted the `//form[1]/sheet[1]/notebook[1]` `position="inside"` block containing the 3 pages.
- Fields on project.task in db 1 used by tabs: `x_studio_repair_image_01`, `x_studio_repair_image_02` (binary), `x_studio_warranty_card`, `x_studio_related_information` (binary), `x_studio_diagnosis_ids` (one2many → `x_task_diagnosis`). None present in db 2.
- `x_task_diagnosis` is a Studio model in db 1 with 9 lookup-model relations: `x_conditions`, `x_diagnosis_areas`, `x_diagnosis_codes`, `x_repair_reason`, `x_repair_stages`, `x_repair_sub_reason`, `x_resolutions`, `x_symptom_areas`, `x_symptom_codes`. db 2 has none of them. Module code has none of them.
- Wrote `models/task_diagnosis.py` with all 10 models (correct `_rec_name`, `_active_name`, `_order`, intra-model many2ones including `x_studio_diagnosis_area_1` on diagnosis_codes and `x_studio_reason_code` on sub_reason, `x_studio_symptom_area` on symptom_codes).
- Updated `models/__init__.py` (import task_diagnosis), `models/project_task.py` (add 4 Binary + 1 One2many after dispatch_done), wrote `views/project_task_views.xml` from empty stub (inherit_id=`project.view_task_form2`, 3 pages, helpdesk_ticket_id invisible via `//sheet`), added 22 ACL records to `security/ir_model_access.xml`, bumped manifest to `15.0.1.14`.
- First upgrade on db 2 failed: `Field 'helpdesk_ticket_id' used in attrs ... must be present in view`. Added `<field name="helpdesk_ticket_id" invisible="1"/>` inside `//sheet`.
- Second upgrade failed: `Field "material_line_product_count" does not exist in model`. That field is a compute defined in `enterprise/industry_fsm_sale/models/project_task.py:19`; module installed in db 2 but the view-validator (composing through our inherit chain) didn't surface it. Dropped the `readonly` attrs that referenced it; kept `force_save="True"`.
- Third upgrade EXIT 0. Verified 10 new tables in db 2, 5 new fields registered on project.task in `ir_model_fields` (binaries don't show as columns because `attachment=True`), `latest_version = 15.0.1.14`. Service restarted clean.
