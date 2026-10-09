"""Install the user-supplied Rovema sheet once, with existing identities and audit."""
from copy import deepcopy
import json
from pathlib import Path
from . import database as db
from .linetech import LineTechConfig, validate_config_references


def rovema_preset():
    return json.loads(Path(__file__).with_name("rovema_linetech_presets.json").read_text())


def install_rovema_presets(actor, idempotency=None):
    from .linetech_api import initial_config
    if not actor or not actor.strip():
        raise ValueError("A named Management actor is required.")
    preset = rovema_preset()
    with db.get_database_connection() as connection:
        with connection.cursor(row_factory=db.dict_row) as cursor:
            db._claim_idempotency(cursor, connection, idempotency)
            cursor.execute("SELECT * FROM public.production_lines WHERE name='Rovema' AND active FOR UPDATE")
            before = cursor.fetchone()
            if before is None:
                raise db.PulseCaptureError(404, "Active Rovema line not found.")
            settings = deepcopy(before.get("linetech_config") or {})
            cursor.execute("SELECT id FROM public.management_audit_log WHERE action='linetech_sheet_configuration' AND record_type='production_line' AND record_id=%s LIMIT 1", (str(before["id"]),))
            if cursor.fetchone():
                result = {"status": "success", "already_installed": True, "config": settings}
            else:
                # Serialize with catalogue writes; bounded by the caller/database timeout.
                cursor.execute("LOCK TABLE public.machines, public.buttons IN SHARE ROW EXCLUSIVE MODE")
                resolved = []
                for order, wanted in enumerate(preset["machines"], 1):
                    cursor.execute("SELECT * FROM public.machines WHERE production_line_id=%s AND lower(name)=lower(%s)", (before["id"], wanted["name"]))
                    matches = cursor.fetchall()
                    if len(matches) > 1:
                        raise db.PulseCaptureError(409, "Duplicate machine names need review: " + wanted["name"])
                    original = matches[0] if matches else None
                    if original is None:
                        cursor.execute("INSERT INTO public.machines(production_line_id,name,display_order) VALUES(%s,%s,%s) RETURNING *", (before["id"], wanted["name"], order))
                        machine = cursor.fetchone()
                        db._configuration_audit(cursor,"linetech_sheet_machine",actor,"machine",None,machine)
                    else:
                        machine = original
                        if not machine["active"]:
                            cursor.execute("UPDATE public.machines SET active=true,updated_at=now() WHERE id=%s RETURNING *", (machine["id"],))
                            machine = cursor.fetchone()
                            db._configuration_audit(cursor,"linetech_sheet_machine",actor,"machine",original,machine)
                    categories = []
                    for category, names in wanted["categories"].items():
                        ids = []
                        for index, name in enumerate(names):
                            cursor.execute("SELECT * FROM public.buttons WHERE machine_id=%s AND lower(name)=lower(%s)", (machine["id"], name))
                            matches = cursor.fetchall()
                            if len(matches)>1:
                                raise db.PulseCaptureError(409, "Duplicate reason names need review: " + name)
                            old = matches[0] if matches else None
                            if old and old["event_type"] != "unplanned_fault":
                                raise db.PulseCaptureError(409, "Existing planned reason conflicts with sheet fault: " + name)
                            if old is None:
                                cursor.execute("INSERT INTO public.buttons(machine_id,name,event_type,ownership,display_order) VALUES(%s,%s,'unplanned_fault','Production',%s) RETURNING *", (machine["id"],name,index))
                                button = cursor.fetchone()
                                db._configuration_audit(cursor,"linetech_sheet_button",actor,"button",None,button)
                            else:
                                button = old
                                if not button["active"]:
                                    cursor.execute("UPDATE public.buttons SET active=true,updated_at=now() WHERE id=%s RETURNING *", (button["id"],))
                                    button = cursor.fetchone()
                                    db._configuration_audit(cursor,"linetech_sheet_button",actor,"button",old,button)
                            ids.append(button["id"])
                        categories.append({"name":category,"active":True,"button_ids":ids})
                    resolved.append((wanted,machine,categories))
                if not settings:
                    settings = initial_config([])
                groups = settings.setdefault("groups", [])
                labels = {"sbs":"SBS / Bagger","xray":"X-ray","casepacker":"Case Packer","robot":"Robot Palletiser"}
                for key,label in labels.items():
                    if not any(g["key"]==key for g in groups):
                        groups.append({"key":key,"label":label,"equipment":[]})
                for wanted,machine,categories in resolved:
                    old_equipment = next((e for g in groups for e in g["equipment"] if e["machine_id"]==machine["id"]), None)
                    equipment = deepcopy(old_equipment) if old_equipment else {"machine_id":machine["id"],"label":wanted["label"],"categories":[]}
                    equipment["active"] = True
                    preset_ids = {b for c in categories for b in c["button_ids"]}
                    for c in equipment["categories"]:
                        c["button_ids"] = [b for b in c["button_ids"] if b not in preset_ids]
                    for category in categories:
                        existing = next((c for c in equipment["categories"] if c["name"]==category["name"]),None)
                        if existing:
                            existing["button_ids"] += category["button_ids"]
                            existing["active"] = True
                        else:
                            equipment["categories"].append(category)
                    for g in groups:
                        g["equipment"] = [e for e in g["equipment"] if e["machine_id"]!=machine["id"]]
                        if g["key"]==wanted["group"]:
                            g["equipment"].append(equipment)
                planned = settings.setdefault("planned", [])
                for wanted in preset["planned"]:
                    existing = next((p for p in planned if p["reason"].casefold()==wanted["reason"].casefold()),None)
                    if existing:
                        existing["active"] = True
                        # Film/label identities on these supplied sheets are BV1 and BV2.
                        existing["components"] = wanted["components"]
                    else:
                        planned.append(wanted)
                settings.update(enabled=True)
                settings = LineTechConfig.model_validate(settings).model_dump()
                cursor.execute("SELECT id FROM public.machines WHERE production_line_id=%s", (before["id"],))
                machines = cursor.fetchall()
                for machine in machines:
                    cursor.execute("SELECT id,event_type FROM public.buttons WHERE machine_id=%s", (machine["id"],))
                    machine["buttons"] = cursor.fetchall()
                validate_config_references(LineTechConfig.model_validate(settings), machines)
                cursor.execute("UPDATE public.production_lines SET linetech_config=%s,updated_at=now() WHERE id=%s RETURNING *", (db.Json(settings),before["id"]))
                after = cursor.fetchone()
                db._configuration_audit(cursor,"linetech_sheet_configuration",actor,"production_line",before,after)
                result = {"status":"success","already_installed":False,"config":settings}
            db._store_idempotent_response(cursor,idempotency,result)
        connection.commit()
    return result
