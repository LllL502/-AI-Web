import pytest
from apps.assistant.ranking import score_factors, resolve_hint, accept_candidate
from apps.matching.engine import FactorValue, DEFAULT_WEIGHTS, MatchingEngine, ItemFeature
from datetime import datetime, timezone


def test_missing_factors_do_not_count_as_mismatches():
    factors = {name: FactorValue(0, False) for name in DEFAULT_WEIGHTS}
    factors['text'] = FactorValue(.8, True)
    result = score_factors(factors, DEFAULT_WEIGHTS)
    assert result['score'] == pytest.approx(.8)
    assert result['penalty_multiplier'] == 1
    assert result['factors']['color'] is None


def test_explicit_color_conflict_is_penalized_and_explained():
    factors = {name: FactorValue(0, False) for name in DEFAULT_WEIGHTS}
    factors['text'] = FactorValue(.99, True)
    factors['color'] = FactorValue(0, True, conflict='颜色已知不同')
    result = score_factors(factors, DEFAULT_WEIGHTS)
    assert result['penalties'] == {'color': .55}
    assert result['score'] < .5
    assert '颜色已知不同' in result['conflicts']


@pytest.mark.parametrize('query_kind', ['LOST', 'FOUND'])
def test_time_conflict_is_symmetric_for_lost_and_found_queries(query_kind):
    lost = ItemFeature(id='lost', kind='LOST', public_text='耳机', event_start=datetime(2026, 1, 2, tzinfo=timezone.utc))
    found = ItemFeature(id='found', kind='FOUND', public_text='耳机', event_start=datetime(2026, 1, 1, tzinfo=timezone.utc))
    query, candidate = (lost, found) if query_kind == 'LOST' else (found, lost)
    factors = MatchingEngine().compute_factors(query, candidate, .9, True)
    result = score_factors(factors, DEFAULT_WEIGHTS)
    assert result['penalties']['time'] == .35
    assert '拾取时间早于遗失时间' in result['conflicts']


def test_ambiguous_category_is_missing_instead_of_guessed():
    assert resolve_hint('手机或耳机', [('手机', ('手机',)), ('耳机', ('耳机',))], str.strip) == ()


def test_acceptance_gate_preserves_unknown_fields_but_blocks_conflicts():
    assert accept_candidate({'score': .7, 'penalties': {}})
    assert not accept_candidate({'score': .59, 'penalties': {}})
    assert not accept_candidate({'score': .9, 'penalties': {'time': .35}})
    assert not accept_candidate({'score': .9, 'penalties': {'category': .25}})
    assert accept_candidate({'score': .6, 'penalties': {}})
