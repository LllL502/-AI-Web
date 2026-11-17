"""Verify recovered bytes and prepare history navigation for publication."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT / 'deliverables/森林冰火人_寻迹_提交材料_20261117/代码仓库'
def git(*args):
    return subprocess.check_output(['git', '-C', str(REPO), *args])

attribute = REPO / '.gitattributes'
text = attribute.read_text('utf-8')
if 'history/versions/** -text' not in text:
    attribute.write_text(text + '\n# Historical source bytes follow their original manifests.\nhistory/versions/** -text\n', 'utf-8')
doc = ROOT / 'docs/submission/历史版本归档说明.md'
shutil.copy2(doc, REPO / 'docs/submission' / doc.name)
for base in [ROOT, REPO]:
    readme = base / 'README.md'
    text = readme.read_text('utf-8')
    old = '本次上传前，本地父级Git仓库没有任何提交，新建远程仓库亦为空。因此没有可迁移的历史Git提交；本仓库从本次真实整理开始记录，不补造早期作者、日期或提交。`docs/`中的阶段记录可作为过程材料，但不能替代原始Git历史。后续修改应正常提交并保留历史，禁止为凑提交数拆造历史。'
    new = '历史版本此前保存在本地，未逐次同步到远程仓库。现已保留全部已有Git提交，并补充10月9日前端、10月15日前后端框架、11月15日前端及两份本地源码快照，附原始交付记录和文件校验清单。详见[历史版本与真实开发过程](docs/submission/历史版本归档说明.md)。本次归档使用实际提交时间，原版本时间依据单独记录，不倒填日期，也不补造早期逐次提交。'
    if old in text:
        readme.write_text(text.replace(old, new), 'utf-8')
for name in ['archive_recovered_history.py', 'finalize_history_archive.py']:
    shutil.copy2(ROOT / 'scripts' / name, REPO / 'scripts' / name)
git('add', '--', '.gitattributes')
git('add', '--renormalize', '--', 'history/versions')
results = []
for snapshot in sorted((REPO / 'history/versions').iterdir()):
    metadata = json.loads((snapshot / 'snapshot.json').read_text('utf-8'))
    for relative, expected in metadata['files'].items():
        path = snapshot / relative
        content = git('show', ':' + path.relative_to(REPO).as_posix())
        if hashlib.sha256(content).hexdigest() != expected['sha256']:
            raise RuntimeError('Staged content does not match original: ' + str(path))
    results.append({'id': metadata['id'], 'verified_files': len(metadata['files']), 'mismatches': 0})
report = {'snapshots': results, 'total_verified': sum(r['verified_files'] for r in results), 'scope': '逐一核验Git暂存区实际字节与原始源码快照清单一致，不是仅核对工作目录'}
(REPO / 'evidence/history/recovered-source-verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf-8')
git('add', '--', 'README.md', 'docs/submission/历史版本归档说明.md', 'scripts/archive_recovered_history.py', 'scripts/finalize_history_archive.py', 'evidence/history/recovered-source-verification.json')
print(json.dumps(report, ensure_ascii=False))
