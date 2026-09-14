# ==========================================================
# TONNAGEFLOW PULSE
# Dashboard Read API
# ==========================================================
#
# HTTP-only, read-only. Reuses the dashboard query functions in
# src/database.py. Never calls src/main.py's CLI/input() functions.
#
# MVP calculation decisions (see docs/dashboard_integration.md):
#   - Expected/actual pallets: SUM(hourly_updates.expected_pallets /
#     .actual_pallets) - NOT production_runs.total_pallets_completed,
#     whose overrun handling differs.
#   - Tonnes = pallets * cases_per_pallet * packs_per_case *
#     pack_weight_kg / 1000.
#   - Output gap = MAX(expected - actual, 0).
#   - Target achievement % = actual/expected*100, or null (not 0)
#     when expected is 0. Never sourced from reported OEE.
#   - Unplanned downtime = resolved_at - opened_at for resolved
#     faults, or NOW() - opened_at for open faults (marked active).
#     NOT a substitute for hourly_updates.estimated_lost_minutes.
#   - Machine Setup/Repair split and Quality Events: no reliable
#     source data exists yet - both are returned with an explicit
#     "not_captured"/"not_available" status, never invented zeros.

from datetime import date, datetime, timezone
import csv
import io

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel

try:
    from .database import (
        get_dashboard_downtime_events,
        get_dashboard_engineering_updates,
        get_dashboard_faults,
        get_dashboard_filter_options,
        get_dashboard_output_timeline,
        get_dashboard_planned_downtime,
        get_dashboard_run,
        get_dashboard_summary,
        list_dashboard_runs,
    )
except ImportError:
    from database import (
        get_dashboard_downtime_events,
        get_dashboard_engineering_updates,
        get_dashboard_faults,
        get_dashboard_filter_options,
        get_dashboard_output_timeline,
        get_dashboard_planned_downtime,
        get_dashboard_run,
        get_dashboard_summary,
        list_dashboard_runs,
    )


router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])

MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 25
EXPORT_MAX_ROWS = 100_000


# ==========================================================
# SHARED FILTER DEPENDENCY
# ==========================================================
# "format" is accepted (so callers never get a 422 for sending it) but
# is never applied - no reliable column mapping exists for it anywhere
# in the schema. See DashboardFilterOptions.unsupported_filters.


def dashboard_filters(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    production_line: str | None = Query(default=None),
    shift: str | None = Query(default=None),
    product: str | None = Query(default=None),
    customer: str | None = Query(default=None),
    format: str | None = Query(default=None),
    technician: str | None = Query(default=None),
    engineer: str | None = Query(default=None),
    machine: str | None = Query(default=None),
    downtime_type: str | None = Query(default=None),
    engineering_class: str | None = Query(default=None),
    run_status: str | None = Query(default=None),
    fault_status: str | None = Query(default=None),
) -> dict:
    return {
        "date_from": date_from,
        "date_to": date_to,
        "production_line": production_line,
        "shift": shift,
        "product": product,
        "customer": customer,
        "format": format,
        "technician": technician,
        "engineer": engineer,
        "machine": machine,
        "downtime_type": downtime_type,
        "engineering_class": engineering_class,
        "run_status": run_status,
        "fault_status": fault_status,
    }


