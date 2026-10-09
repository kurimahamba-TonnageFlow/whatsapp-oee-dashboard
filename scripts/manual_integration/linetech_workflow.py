"""Destructive ONLY to a newly created local test database; never accepts a remote URL.

Usage: python -m scripts.manual_integration.linetech_workflow
Requires the local pulse_linetech preview schema on 127.0.0.1:5432.
"""
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Json
from src import database as db
from src.linetech_api import initial_config, update_verification, Verification, Cancellation, configuration, save_config
from src.linetech import LineTechConfig
from src.api_idempotency import build_idempotency
from src.pulse_capture_api import LineStoppageStartRequest

ADMIN = "postgresql://postgres@127.0.0.1:5432/postgres?connect_timeout=3"
NAME = "pulse_linetech_test_" + uuid4().hex[:10]
URL = f"postgresql://postgres@127.0.0.1:5432/{NAME}?connect_timeout=3"
NOW = datetime.now(timezone.utc)


def connect():
    return psycopg.connect(URL, row_factory=dict_row)


def reset():
    with connect() as c:
        tables = c.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'").fetchall()
        c.execute(sql.SQL("TRUNCATE {} RESTART IDENTITY CASCADE").format(sql.SQL(',').join(sql.Identifier('public', t['tablename']) for t in tables)))
        line = c.execute("INSERT INTO production_lines(name) VALUES ('Rovema') RETURNING id").fetchone()['id']
        machine = c.execute("INSERT INTO machines(production_line_id,name) VALUES (%s,'SBS Bagger BV1') RETURNING id", (line,)).fetchone()['id']
        button = c.execute("INSERT INTO buttons(machine_id,name,event_type,ownership) VALUES (%s,'Film Torn','unplanned_fault','Production') RETURNING id", (machine,)).fetchone()['id']
        config = initial_config([{'id': machine, 'name': 'SBS Bagger BV1', 'active': True, 'buttons': [{'id': button, 'name': 'Film Torn', 'event_type': 'unplanned_fault'}]}])
        config.update(enabled=True, formats=['1 kg x 10', '1 kg x 8'], sizes=['0.5', '1', '2'])
        c.execute('UPDATE production_lines SET linetech_config=%s WHERE id=%s', (Json(config), line))
        for weight in [0.5, 1, 2]:
            c.execute("""INSERT INTO production_standard_versions(production_line,pack_weight_kg,standard_speed_ppm,effective_at,manager_name,reason)
                VALUES ('Rovema',%s,120,%s,'Preview manager','Synthetic integration fixture')""", (weight, NOW-timedelta(days=1)))
    return machine, button


def run(product='White Basmati', weight=1, format='1 kg x 10'):
    return dict(production_line='Rovema', line_technician='Liam', shift='Days', customer='Aldi', product=product,
        pack_weight_kg=weight, packs_per_case=10, pack_type=format, format=format, cases_per_pallet=100,
        starting_pallets_remaining=10, pallets_remaining=10, previous_run_completed=0)


def ended_run():
    created = db.create_production_run(run())
    with connect() as c:
        c.execute("UPDATE production_runs SET status='Completed',finished_at=now() WHERE id=%s", (created['id'],))
    return created['id']


def conflict(call):
    try:
        call()
    except db.PulseCaptureError as error:
        assert error.status_code in [409, 422], error
    else:
        raise AssertionError('An invalid transition succeeded')


def scenario(kind, next_value):
    reset(); previous = ended_run()
    payload=LineStoppageStartRequest(kind='changeover',started_by='Liam',changeover_selection={'kind':kind,'next_value':next_value})
    identity=build_idempotency(uuid4().hex,'local-changeover',payload,201,lambda x:{'stoppage_id':x['stoppage']['id']})
    result=db.start_line_stoppage('Rovema','changeover',None,'Liam',datetime.now(timezone.utc),idempotency=identity,changeover_selection=payload.changeover_selection)
    stop=result['stoppage']['id']; assert result['changeover']['previous_production_run_id']==previous
    try:
        db.start_line_stoppage('Rovema','changeover',None,'Liam',datetime.now(timezone.utc),idempotency=identity,changeover_selection=payload.changeover_selection)
    except db.IdempotentReplay as replay:
        assert replay.body['stoppage_id']==stop
    else:
        raise AssertionError('Retry was not replayed')
    conflict(lambda:db.start_line_stoppage('Rovema','changeover',None,'Liam',datetime.now(timezone.utc),changeover_selection=payload.changeover_selection))
    new=run(**{'product':next_value} if kind=='product' else {'weight':float(next_value)} if kind=='size' else {'format':next_value})
    conflict(lambda:db.create_production_run(new))
    jobs=db.get_casepacker_requests(stop)
    assert len(jobs)==(0 if kind=='product' else 1)
    if jobs:
        job=jobs[0]['id']; db.update_casepacker_request(job,'accept','Alfie','',datetime.now(timezone.utc))
        conflict(lambda:db.update_casepacker_request(job,'ready','Other engineer','Incorrect owner',datetime.now(timezone.utc)))
        db.update_casepacker_request(job,'handover','Alfie','Guide setting recorded; next engineer to check program',datetime.now(timezone.utc))
        db.update_casepacker_request(job,'accept','Aaron','',datetime.now(timezone.utc))
        db.update_casepacker_request(job,'ready','Aaron','Program and guide settings verified',datetime.now(timezone.utc))
    conflict(lambda:db.create_production_run(new))  # Engineering complete is NOT restart.
    verification=Verification(technician='Liam',first_off=True,label=True,date_code=True,ccp=True,reference='LOCAL-QA-001')
    conflict(lambda:update_verification(stop,verification))  # Physical work not confirmed.
    db.end_line_stoppage(stop,'Liam',datetime.now(timezone.utc))
    conflict(lambda:db.create_production_run(new))  # Still awaiting verification.
    failed=verification.model_copy(update={'ccp':False})
    conflict(lambda:update_verification(stop,failed))
    update_verification(stop,verification)
    conflict(lambda:db.create_production_run(run()))  # Wrong new configuration.
    created=db.create_production_run(new)
    with connect() as c:
        row=c.execute('SELECT * FROM line_stoppages WHERE id=%s',(stop,)).fetchone()
        assert row['next_production_run_id']==created['id'] and row['ended_at']>=row['physical_ended_at']
        assert c.execute('SELECT count(*) AS n FROM line_stoppages').fetchone()['n']==1
        assert c.execute('SELECT workflow FROM changeovers WHERE line_stoppage_id=%s',(stop,)).fetchone()['workflow']['qa_status']=='verified'
    print(f'PASS {kind}: linked job, replay, owner, physical/QA/restart guards, one production clock')


