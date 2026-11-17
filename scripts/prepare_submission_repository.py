"""Export an allowlisted review repository without runtime data or secrets."""
from pathlib import Path
import hashlib
import json
import os
import shutil

ROOT=Path(__file__).resolve().parents[1]
PACKAGE=ROOT/'deliverables/森林冰火人_寻迹_提交材料_20261117'
DEST=PACKAGE/'代码仓库'
if not (DEST/'.git').is_dir():
    raise RuntimeError('Clone the designated repository first; never replace an existing repository.')
SKIP_DIRS={'.git','.venv','node_modules','dist','__pycache__','.pytest_cache','.tmp','media','public-media','staticfiles','playwright-report','test-results'}
def permitted(path):
    if path.is_symlink():return False
    name=path.name
    if name.startswith('.env') and not name.endswith('.example'):return False
    if name.endswith(('.pyc','.pyo','.tsbuildinfo','.log','.pid','.key','.pem','.part')):return False
    if name.startswith('pytest-cache-files'):return False
    return True
def copy_tree(relative, suffixes=None):
    source=ROOT/relative
    for folder,dirs,files in os.walk(source):
        dirs[:]=[d for d in dirs if d not in SKIP_DIRS and not d.startswith('pytest-cache-files')]
        for name in files:
            path=Path(folder)/name
            if not permitted(path) or (suffixes is not None and path.suffix not in suffixes):continue
            target=DEST/path.relative_to(ROOT)
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(path,target)
for directory in ['backend','frontend','scripts','deploy']:
    copy_tree(directory)
for directory in ['data/benchmark','data/demo-photos','data/demo-images','data/schools','data/seed','data/dictionaries','data/manifests']:
    if (ROOT/directory).exists():copy_tree(directory)
copy_tree('docs',{'.md'})
copy_tree('docs/submission',{'.md','.json','.png','.pdf'})
for name in ['README.md','CONTRIBUTING.md','THIRD_PARTY_NOTICES.md','.gitignore','.gitattributes','.editorconfig','.dockerignore','docker-compose.prod.yml']:
    shutil.copy2(ROOT/name,DEST/name)
evidence=DEST/'evidence'
evidence.mkdir(exist_ok=True)
mapping={}
for relative in [
    'artifacts/ten-fixes/verification-summary.json','artifacts/ten-fixes/real-dialogue.json',
    'artifacts/ten-fixes/dynamic-voice.json','artifacts/ten-fixes/dynamic-voice.wav',
    'artifacts/ten-fixes/browser-summary.json','artifacts/backend-fixes/local-restore.json',
]:
    target=evidence/Path(relative).name
    shutil.copy2(ROOT/relative,target)
    mapping[relative]=target.relative_to(DEST).as_posix()
for path in (ROOT/'artifacts/benchmark').glob('assistant-fixed-v2-*.json'):
    target=evidence/'benchmark'/path.name
    target.parent.mkdir(exist_ok=True)
    shutil.copy2(path,target)
    mapping[path.relative_to(ROOT).as_posix()]=target.relative_to(DEST).as_posix()
(evidence/'source-map.json').write_text(json.dumps(mapping,ensure_ascii=False,indent=2),encoding='utf-8')
(evidence/'README.md').write_text('# 验证证据\n\n这是精选的本地验证汇总，不含真实密钥、运行数据库或用户日志。阶段文档保留原路径，分发位置映射见source-map.json。benchmark目录为固定合成评测，不是真实校园找回率。动态童声是固定测试句，不是用户录音。\n',encoding='utf-8')

# Compare against actual local credentials in memory; never print their values.
private_values=[]
for file in [ROOT/'backend/.env',ROOT/'backend/.env.amap',ROOT/'deploy/.env.production']:
    if not file.exists():continue
    for line in file.read_text('utf-8').splitlines():
        if '=' not in line or line.lstrip().startswith('#'):continue
        key,value=line.split('=',1);value=value.strip().strip('"').strip("'")
        if any(marker in key.upper() for marker in ['SECRET','API_KEY','SECURITY_CODE','PASSWORD','AMAP_WEB_KEY']):
            if len(value)>=10 and value not in {'campustrace-local-only','ollama-local-placeholder','CampusTrace!2026'} and not value.startswith(('replace-','unsafe-development')):
                private_values.append((key,value.encode()))
manifest={}
violations=[]
for folder,dirs,files in os.walk(DEST):
    dirs[:]=[d for d in dirs if d!='.git']
    for name in files:
        path=Path(folder)/name;relative=path.relative_to(DEST).as_posix()
        data=path.read_bytes()
        if not permitted(path):violations.append({'file':relative,'reason':'excluded runtime or secret name'})
        if len(data)>90_000_000:violations.append({'file':relative,'reason':'oversized Git blob'})
        if path.suffix.lower() in {'.py','.ts','.vue','.md','.json','.yaml','.yml','.ps1','.sh','.cmd','.example','.lock','.in','.txt','.toml'}:
            for key,value in private_values:
                if value in data:violations.append({'file':relative,'reason':f'local credential value matches {key}'})
        manifest[relative]={'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
report={'files':len(manifest),'total_bytes':sum(v['bytes'] for v in manifest.values()),'credential_comparisons':len(private_values),'violations':violations,'remote':'https://github.com/LllL502/-AI-Web.git','original_local_history':'no commits','original_remote_history':'empty at clone'}
PACKAGE.mkdir(parents=True,exist_ok=True)
(PACKAGE/'源码文件校验.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
(PACKAGE/'敏感文件检查.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
if violations:
    print(json.dumps(report,ensure_ascii=True));raise RuntimeError('Export scan failed; do not push.')
print(json.dumps(report,ensure_ascii=True))
