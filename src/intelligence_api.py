"""Management-only production intelligence. Financial capability is unavailable."""
from datetime import datetime, timezone
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from . import management_auth, operational_intelligence as intelligence
from .api_logging import log_operation_failure

router = APIRouter(prefix='/api/v1/dashboard', tags=['operational-intelligence'],
                   dependencies=[Depends(management_auth.require_management_session)])


def deployment_capabilities():
    # Authoritative server policy for this single-factory deployment. Future
    # tenant entitlements belong here, derived from authenticated server scope.
    # Neither query parameters nor a client toggle can grant financial access.
    return {'production_intelligence': True, 'financial_intelligence': False,
            'scope': 'current_factory'}


def require_financial_intelligence():
    if not deployment_capabilities()['financial_intelligence']:
        raise HTTPException(403, 'Financial Intelligence is a separately agreed Phase 2 capability.')


class IntelligenceSnapshot(BaseModel):
    generated_at: datetime
    window: dict
    configured_lines: list[str]
    selected_line: str | None
    weekly: dict
    lines: list[dict]
    output_gap: dict
    downtime: dict
    loss_drivers: list[dict]
    ranking_method: str
    line_stops: dict
    material_flow: list[dict]
    data_issues: list[str]
    capabilities: dict


@router.get('/operational-intelligence', response_model=IntelligenceSnapshot)
def snapshot(window: Literal['production_week','current_shift','factory_day','rolling_24h']='production_week',
             production_line: str | None=None):
    now = datetime.now(timezone.utc)
    try:
        data, week = intelligence.load_data(now)
        if production_line and production_line not in data['lines']:
            raise HTTPException(422, 'Choose a configured production line.')
        return {**intelligence.build_intelligence(data, week, now, window, production_line),
                'capabilities': deployment_capabilities()}
    except HTTPException:
        raise
    except Exception as error:
        log_operation_failure('dashboard', 'operational_intelligence', error)
        raise HTTPException(503, 'Operational intelligence is temporarily unavailable.') from error


@router.get('/financial-intelligence', dependencies=[Depends(require_financial_intelligence)])
def financial_intelligence():
    # There is deliberately no financial result provider in this release.
    raise HTTPException(403, 'Financial Intelligence is not implemented in this release.')