def cancellation():
    reset();ended_run()
    stop=db.start_line_stoppage('Rovema','changeover',None,'Liam',datetime.now(timezone.utc),changeover_selection={'kind':'format','next_value':'1 kg x 8'})['stoppage']['id']
    job=db.get_casepacker_requests(stop)[0]['id']
    update_verification(stop,Cancellation(technician='Liam',reason='Order cancelled before setup'),True)
    conflict(lambda:db.update_casepacker_request(job,'accept','Alfie','',datetime.now(timezone.utc)))
    with connect() as c:
        assert c.execute('SELECT ended_at FROM line_stoppages WHERE id=%s',(stop,)).fetchone()['ended_at'] is None
    db.create_production_run(run())
    print('PASS cancellation: preserves production stop; cancels job; permits a deliberate new run')


def faults_and_planned():
    machine,button=reset();created=db.create_production_run(run());run_id=created['id']
    for reason,component in [('Film Change','BV1'),('Film Change','BV2'),('Label Change','Label 1'),('Label Change','Label 2'),('CCP Check',None)]:
        event=db.start_planned_downtime(run_id,reason,'Liam',datetime.now(timezone.utc),component=component)
        assert event['component']==component
        db.end_planned_downtime(event['id'],'Liam',datetime.now(timezone.utc))
    conflict(lambda:db.start_planned_downtime(run_id,'Film Change','Liam',datetime.now(timezone.utc),component='BV9'))
    report=dict(reported_by='Liam',machine='SBS Bagger BV1',reason='Film Torn',machine_id=machine,button_id=button,note=None)
    moment=datetime.now(timezone.utc)
    resolved=db.report_fault_to_engineering(run_id,{**report,'outcome':'resolved','started_at':created['started_at'],'restored_at':moment},moment)
    assert resolved['production_status']=='Resolved'
    called=db.report_fault_to_engineering(run_id,report,datetime.now(timezone.utc))
    assert called['production_status']=='Ongoing'
    waiting=db.report_fault_to_engineering(run_id,{**report,'outcome':'resolved_waiting_restart','started_at':created['started_at']},datetime.now(timezone.utc))
    with connect() as c:
        record=c.execute('SELECT * FROM downtime_events WHERE id=%s',(waiting['id'],)).fetchone()
        assert record['linetech_resolved_at'] is not None and record['resolved_at'] is None
        assert not record['engineer_called'] and record['production_status']=='Ongoing'
    print('PASS planned components/CCP stop and optional-note resolved preset; escalation leaves production stopped')


def management():
    machine,button=reset()
    settings=LineTechConfig.model_validate(configuration('Rovema')['config'])
    settings.groups[0].equipment[0].categories[0].name='Film handling'
    save_config('Rovema',settings,'Preview manager')
    with connect() as c:
        assert c.execute("SELECT count(*) AS n FROM management_audit_log WHERE action='linetech_configuration'").fetchone()['n']==1
    assert configuration('Rovema')['config']['groups'][0]['equipment'][0]['categories'][0]['button_ids']==[button]
    db.update_button(button,name='Film torn — checked label',audit_actor='Preview manager')
    assert db.get_button(button)['machine_id']==machine
    print('PASS Management configuration, audit record and preserved machine/button identities')


def main():
    with psycopg.connect(ADMIN,autocommit=True) as admin:
        admin.execute(sql.SQL('CREATE DATABASE {} TEMPLATE pulse_linetech').format(sql.Identifier(NAME)))
        db.DATABASE_URL=URL
        try:
            for kind,value in [('product','Brown Basmati'),('format','1 kg x 8'),('size','0.5')]:
                scenario(kind,value)
            cancellation();faults_and_planned();management()
        finally:
            admin.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(NAME)))

if __name__=='__main__':
    main()
