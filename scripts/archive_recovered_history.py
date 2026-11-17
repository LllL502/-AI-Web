"""Archive surviving source snapshots without changing historical commit dates."""
from pathlib import Path
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT.parent
REPO = ROOT / 'deliverables/森林冰火人_寻迹_提交材料_20261117/代码仓库'
SKIP = {'.git', '.venv', 'node_modules', 'dist', '__pycache__', '.pytest_cache', 'media', 'public-media', 'staticfiles', 'test-results', 'playwright-report'}
TEXT = {'.py', '.ts', '.vue', '.json', '.html', '.css', '.scss', '.txt', '.lock', '.toml', '.yaml', '.yml', '.example', '.in', '.svg'}

def git(*args):
    return subprocess.check_output(['git', '-C', str(REPO), *args], text=True, encoding='utf-8').strip()

def archive(identifier, source, parts, evidence):
    destination = REPO / 'history/versions' / identifier
    if destination.exists():
        raise RuntimeError('Snapshot already exists; refusing to replace it')
    manifest = {}
    # Collect private values from both current and surviving historical environments.
    private = []
    for base in [ROOT / 'backend', source / 'backend']:
        if not base.exists():
            continue
        for envfile in base.glob('.env*'):
            if not envfile.is_file() or envfile.name.endswith('.example'):
                continue
            for line in envfile.read_text('utf-8', errors='replace').splitlines():
                if '=' not in line or line.lstrip().startswith('#'):
                    continue
                key, value = line.split('=', 1)
                value = value.strip().strip('\"').strip("'")
                if re.search('SECRET|API_KEY|PASSWORD|SECURITY_CODE|AMAP_WEB_KEY', key, re.I) and len(value) >= 12 and not value.startswith(('replace-', 'unsafe-', 'campustrace-local', 'CampusTrace!')):
                    private.append(value.encode())
    for part in parts:
        base = source / part
        for folder, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d not in SKIP and not d.startswith('pytest-cache')]
            for name in files:
                path = Path(folder) / name
                relative = path.relative_to(source)
                if path.is_symlink() or (name.startswith('.env') and not name.endswith('.example')):
                    continue
                if path.suffix.lower() not in TEXT or name.endswith(('.tsbuildinfo', '.log')):
                    continue
                data = path.read_bytes()
                if any(value in data for value in private) or re.search(rb'(?:sk-[A-Za-z0-9]{24,}|gh[pousr]_[A-Za-z0-9]{20,}|-----BEGIN (?:RSA |OPENSSH )?PRIVATE KEY-----)', data):
                    raise RuntimeError('Credential scan blocked file: ' + str(relative))
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                manifest[relative.as_posix()] = {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
    if not manifest:
        raise RuntimeError('Empty snapshot')
    metadata = {'id': identifier, 'scope': parts, 'source_evidence': evidence, 'archived_at': __import__('datetime').datetime.now().astimezone().isoformat(), 'limitations': '原样恢复留存源码文本；未包含照片、构建产物、运行数据库、依赖及密钥。局部前端版本不代表当时完整项目状态。历史时间依据不是本次Git提交时间。', 'files': manifest}
    (destination / 'snapshot.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), 'utf-8')
    git('add', '--', str(destination.relative_to(REPO)))
    git('-c', 'user.name=森林冰火人（提交归档）', '-c', 'user.email=LllL502@users.noreply.github.com', 'commit', '-m', 'Archive surviving source snapshot: ' + identifier + ' (imported now)')
    print(json.dumps({'id': identifier, 'files': len(manifest), 'commit': git('rev-parse', 'HEAD')}, ensure_ascii=False))

if __name__ == '__main__':
    stage = sys.argv[1]
    if stage == 'oct09':
        archive('2026-10-09-frontend', ROOT / 'artifacts/handoff/frontend-20261009', ['frontend'], {'archive_sha256': 'e1b44f7f3e6dbd44e2c235f50737f858c9359d6822554ed8f2ef7ed882b87802', 'time_basis': '交接包名称及ZIP内部日期，仅作辅助时间标记'})
    elif stage == 'oct15':
        archive('2026-10-15-framework', WORK / 'CampusTrace_完整工程归档_20261015/01_CampusTrace完整源代码', ['backend', 'frontend'], {'archive_sha256': '52e4f84ff190a4c966e3b36873b9125e71290985fadc6b535e34e2fe4e3a4a78', 'delivery_record': '01a13b35-e4f0-7662-b16c-cde7650c486f', 'reported_delivery_at': '2026-10-15T00:24:42+08:00'})
    elif stage == 'nov15':
        archive('2026-11-15-frontend', ROOT / 'artifacts/handoff-baselines/xunji-frontend-20261115-v1', ['original-frontend'], {'archive_sha256': '79cc70b655e626a0238f0fde5671e099d15c43b82f88b9b2d4895ea5272f71ef', 'delivery_record': '01a1df3c-ef08-7c01-993c-93e8b1977de4', 'reported_delivery_at': '2026-11-15T20:56:32+08:00', 'baseline_check': '原始基线83个文件哈希全部一致；本次仅归档源码文本'})
    elif stage in {'checkpoint-a', 'checkpoint-b'}:
        tree = {'checkpoint-a': '469d1a53a3ad98949abb7affed5016c90459666a', 'checkpoint-b': '26e0aacdccde47f659fee644d863c533f35fe4c8'}[stage]
        source = ROOT / 'artifacts/history-evidence/recovered-trees' / tree
        names = subprocess.check_output(['git', '-C', str(WORK), 'ls-tree', '-r', '--name-only', tree, '--', 'app', 'campustrace/backend', 'campustrace/frontend'], encoding='utf-8').splitlines()
        for name in names:
            path = Path(name)
            if path.suffix.lower() not in TEXT or any(part in SKIP for part in path.parts) or path.name.startswith('.env'):
                continue
            target = source / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(subprocess.check_output(['git', '-C', str(WORK), 'show', tree + ':' + name]))
        archive('local-' + stage, source, ['app', 'campustrace/backend', 'campustrace/frontend'], {'original_git_tree': tree, 'time_basis': '本地快照引用中的时间线索，不能等同于普通Git提交时间或独立时间认证', 'scope': '留存树对象内的源码；不承诺覆盖完整工程'})
    else:
        raise RuntimeError('Unknown stage')
