"""Local MySQL restore drill; import to a disposable schema and compare every table."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.conf import settings
import MySQLdb

db = settings.DATABASES['default']
mysql_home = ROOT / 'tools/mysql-8.4.11-winx64/bin'
database = 'restore_check_' + uuid.uuid4().hex
# Local bootstrap root is restricted to the bundled development MySQL port.
if db['HOST'] != '127.0.0.1' or int(db['PORT']) != 3307:
    raise RuntimeError('This drill is only for the bundled local development database.')
conn = MySQLdb.connect(host=db['HOST'], port=3307, user='root', charset='utf8mb4')
cursor = conn.cursor()
media_root = Path(settings.MEDIA_ROOT)
args = ['--protocol=TCP', '--host=127.0.0.1', '--port=3307', '--user=root']
try:
    cursor.execute(f'CREATE DATABASE `{database}` CHARACTER SET utf8mb4')
    with tempfile.TemporaryDirectory(prefix='campustrace-restore-') as directory:
        work = Path(directory)
        dump = subprocess.run([str(mysql_home / 'mysqldump.exe'), *args, '--single-transaction', '--routines', '--triggers', '--no-tablespaces', db['NAME']], check=True, capture_output=True).stdout
        compressed = gzip.compress(dump)
        assert gzip.decompress(compressed) == dump
        subprocess.run([str(mysql_home / 'mysql.exe'), *args, '--binary-mode', database], input=gzip.decompress(compressed), check=True, capture_output=True)
        cursor.execute('SELECT table_name FROM information_schema.tables WHERE table_schema=%s', (db['NAME'],))
        tables = [row[0] for row in cursor.fetchall()]
        rows = 0
        for table in tables:
            cursor.execute(f'SELECT COUNT(*) FROM `{db["NAME"]}`.`{table}`')
            original = cursor.fetchone()[0]
            cursor.execute(f'SELECT COUNT(*) FROM `{database}`.`{table}`')
            assert cursor.fetchone()[0] == original, table
            rows += original
        conn.commit()
        archive = work / 'media.tar.gz'
        with tarfile.open(archive, 'w:gz') as tar:
            tar.add(media_root, arcname='media')
        with tarfile.open(archive, 'r:gz') as tar:
            tar.extractall(work / 'restored', filter='data')
        files = [path for path in media_root.rglob('*') if path.is_file()]
        for path in files:
            restored = work / 'restored/media' / path.relative_to(media_root)
            assert hashlib.sha256(path.read_bytes()).digest() == hashlib.sha256(restored.read_bytes()).digest()
        result = {'database_restore': 'passed', 'tables_compared': len(tables), 'rows_compared': rows,
                  'media_files_compared': len(files), 'media_restore': 'passed', 'temporary_database_dropped': True,
                  'scope': 'bundled local MySQL; Docker server drill must also run after deployment'}
finally:
    cursor.execute(f'DROP DATABASE IF EXISTS `{database}`')
    conn.close()
output = ROOT / 'artifacts/backend-fixes/local-restore.json'
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(result, ensure_ascii=True))
