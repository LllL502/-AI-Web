"""验证补录清单的范围和来源，不将临时主校区算作覆盖。"""
import json
from pathlib import Path
from urllib.parse import urlparse
from apps.stations.management.commands.enrich_campuses import C9, OTHER985, OTHER211


def test_target_catalog_has_official_sources_for_every_priority_school():
    root=Path(__file__).resolve().parents[2]/'data/schools'
    rows=[]
    for path in root.glob('verified-campuses*.json'):
        rows.extend(json.loads(path.read_text(encoding='utf-8'))['schools'])
    targets=set(C9+OTHER985+OTHER211+['海军军医大学','空军军医大学'])
    covered={row['school'] for row in rows if row['campuses']}
    assert len(targets)==115
    assert targets <= covered
    for row in rows:
        assert (urlparse(row['source']).hostname or '').endswith('.edu.cn')
        assert row['campuses']
        assert len(set(row['campuses']))==len(row['campuses'])


def test_expansion_adds_thirty_distinct_schools_with_sources():
    root=Path(__file__).resolve().parents[2]/'data/schools'
    data=json.loads((root/'verified-campuses-expanded.json').read_text(encoding='utf-8'))
    names={row['school'] for row in data['schools']}
    existing=set()
    for path in root.glob('verified-campuses*.json'):
        if path.name != 'verified-campuses-expanded.json':
            existing.update(row['school'] for row in json.loads(path.read_text(encoding='utf-8'))['schools'])
    assert len(names)==30
    assert names.isdisjoint(existing)
    assert sum(len(row['campuses']) for row in data['schools'])==76


def test_local_batch_adds_thirty_new_schools_and_69_records():
    root=Path(__file__).resolve().parents[2]/'data/schools'
    data=json.loads((root/'verified-campuses-local.json').read_text(encoding='utf-8'))
    names={row['school'] for row in data['schools']}
    prior=set()
    for path in root.glob('verified-campuses*.json'):
        if path.name!='verified-campuses-local.json':
            prior.update(row['school'] for row in json.loads(path.read_text(encoding='utf-8'))['schools'])
    assert len(names)==30
    assert names.isdisjoint(prior)
    assert sum(len(row['campuses']) for row in data['schools'])==69
