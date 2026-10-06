from datetime import datetime, timedelta, timezone
from src.task_performance import build_task_performance
from fastapi.testclient import TestClient
from src.api import app


def test_task_matrix_preserves_roster_and_no_evidence_is_grey():
    report = build_task_performance([], ["Liam", "Marina"])
    assert len(report["cells"]) == 14
    assert all(c["rating"] == "grey" and c["recorded_count"] == 0 for c in report["cells"])


def test_median_separates_formats_and_open_timers_without_inventing_ratings():
    start = datetime(2026, 10, 1, tzinfo=timezone.utc)
    def row(i, minutes, product="Rice"):
        return dict(id=i, reason="Film Change", started_by="Liam", ended_by="Marina",
                    started_at=start, ended_at=start+timedelta(minutes=minutes) if minutes else None,
                    product=product, observation_complete=True, from_configuration="1kg x10", to_configuration="1kg x10",
                    completed_successfully=True, waiting_minutes=0, shared_work=False, pack_type="Pillow", pack_weight_kg=1, packs_per_case=10, cases_per_pallet=100)
    rows = [row(1, 10), row(2, 30), row(3, 90, "Other"), row(4, None)]
    report = build_task_performance(rows, ["Liam"])
    cell = report["cells"][0]
    assert cell["recorded_count"] == 4
    assert [g["median_minutes"] for g in cell["groups"]] == [20, 90]
    assert cell["groups"][0]["fastest_minutes"] == 10
    assert cell["groups"][0]["slowest_minutes"] == 30
    assert cell["rating"] == "grey"
    assert cell["evidence"][0]["ended_by"] == "Marina"


def test_task_performance_requires_management_session():
    assert TestClient(app).get("/api/v1/management/task-performance").status_code == 401


def test_zero_unknown_and_legacy_remain_visible_but_never_benchmarks():
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    row = dict(id=1,reason="Film Change",started_by="Liam",ended_by="Liam",started_at=now,ended_at=now)
    cell = build_task_performance([row],["Liam"])["cells"][0]
    assert cell["recorded_count"] == 1
    assert cell["groups"] == []
    assert "No positive completed duration" in cell["evidence"][0]["benchmark_exclusions"]


def test_benchmarks_separate_destination_and_exclude_waiting_shared_or_failed_tasks():
    start=datetime(2026,10,1,tzinfo=timezone.utc)
    base=dict(reason='Changeover',started_by='Liam',ended_by='Liam',started_at=start,
              ended_at=start+timedelta(minutes=10),product='Rice',observation_complete=True,
              from_configuration='1kg',to_configuration='2kg',waiting_minutes=0,
              shared_work=False,completed_successfully=True)
    rows=[dict(base,id=1),dict(base,id=2,to_configuration='4kg'),
          dict(base,id=3,waiting_minutes=2),dict(base,id=4,shared_work=True),
          dict(base,id=5,completed_successfully=False)]
    cell=next(c for c in build_task_performance(rows,['Liam'])['cells'] if c['task']=='Changeover')
    assert len(cell['groups'])==2
    assert sum(g['completed_count'] for g in cell['groups'])==2
    assert cell['recorded_count']==5
    assert all(e['benchmark_exclusions'] for e in cell['evidence'][2:])
