import json
from pathlib import Path
import pytest
from django.conf import settings
from apps.assistant.benchmark import validate_dataset, eligible_candidates, metrics, candidate_text, query_text


def dataset(version='v1'):
    return json.loads((Path(settings.BASE_DIR).parent/f'data/benchmark/assistant-fixed-{version}.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('version', ['v1', 'v2'])
def test_fixed_dataset_split_and_visibility_contract(version):
    data = dataset(version)
    validate_dataset(data)
    assert len(data['queries']) == 24
    assert len(eligible_candidates(data)) == 12
    assert not any(row['id'].startswith('x') for row in eligible_candidates(data))
    for split in ['development', 'validation']:
        rows = [q for q in data['queries'] if q['split'] == split]
        assert len(rows) == 12
        assert sum(not row['gold'] for row in rows) == 4


def test_gold_outside_public_corpus_is_rejected():
    data = dataset()
    data['queries'][0]['gold'] = ['x01']
    with pytest.raises(ValueError):
        validate_dataset(data)


def test_object_leakage_between_splits_is_rejected():
    data = dataset()
    data['queries'][-1]['gold'] = ['c01']
    with pytest.raises(ValueError):
        validate_dataset(data)


def test_metrics_count_no_answer_false_returns_separately():
    rows = [
        {'gold': ['a'], 'rankings': {'method': [{'id':'a'}]}},
        {'gold': ['b'], 'rankings': {'method': [{'id':'a'}, {'id':'b'}]}},
        {'gold': [], 'rankings': {'method': [{'id':'a'}]}},
    ]
    result = metrics(rows, 'method')
    assert result['recall_at_1'] == .5
    assert result['recall_at_3'] == 1
    assert result['mrr_at_5'] == .75
    assert result['no_answer_false_return_rate'] == 1


def test_embedding_input_does_not_include_gold_ids_or_split():
    data = dataset()
    inputs = [candidate_text(row) for row in eligible_candidates(data)] + [query_text(row) for row in data['queries']]
    assert not any('validation' in text or 'development' in text for text in inputs)
    assert not any(target in text for query in data['queries'] for target in query['gold'] for text in inputs)