def _call_db(operation_name, func, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except Exception:
        print("DATABASE ERROR")
        print(f"Dashboard query failed: {operation_name}")

        raise HTTPException(
            status_code=503,
            detail="Dashboard data is temporarily unavailable. Please try again.",
        )


# ==========================================================
# RESPONSE MODELS
# ==========================================================


class DashboardFilterOptions(BaseModel):
    production_lines: list[str]
    shifts: list[str]
    products: list[str]
    customers: list[str]
    technicians: list[str]
    engineers: list[str]
    machines: list[str]
    downtime_types: list[str]
    engineering_classes: list[str]
    run_statuses: list[str]
    fault_statuses: list[str]
    unsupported_filters: list[str]


class DashboardRunSummary(BaseModel):
    run_id: int
    production_line: str
    line_technician: str
    shift: str
    customer: str
    product: str
    pack_type: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    pallets_remaining: int
    total_pallets_completed: int
    changeover_type: str | None


class DashboardRunsResponse(BaseModel):
    items: list[DashboardRunSummary]
    total: int
    page: int
    page_size: int


class DashboardRunDetail(BaseModel):
    run_id: int
    production_line: str
    line_technician: str
    shift: str
    customer: str
    product: str
    pack_weight_kg: float
    packs_per_case: int
    pack_type: str
    target_speed_ppm: float
    cases_per_pallet: int
    starting_pallets_remaining: int
    pallets_remaining: int
    previous_run_completed: int
    total_pallets_completed: int
    potential_overrun_pallets: int
    confirmed_overrun_pallets: int
    status: str
    started_at: datetime
    finished_at: datetime | None
    changeover_type: str | None


class DashboardTimelinePoint(BaseModel):
    hourly_update_id: int
    production_run_id: int
    production_line: str
    sequence_in_run: int
    expected_pallets: float
    actual_pallets: float
    expected_tonnes: float
    actual_tonnes: float
    output_gap_pallets: float
    target_achievement_percent: float | None


class DashboardOutputTimelineResponse(BaseModel):
    items: list[DashboardTimelinePoint]
    note: str


class DashboardPlannedDowntimeGroup(BaseModel):
    downtime_type: str
    total_minutes: float
    occurrences: int


class DashboardPlannedDowntimeResponse(BaseModel):
    groups: list[DashboardPlannedDowntimeGroup]
    total_minutes: float


class DashboardEngineeringClassBreakdown(BaseModel):
    engineering_class: str
    count: int


class DashboardEngineeringDowntimeResponse(BaseModel):
    total_faults: int
    engineer_called_faults: int
    open_faults: int
    resolved_faults: int
    unplanned_downtime_minutes: float
    unplanned_downtime_includes_active_faults: bool
    update_type_breakdown: list[DashboardEngineeringClassBreakdown]
    machine_setup_minutes: float | None
    machine_repair_minutes: float | None
    machine_classification_status: str


class DashboardFault(BaseModel):
    downtime_event_id: int
    production_run_id: int
    production_line: str
    fault_id: int
    machine: str
    reason: str
    reported_by: str
    engineer_called: bool
    production_status: str
    engineering_status: str
    engineer: str | None
    retrospective: bool
    opened_at: datetime
    resolved_at: datetime | None
    duration_minutes: float
    duration_is_active: bool


class DashboardFaultsResponse(BaseModel):
    items: list[DashboardFault]
    total: int


class DashboardQualityEventsResponse(BaseModel):
    items: list[dict] = []
    total: int = 0
    data_status: str = "not_available"
    message: str = (
        "Quality events are not captured by the current Pulse data model."
    )


class DashboardSummary(BaseModel):
    total_runs: int
    expected_pallets: float
    actual_pallets: float
    expected_tonnes: float
    actual_tonnes: float
    output_gap_pallets: float
    output_gap_tonnes: float
    target_achievement_percent: float | None
    planned_downtime_minutes: float
    unplanned_downtime_minutes: float
    unplanned_downtime_includes_active_faults: bool
    estimated_lost_packs: float
    estimated_lost_minutes: float
    estimated_lost_pallets: float
    estimated_lost_tonnes: float
    open_faults: int
    resolved_faults: int
    machine_setup_minutes: float | None
    machine_repair_minutes: float | None
    machine_classification_status: str


# ==========================================================
# ENDPOINTS
# ==========================================================


@router.get("/filter-options", response_model=DashboardFilterOptions)
def dashboard_filter_options():
    data = _call_db(
        "get_dashboard_filter_options", get_dashboard_filter_options
    )
    return DashboardFilterOptions(**data)


@router.get("/runs", response_model=DashboardRunsResponse)
def dashboard_runs(
    filters: dict = Depends(dashboard_filters),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
):
    offset = (page - 1) * page_size

    rows, total = _call_db(
        "list_dashboard_runs", list_dashboard_runs, filters, page_size, offset
    )

    return DashboardRunsResponse(
        items=[DashboardRunSummary(**row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/runs/{run_id}", response_model=DashboardRunDetail)
def dashboard_run_detail(run_id: int):
    row = _call_db("get_dashboard_run", get_dashboard_run, run_id)

    if row is None:
        raise HTTPException(status_code=404, detail="Production Run not found.")

    return DashboardRunDetail(**row)


@router.get("/output-timeline", response_model=DashboardOutputTimelineResponse)
def dashboard_output_timeline(filters: dict = Depends(dashboard_filters)):
    rows = _call_db(
        "get_dashboard_output_timeline", get_dashboard_output_timeline, filters
    )

    items = []
    for row in rows:
        expected_pallets = float(row["expected_pallets"])
        actual_pallets = float(row["actual_pallets"])
        cases_per_pallet = row["cases_per_pallet"]
        packs_per_case = row["packs_per_case"]
        pack_weight_kg = float(row["pack_weight_kg"])

        expected_tonnes = (
            expected_pallets * cases_per_pallet * packs_per_case * pack_weight_kg
        ) / 1000.0
        actual_tonnes = (
            actual_pallets * cases_per_pallet * packs_per_case * pack_weight_kg
        ) / 1000.0

        items.append(
            DashboardTimelinePoint(
                hourly_update_id=row["hourly_update_id"],
                production_run_id=row["production_run_id"],
                production_line=row["production_line"],
                sequence_in_run=row["sequence_in_run"],
                expected_pallets=expected_pallets,
                actual_pallets=actual_pallets,
                expected_tonnes=expected_tonnes,
                actual_tonnes=actual_tonnes,
                output_gap_pallets=max(expected_pallets - actual_pallets, 0),
                target_achievement_percent=(
                    (actual_pallets / expected_pallets * 100)
                    if expected_pallets > 0
                    else None
                ),
            )
        )

    return DashboardOutputTimelineResponse(
        items=items,
        note=(
            "hourly_updates has no timestamp column; ordering uses "
            "submission sequence (sequence_in_run), not wall-clock time."
        ),
    )


@router.get("/planned-downtime", response_model=DashboardPlannedDowntimeResponse)
def dashboard_planned_downtime(filters: dict = Depends(dashboard_filters)):
    rows = _call_db(
        "get_dashboard_planned_downtime", get_dashboard_planned_downtime, filters
    )

    groups = [
        DashboardPlannedDowntimeGroup(
            downtime_type=row["downtime_type"],
            total_minutes=float(row["total_minutes"] or 0),
            occurrences=row["occurrences"],
        )
        for row in rows
    ]

    return DashboardPlannedDowntimeResponse(
        groups=groups,
        total_minutes=sum(group.total_minutes for group in groups),
    )


@router.get(
    "/engineering-downtime", response_model=DashboardEngineeringDowntimeResponse
)
def dashboard_engineering_downtime(filters: dict = Depends(dashboard_filters)):
    downtime_rows = _call_db(
        "get_dashboard_downtime_events", get_dashboard_downtime_events, filters
    )
    engineering_rows = _call_db(
        "get_dashboard_engineering_updates",
        get_dashboard_engineering_updates,
        filters,
    )

    now = datetime.now(timezone.utc)
    total_faults = len(downtime_rows)
    engineer_called_faults = sum(
        1 for row in downtime_rows if row["engineer_called"]
    )
    open_faults = sum(
        1 for row in downtime_rows if row["production_status"] == "Ongoing"
    )
    resolved_faults = sum(
        1 for row in downtime_rows if row["production_status"] == "Resolved"
    )

    total_minutes = 0.0
    includes_active = False

    for row in downtime_rows:
        opened_at = row["opened_at"]
        resolved_at = row["resolved_at"]

        if opened_at.tzinfo is None:
            opened_at = opened_at.replace(tzinfo=timezone.utc)

        if resolved_at is None:
            includes_active = True
            end = now
        else:
            end = (
                resolved_at
                if resolved_at.tzinfo is not None
                else resolved_at.replace(tzinfo=timezone.utc)
            )

        total_minutes += (end - opened_at).total_seconds() / 60.0

    breakdown_counts: dict[str, int] = {}
    for row in engineering_rows:
        update_type = row["update_type"]
        breakdown_counts[update_type] = breakdown_counts.get(update_type, 0) + 1

    update_type_breakdown = [
        DashboardEngineeringClassBreakdown(engineering_class=key, count=value)
        for key, value in sorted(breakdown_counts.items())
    ]

    return DashboardEngineeringDowntimeResponse(
        total_faults=total_faults,
        engineer_called_faults=engineer_called_faults,
        open_faults=open_faults,
        resolved_faults=resolved_faults,
        unplanned_downtime_minutes=total_minutes,
        unplanned_downtime_includes_active_faults=includes_active,
        update_type_breakdown=update_type_breakdown,
        machine_setup_minutes=None,
        machine_repair_minutes=None,
        machine_classification_status="not_captured",
    )


@router.get("/faults", response_model=DashboardFaultsResponse)
def dashboard_faults(filters: dict = Depends(dashboard_filters)):
    rows = _call_db("get_dashboard_faults", get_dashboard_faults, filters)
    items = [DashboardFault(**row) for row in rows]

    return DashboardFaultsResponse(items=items, total=len(items))


@router.get("/quality-events", response_model=DashboardQualityEventsResponse)
def dashboard_quality_events():
    # No quality_events table or columns exist anywhere in the schema -
    # this is not a placeholder bug, it is the documented MVP status.
    return DashboardQualityEventsResponse()


@router.get("/summary", response_model=DashboardSummary)
def dashboard_summary(filters: dict = Depends(dashboard_filters)):
    data = _call_db("get_dashboard_summary", get_dashboard_summary, filters)
    return DashboardSummary(**data)


@router.get("/export")
def dashboard_export(filters: dict = Depends(dashboard_filters)):
    rows, _total = _call_db(
        "list_dashboard_runs",
        list_dashboard_runs,
        filters,
        EXPORT_MAX_ROWS,
        0,
    )

    fieldnames = [
        "run_id",
        "production_line",
        "line_technician",
        "shift",
        "customer",
        "product",
        "pack_type",
        "status",
        "started_at",
        "finished_at",
        "pallets_remaining",
        "total_pallets_completed",
        "changeover_type",
    ]

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()

    for row in rows:
        csv_row = dict(row)

        if csv_row.get("started_at") is not None:
            csv_row["started_at"] = csv_row["started_at"].isoformat()

        if csv_row.get("finished_at") is not None:
            csv_row["finished_at"] = csv_row["finished_at"].isoformat()

        writer.writerow(csv_row)

    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=pulse_runs_export.csv"
        },
    )
