"""Management-protected live snapshot and existing single-site target configuration."""
from datetime import date,datetime,timezone
from decimal import Decimal
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,Field,ConfigDict
from . import management_auth,database as db,live_dashboard as live
from .api_logging import log_operation_failure

router=APIRouter(prefix='/api/v1',tags=['live-dashboard'],dependencies=[Depends(management_auth.require_management_session)])

class LiveLine(BaseModel):
    name:str
    status:Literal['running','changeover','stopped','not_scheduled','idle','unknown']
    status_label:str
    tone:str
    status_recorded_at:datetime|None
    last_production_at:datetime|None
    job:dict|None
    changeover:dict|None
    last_hour:dict|None
    trend:list[dict]

class LiveSnapshot(BaseModel):
    generated_at:datetime
    timezone:str
    shift:dict
    recording_note:str
    latest_submission_at:datetime|None
    weekly:dict
    period:dict
    lines:list[LiveLine]
    summary:dict
    issues:list[dict]
    breakdowns:list[dict]
    thresholds:dict
    breakdown_method:str

@router.get('/dashboard/live',response_model=LiveSnapshot)
def snapshot(week_start:date|None=None):
    now=datetime.now(timezone.utc)
    try:
        data,week=live.load_snapshot(now,week_start)
        return live.build_snapshot(data,week,now)
    except Exception as error:
        log_operation_failure('dashboard','live_snapshot',error)
        raise HTTPException(503,'Live dashboard data is temporarily unavailable.') from error

class SiteTarget(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    site:Literal['site']='site'
    week_start:date
    week_start_day:int=Field(ge=0,le=6)
    target_tonnes:Decimal=Field(gt=0,le=1000000,decimal_places=3)
    notes:str=Field(default='',max_length=500)


def save_site_target(payload,actor):
    if payload.week_start.weekday()!=payload.week_start_day:
        raise HTTPException(422,'Effective week must start on the selected weekday.')
    with db.get_database_connection() as connection:
        with connection.cursor(row_factory=db.dict_row) as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",('live-site-weekly-target',))
            cursor.execute("SELECT * FROM public.weekly_tonnage_targets WHERE scope='site' AND week_start=%s FOR UPDATE",(payload.week_start,))
            before=cursor.fetchone()
            cursor.execute("SELECT id FROM public.weekly_tonnage_targets WHERE scope='site' AND week_start<>%s AND week_start>%s::date-7 AND week_start<%s::date+7",(payload.week_start,payload.week_start,payload.week_start))
            if cursor.fetchone():raise HTTPException(409,'This week overlaps an existing site target. Choose a non-overlapping effective week.')
            cursor.execute("""INSERT INTO public.weekly_tonnage_targets(week_start,scope,production_line,target_tonnes,set_by,notes)
                VALUES(%s,'site',NULL,%s,%s,%s) ON CONFLICT (week_start,scope,(COALESCE(production_line,'')))
                DO UPDATE SET target_tonnes=EXCLUDED.target_tonnes,set_by=EXCLUDED.set_by,notes=EXCLUDED.notes,updated_at=now() RETURNING *""",(payload.week_start,payload.target_tonnes,actor,payload.notes))
            after=cursor.fetchone()
            db._configuration_audit(cursor,'set_weekly_tonnage_target',actor,'weekly_tonnage_target',before,after)
        connection.commit()
    return {'status':'success','target':after}

@router.post('/management/live-weekly-target')
def set_site_target(payload:SiteTarget,actor=Depends(management_auth.require_management_session)):
    try:return save_site_target(payload,actor)
    except HTTPException:raise
    except db.psycopg.errors.ExclusionViolation as error:
        raise HTTPException(409,'This week overlaps an existing site target.') from error
    except Exception as error:
        log_operation_failure('management','live_weekly_target',error)
        raise HTTPException(503,'Could not save weekly target.') from error
