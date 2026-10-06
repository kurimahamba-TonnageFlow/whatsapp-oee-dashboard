"""Evidence-only task timing: no inferred competence or unapproved thresholds."""
from collections import defaultdict
from statistics import median

from .catalogue import CATALOGUE
TASKS = tuple(CATALOGUE["tasks"])
REASONS = {task.casefold(): task for task in TASKS}
REASONS["ccp check"] = "X-ray (CCP)"


def build_task_performance(rows, technicians):
    grouped = defaultdict(list)
    unclassified = 0
    for row in rows:
        task = REASONS.get(row["reason"].strip().casefold())
        if task is None:
            unclassified += 1
            continue
        grouped[(row["started_by"], task)].append(row)
    names = sorted(set(technicians) | {name for name, _ in grouped}, key=str.casefold)
    cells = []
    for name in names:
        for task in TASKS:
            records = grouped.get((name, task), [])
            contexts = defaultdict(list)
            evidence = []
            for row in records:
                start, end = row["started_at"], row["ended_at"]
                minutes = (end - start).total_seconds() / 60 if end and end >= start else None
                issues = []
                if minutes is None or minutes <= 0: issues.append("No positive completed duration")
                if not row.get("observation_complete"): issues.append("Legacy timer: performer, transition or delay context not confirmed")
                if not all(str(row.get(k) or "").strip().casefold() not in ("", "unknown", "n/a") for k in ("product", "from_configuration", "to_configuration")):
                    issues.append("Incomplete configuration")
                if row.get("shared_work"): issues.append("Shared work")
                if row.get("waiting_minutes", 0) > 0: issues.append("Waiting recorded")
                if row.get("completed_successfully") is not True: issues.append("Successful completion not confirmed")
                key = tuple(str(row.get(k) or "Unknown").strip().casefold() for k in
                            ("product", "from_configuration", "to_configuration"))
                if not issues:
                    contexts[key].append(minutes)
                evidence.append({"id": f"{row.get('source', 'legacy')}:{row['id']}", "benchmark_exclusions": issues,
                                 "notes": row.get("notes", ""), "waiting_minutes": row.get("waiting_minutes"),
                                 "shared_work": row.get("shared_work"), "source": row.get("source", "legacy"),
                                 "started_at": start, "ended_at": end,
                                 "started_by": row["started_by"], "ended_by": row["ended_by"],
                                 "elapsed_minutes": round(minutes, 2) if minutes is not None else None,
                                 "configuration": " / ".join(key)})
            cells.append({"technician": name, "task": task, "rating": "grey",
                          "status": "Reference and comparison rules not agreed" if records else "No timed evidence",
                          "recorded_count": len(records), "evidence": evidence,
                          "groups": [{"configuration": " / ".join(key), "completed_count": len(values),
                                      "fastest_minutes": round(min(values), 2), "slowest_minutes": round(max(values), 2),
                                      "median_minutes": round(median(values), 2)} for key, values in contexts.items()]})
    return {"production_line": "Rovema", "tasks": TASKS, "technicians": names,
            "cells": cells, "unclassified_count": unclassified}
