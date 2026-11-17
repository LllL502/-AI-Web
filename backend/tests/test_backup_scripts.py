"""Exercise the real POSIX scripts with controlled Docker process failures."""
import io
import os
from pathlib import Path
import shutil
import subprocess
import tarfile

import pytest

ROOT = Path(__file__).resolve().parents[2]
BASH = shutil.which('bash') or ('C:/Program Files/Git/bin/bash.exe' if Path('C:/Program Files/Git/bin/bash.exe').exists() else None)
pytestmark = pytest.mark.skipif(not BASH, reason='POSIX shell unavailable')


@pytest.fixture
def backup_runtime(tmp_path):
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    archive = tmp_path / 'sample.tar.gz'
    with tarfile.open(archive, 'w:gz') as tar:
        data = b'real-media-fixture'
        info = tarfile.TarInfo('items/photo.webp')
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    docker = bin_dir / 'docker'
    docker.write_text('''#!/bin/sh
case "$*" in
 *mysqldump*)
   if [ "$BACKUP_TEST_MODE" = dump_fail ]; then printf partial; exit 17; fi
   printf 'CREATE TABLE restored (id INT); INSERT INTO restored VALUES (1);\n';;
 *tar*)
   if [ "$BACKUP_TEST_MODE" = media_fail ]; then printf partial; exit 18; fi
   cat "$BACKUP_TEST_ARCHIVE";;
 *information_schema*) printf '1\n';;
 *mysql*-e*) exit 0;;
 *mysql*) cat >/dev/null;;
 *) exit 19;;
esac
''', encoding='utf-8', newline='\n')
    docker.chmod(0o755)
    backup = tmp_path / 'backups'
    backup.mkdir()
    old = backup / 'backup-20000101T000000Z-1'
    old.mkdir()
    (old / 'keep').write_text('previous successful backup')
    os.utime(old, (1, 1))
    env = {**os.environ, 'PATH': str(bin_dir) + os.pathsep + os.environ['PATH'],
           'CAMPUS_TRACE_BACKUP_DIR': backup.as_posix(), 'BACKUP_TEST_ARCHIVE': archive.as_posix(), 'BACKUP_TEST_MODE': 'success'}
    return backup, old, env


@pytest.mark.parametrize('mode', ['dump_fail', 'media_fail'])
def test_failed_backup_does_not_publish_or_prune(backup_runtime, mode):
    backup, old, env = backup_runtime
    result = subprocess.run([BASH, str(ROOT / 'deploy/backup.sh')], env={**env, 'BACKUP_TEST_MODE':mode}, capture_output=True)
    assert result.returncode != 0, result.stdout
    assert list(backup.iterdir()) == [old]


def test_successful_backup_checksums_and_restore_validation(backup_runtime):
    backup, old, env = backup_runtime
    result = subprocess.run([BASH, str(ROOT / 'deploy/backup.sh')], env=env, capture_output=True)
    assert result.returncode == 0, result.stderr
    bundles = list(backup.glob('backup-*'))
    assert len(bundles) == 1 and not old.exists()
    bundle = bundles[0]
    assert {p.name for p in bundle.iterdir()} == {'database.sql.gz', 'media.tar.gz', 'SHA256SUMS'}
    result = subprocess.run([BASH, str(ROOT / 'deploy/verify-backup.sh'), bundle.as_posix()], env=env, capture_output=True)
    assert result.returncode == 0, result.stderr
    (bundle / 'database.sql.gz').write_bytes(b'corrupted')
    result = subprocess.run([BASH, str(ROOT / 'deploy/verify-backup.sh'), bundle.as_posix()], env=env, capture_output=True)
    assert result.returncode != 0
