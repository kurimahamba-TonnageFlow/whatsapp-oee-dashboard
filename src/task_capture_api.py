"""Independent task observations: never create production downtime."""
from datetime import datetime, timezone
from decimal import Decimal
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator, model_validator
from . import database as db
from .hmi_auth import require_device
from .main import line_technicians_by_line
from .task_performance import TASKS
from .catalogue import canonical
from .api_idempotency import IdempotencyKey, build_idempotency, run_idempotent_write

router = APIRouter(prefix="/api/v1/task-observations", tags=["task observations"])

class Observation(BaseModel):
    production_line: str = "Rovema"
    task: str
    technician: str
    started_at: datetime
    ended_at: datetime
    product: str = Field(min_length=1, max_length=120)
    from_configuration: str = Field(min_length=1, max_length=300)
    to_configuration: str = Field(min_length=1, max_length=300)
    waiting_minutes: Decimal = Field(ge=0)
    shared_work: bool
    completed_successfully: bool
    notes: str = Field(max_length=2000)

    @field_validator("product", "from_configuration", "to_configuration")
    @classmethod
    def nonblank(cls, value):
        if not value.strip(): raise ValueError("Configuration must be recorded")
        return value.strip()

    @model_validator(mode="after")
    def valid(self):
        if self.production_line != "Rovema" or self.task not in TASKS:
            raise ValueError("Choose a Rovema task")
        if self.technician not in line_technicians_by_line["Rovema"]:
            raise ValueError("Choose a known Rovema technician")
        if any(t.tzinfo is None or t.utcoffset() is None for t in (self.started_at,self.ended_at)):
            raise ValueError("Task times must include a timezone")
        if self.ended_at <= self.started_at or self.ended_at > datetime.now(timezone.utc):
            raise ValueError("Record a completed task with valid past start/end times")
        if self.waiting_minutes > Decimal(str((self.ended_at-self.started_at).total_seconds()/60)):
            raise ValueError("Waiting cannot exceed elapsed time")
        if (self.waiting_minutes > 0 or self.shared_work or not self.completed_successfully) and not self.notes.strip():
            raise ValueError("Describe waiting, shared work or incomplete results")
        self.product = canonical("product", self.product)
        return self

def save_observation(values, device_name, idempotency=None):
    with db.get_database_connection() as connection:
        with connection.cursor(row_factory=db.dict_row) as cursor:
            db._claim_idempotency(cursor, connection, idempotency)
            cursor.execute("""INSERT INTO public.task_observations
             (production_line,task,technician,started_at,ended_at,product,from_configuration,to_configuration,
              waiting_minutes,shared_work,completed_successfully,notes,device_name)
             VALUES (%(production_line)s,%(task)s,%(technician)s,%(started_at)s,%(ended_at)s,%(product)s,
              %(from_configuration)s,%(to_configuration)s,%(waiting_minutes)s,%(shared_work)s,%(completed_successfully)s,%(notes)s,%(device_name)s)
             ON CONFLICT (production_line,task,technician,started_at) DO NOTHING RETURNING id""", {**values,"device_name":device_name})
            row=cursor.fetchone()
            if row is None: raise db.PulseCaptureError(409,"A task with this start time is already recorded. Review the existing evidence.")
            result={"status":"saved","id":row["id"]}
            db._store_idempotent_response(cursor,idempotency,result)
        connection.commit()
    return result

@router.post("",status_code=201)
def capture(payload: Observation, key: IdempotencyKey, device=Depends(require_device)):
    idem=build_idempotency(key,"task_observation",payload,201,lambda r:r)
    return run_idempotent_write("task_observation",save_observation,payload.model_dump(),device["device_name"],idempotency=idem)
