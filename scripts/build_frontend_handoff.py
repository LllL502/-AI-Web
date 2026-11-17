"""Produce a reproducible frontend handoff plus private merge baselines."""
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ID = 'xunji-frontend-20261115-v1'
OUT = ROOT.parent / 'output' / 'frontend-handoff'
PACKAGE = OUT / ID
BASE = ROOT / 'artifacts' / 'handoff-baselines' / ID
FILES = ['index.html', 'package.json', 'package-lock.json', 'vite.config.ts', 'vitest.config.ts',
         'playwright.config.ts', 'tsconfig.json', 'tsconfig.app.json', 'tsconfig.node.json']


def manifest(folder):
    return {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(folder.rglob('*')) if p.is_file()}


def main():
    if PACKAGE.exists() or BASE.exists():
        raise RuntimeError('Handoff ID already exists; do not overwrite a shared baseline.')
    front = PACKAGE / 'frontend'
    front.mkdir(parents=True)
    for directory in ['src', 'public', 'tests']:
        shutil.copytree(ROOT / 'frontend' / directory, front / directory,
            ignore=shutil.ignore_patterns('.env*', '__pycache__', '.DS_Store', '*.tsbuildinfo'))
    for name in FILES:
        shutil.copy2(ROOT / 'frontend' / name, front / name)
    BASE.mkdir(parents=True)
    shutil.copytree(front, BASE / 'original-frontend')
    original = manifest(front)
    (BASE / 'original-sha256.json').write_text(json.dumps(original, indent=2), encoding='utf-8')
    shutil.copy2(ROOT / 'scripts/handoff-preview.ts', front / 'handoff-preview.ts')
    config = (front / 'vite.config.ts').read_text(encoding='utf-8')
    config = "import designPreview from './handoff-preview'\n" + config.replace(
        'plugins: [vue(), previewCacheHeaders]', 'plugins: [designPreview(), vue(), previewCacheHeaders]')
    (front / 'vite.config.ts').write_text(config, encoding='utf-8')
    (front / 'scripts').mkdir()
    (front / 'scripts/design-preview.mjs').write_text("import { createServer } from 'vite';\nprocess.env.CAMPUS_TRACE_DESIGN_PREVIEW='1';\nconst server=await createServer();await server.listen();server.printUrls();\n", encoding='utf-8')
    package = json.loads((front / 'package.json').read_text(encoding='utf-8'))
    package['scripts']['dev:design'] = 'node scripts/design-preview.mjs'
    (front / 'package.json').write_text(json.dumps(package, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    (front / 'public/design-assets').mkdir(exist_ok=True)
    for name in ['black-earbuds.png', 'black-umbrella.png']:
        shutil.copy2(ROOT / 'data/demo-images' / name, front / 'public/design-assets' / name)
    shutil.copy2(ROOT / 'scripts/frontend-handoff-guide.md', PACKAGE / '开始阅读.md')
    docs = PACKAGE / 'reference'
    docs.mkdir()
    for name in ['03_API与权限合同.md','23_AI工作流与结构化协议.md','25_AI寻物六因子重排.md','26_第九届网站改版记录.md']:
        shutil.copy2(ROOT / 'docs' / name, docs / name)
    delivered = manifest(front)
    (PACKAGE / 'baseline-sha256.json').write_text(json.dumps(delivered, indent=2), encoding='utf-8')
    (PACKAGE / 'handoff.json').write_text(json.dumps({'id': ID, 'original_frontend': original,
        'delivered_frontend': delivered, 'handoff_only': ['handoff-preview.ts','scripts/design-preview.mjs','public/design-assets'],
        'adapted_for_handoff': ['vite.config.ts','package.json']}, indent=2), encoding='utf-8')
    shutil.copy2(PACKAGE / 'handoff.json', BASE / 'handoff.json')
    archive = OUT / f'{ID}.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for path in sorted(PACKAGE.rglob('*')):
            if path.is_file():
                z.write(path, path.relative_to(OUT))
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        assert not any('/node_modules/' in n or '/.env' in n or '/dist/' in n for n in z.namelist())
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix('.zip.sha256').write_text(digest+'  '+archive.name+'\n', encoding='utf-8')
    print(json.dumps({'archive': str(archive), 'bytes': archive.stat().st_size, 'files': len(delivered), 'sha256': digest}, indent=2))


if __name__ == '__main__':
    main()
