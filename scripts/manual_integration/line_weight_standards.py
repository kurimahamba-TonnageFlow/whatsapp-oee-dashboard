"""Local-only PostgreSQL rehearsal; never reads .env or production credentials."""
import uuid
from pathlib import Path
import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parents[2]
BASE = "host=127.0.0.1 port=65439 user=postgres connect_timeout=5"
name = "standard_test_" + uuid.uuid4().hex[:12]
with psycopg.connect(BASE + " dbname=postgres", autocommit=True) as admin:
    admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        with psycopg.connect(BASE + " dbname=" + name, autocommit=True) as c:
            for role in ("anon", "authenticated"):
                if not c.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)).fetchone():
                    c.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(role)))
            c.execute("""CREATE TABLE production_runs (
                id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                production_line text, product text, pack_type text,
                pack_weight_kg numeric, packs_per_case integer, cases_per_pallet integer,
                started_at timestamptz, target_speed_ppm numeric)""")
            for filename in ("20261005054638_fixed_production_standard.sql",
                             "20261005135527_management_production_standards.sql",
                             "20261006021758_task_observations.sql"):
                c.execute((ROOT / "migrations" / filename).read_text())
            legacy = c.execute("""INSERT INTO production_standard_versions
              (production_line, product, pack_type, pack_weight_kg, packs_per_case,
               cases_per_pallet, standard_speed_ppm, effective_at, manager_name, reason)
              VALUES ('Rovema','Rice','Pillow',1,10,100,120,'2026-01-01','Manager','Original')
              RETURNING id""").fetchone()[0]
            run = c.execute("""INSERT INTO production_runs
              (production_line,product,pack_type,pack_weight_kg,packs_per_case,cases_per_pallet,started_at)
              VALUES ('Rovema','Rice','Pillow',1,10,100,'2026-02-01') RETURNING id""").fetchone()[0]
            c.execute((ROOT / "migrations/20261008232014_line_weight_production_standards.sql").read_text())
            def resolve(line, weight, product, at):
                return c.execute("SELECT id, standard_speed_ppm FROM resolve_production_standard(%s,%s,%s,'Pillow',10,100,%s)",
                                 (line,weight,product,at)).fetchone()
            assert resolve('Rovema',1,'Rice','2026-02-01')[0] == legacy
            assert resolve('Rovema',1,'Other','2026-02-01') is None
            simple = c.execute("""INSERT INTO production_standard_versions
              (production_line,pack_weight_kg,standard_speed_ppm,effective_at,manager_name,reason)
              VALUES ('Rovema',1,130,'2026-03-01','Manager','Line weight baseline') RETURNING id""").fetchone()[0]
            assert resolve('Rovema',1,'Other','2026-03-01')[0] == simple
            assert resolve('Rovema',1,'Rice','2026-03-01')[0] == simple
            assert resolve('Rovema',1,'Rice','2026-02-01')[0] == legacy
            assert resolve('GIC',1,'Other','2026-03-01') is None
            assert resolve('Rovema',2,'Other','2026-03-01') is None
            assert c.execute('SELECT standard_speed_ppm,standard_version_id FROM production_runs WHERE id=%s',(run,)).fetchone() == (120,legacy)
            assert c.execute("""INSERT INTO production_runs
              (production_line,product,pack_type,pack_weight_kg,packs_per_case,cases_per_pallet,started_at)
              VALUES ('Rovema','Other','Different',1,6,80,'2026-04-01')
              RETURNING standard_speed_ppm,standard_version_id""").fetchone() == (130,simple)
            try:
                c.execute('UPDATE production_runs SET standard_speed_ppm=999 WHERE id=%s',(run,))
                raise AssertionError('Historical snapshot was editable')
            except psycopg.errors.RaiseException:
                pass
            print('PASS: migration, legacy matching, line/weight scope, effective times, run selection and immutable snapshots')
    finally:
        admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))
