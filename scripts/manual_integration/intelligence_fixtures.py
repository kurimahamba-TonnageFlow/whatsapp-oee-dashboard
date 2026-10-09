"""Synthetic preview records passed through the real operational calculations."""
from copy import deepcopy
from datetime import date
from pathlib import Path
import json
from fastapi.encoders import jsonable_encoder
from scripts.manual_integration.live_dashboard_fixtures import source, NOW
from src.operational_intelligence import build_intelligence
from src.live_dashboard import reporting_week
from src.intelligence_api import deployment_capabilities


def fixtures():
    data = source()
    data['stoppages'][0].update(reference_pack_weight_kg=1, reference_packs_per_case=10, reference_cases_per_pallet=100)
    empty = deepcopy(data)
    for key in ['runs', 'readings', 'planned', 'faults', 'stoppages', 'targets']: empty[key] = []
    unscheduled = deepcopy(data)
    unscheduled['runs'] = [r for r in unscheduled['runs'] if r['id'] != 2]
    unscheduled['readings'] = [r for r in unscheduled['readings'] if r['production_run_id'] != 2]
    unscheduled['planned'] = []
    unscheduled['stoppages'][0].update(kind='not_scheduled', started_at=NOW.replace(hour=0, minute=0))
    return {key: jsonable_encoder({**build_intelligence(value, reporting_week(date(2026, 10, 5)), NOW), 'capabilities': deployment_capabilities()})
            for key, value in [('normal', data), ('empty', empty), ('unscheduled', unscheduled)]}

if __name__ == '__main__':
    Path('frontend/preview/intelligence-fixtures.json').write_text(json.dumps(fixtures(), indent=2), encoding='utf-8')
