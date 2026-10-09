"""Real SQL verification in a fresh LOCAL clone only. Never accepts a remote URL."""
from pathlib import Path
from uuid import uuid4
from datetime import datetime,timedelta,timezone,date
import json
import psycopg
from psycopg import sql
from src import database as db, live_dashboard as live
from src.live_dashboard_api import SiteTarget,save_site_target
from scripts.manual_integration import linetech_workflow as fixture


def main():
    name='pulse_live_test_'+uuid4().hex[:10]
    url=f'postgresql://postgres@127.0.0.1:5432/{name}?connect_timeout=3'
    with psycopg.connect(fixture.ADMIN,autocommit=True) as admin:
        admin.execute(sql.SQL('CREATE DATABASE {} TEMPLATE pulse_linetech').format(sql.Identifier(name)))
        try:
            db.DATABASE_URL=url;fixture.URL=url
            with psycopg.connect(url) as c:c.execute(next(Path('migrations').glob('*live_operations_targets.sql')).read_text())
            fixture.reset()
            run=db.create_production_run(fixture.run())
            now=datetime.now(timezone.utc)
            start=live.clock_hour_start(now)-timedelta(hours=1)
            with psycopg.connect(url) as c:
                c.execute('UPDATE production_runs SET started_at=%s WHERE id=%s',(start,run['id']))
            # Exercise actual HMI write, including correction-safe run progress.
            db.record_hourly_update(run['id'],start,3,'Liam','Synthetic preview',now)
            data,week=live.load_snapshot(now)
            output=live.build_snapshot(data,week,now)
            assert output['weekly']['actual_tonnes']==3
            assert output['lines'][0]['last_hour']['line']['actual_packs']==3000
            assert output['lines'][0]['job']['remaining_pallets']==7
            day=week.start.astimezone(live.FACTORY_TZ).date()
            saved=save_site_target(SiteTarget(week_start=day,week_start_day=day.weekday(),target_tonnes=6,notes='Local test'),'Local test manager')
            data,week=live.load_snapshot(now)
            assert live.build_snapshot(data,week,now)['weekly']['progress_percent']==50
            try:save_site_target(SiteTarget(week_start=day+timedelta(days=1),week_start_day=(day.weekday()+1)%7,target_tonnes=8),'Local test manager')
            except Exception as e:assert getattr(e,'status_code',None)==409
            else:raise AssertionError('Overlapping site targets accepted')
            with psycopg.connect(url) as c:
                assert c.execute("SELECT count(*) FROM management_audit_log WHERE action='set_weekly_tonnage_target'").fetchone()[0]==1
                assert c.execute("SELECT relrowsecurity FROM pg_class WHERE oid='public.weekly_tonnage_targets'::regclass").fetchone()[0]
            print('PASS local migration, actual HMI write, dashboard SQL, weighted output, reconciled pallets, audited target and overlap rejection; RLS retained')
        finally:admin.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))

if __name__=='__main__':main()
