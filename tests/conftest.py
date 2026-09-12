"""Force integration tests onto a dedicated local PostgreSQL instance."""
import os
import psycopg

local_test_url='postgresql://emberkeep_test:emberkeep_test@127.0.0.1:55433/emberkeep_test'
test_url=os.environ.get('TEST_DATABASE_URL',local_test_url)
if '127.0.0.1' not in test_url and 'localhost' not in test_url:
    raise RuntimeError('TEST_DATABASE_URL must point to a local PostgreSQL instance.')
os.environ['DATABASE_URL']=test_url

try:
    with psycopg.connect(test_url,connect_timeout=3) as connection:
        connection.execute('SELECT 1')
except psycopg.OperationalError as exc:
    raise RuntimeError(
        'Local test PostgreSQL is unavailable. Start it with '
        '`docker compose -f compose.test.yaml up -d --wait`.'
    ) from exc
