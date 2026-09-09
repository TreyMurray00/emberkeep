"""Keep integration-test state separate from the live local playtest database."""
import os
from pathlib import Path
import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

root=Path(__file__).resolve().parents[1]
for line in (root/'.env').read_text().splitlines():
    if '=' in line and not line.startswith('#'):
        key,value=line.split('=',1)
        os.environ.setdefault(key,value)

base=os.environ['DATABASE_URL']
test_name='emberkeep_test'
with psycopg.connect(base,autocommit=True) as connection:
    if not connection.execute('SELECT 1 FROM pg_database WHERE datname=%s',(test_name,)).fetchone():
        connection.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(test_name)))
os.environ['DATABASE_URL']=make_conninfo(base,dbname=test_name)
