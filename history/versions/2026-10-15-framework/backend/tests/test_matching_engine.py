from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from apps.matching.engine import (
    ChinesePreprocessor,
    FactorValue,
    ItemFeature,
    MatchingEngine,
    reference_tfidf,
)


def make_item(item_id: str, kind: str, text: str, **overrides) -> ItemFeature:
    base = {
        "owner_id": f"owner-{item_id}",
        "category_path": ("数码", "耳机"),
        "location_path": ("主校区", "图书馆"),
        "color_values": ("黑色",),
        "brand": "Sony",
        "event_start": datetime(2026, 9, 1, 8, tzinfo=timezone.utc),
    }
    base.update(overrides)
    return ItemFeature(id=item_id, kind=kind, public_text=text, **base)


def test_preprocessing_normalizes_aliases_and_keeps_negation():
    processor = ChinesePreprocessor(
        aliases={"校图": "图书馆"},
        stop_words={"的", "无"},
        custom_words={"图书馆", "充电盒"},
    )
    tokens = processor.tokenize("  校图 的 黑色耳机，无挂绳  ")
    assert "图书馆" in tokens
    assert "无" in tokens
    assert "的" not in tokens


def test_reference_tfidf_matches_sklearn_formula():
    processor = ChinesePreprocessor()
    documents = ["黑色 耳机 耳机", "蓝色 耳机", "校园卡"]
    index = MatchingEngine(processor).fit_index(
        [make_item(str(i), "FOUND", text) for i, text in enumerate(documents)]
    )
    tokens = [processor.tokenize(text) for text in documents]
    vocabulary, expected = reference_tfidf(tokens)
    actual_columns = list(index.vectorizer.get_feature_names_out())
    assert actual_columns == vocabulary
    np.testing.assert_allclose(index.matrix.toarray(), expected, rtol=1e-12, atol=1e-12)


def test_cosine_same_text_one_and_zero_vector_safe():
    engine = MatchingEngine()
    candidate = make_item("found", "FOUND", "黑色 sony 耳机")
    index = engine.fit_index([candidate])
    same = make_item("lost", "LOST", "黑色 sony 耳机")
    assert float((index.matrix @ engine.transform_query(same, index).T).toarray()[0, 0]) == pytest.approx(1.0)
    unseen = make_item("lost-2", "LOST", "完全未登录词xyz987")
    vector = engine.transform_query(unseen, index)
    assert vector.nnz == 0
    # 查询文本无法进入候选词表时，不再为了凑数返回“仅供浏览”结果。
    assert engine.rank(unseen, index) == []


def test_six_factor_arithmetic_and_missing_brand_example():
    engine = MatchingEngine()
    factors = {
        "text": FactorValue(0.80, True),
        "category": FactorValue(1.00, True),
        "location": FactorValue(0.75, True),
        "time": FactorValue(0.90, True),
        "color": FactorValue(1.00, True),
        "brand": FactorValue(0.00, True, conflict="品牌已知不同"),
    }

    def calculate(values):
        coverage = sum(engine.weights[name] for name, value in values.items() if value.available)
        score = sum(engine.weights[name] * value.score for name, value in values.items() if value.available) / coverage
        return score, coverage

    score, coverage = calculate(factors)
    assert score == pytest.approx(0.81)
    assert coverage == pytest.approx(1.0)
    factors["brand"] = FactorValue(0.0, False)
    score, coverage = calculate(factors)
    assert coverage == pytest.approx(0.95)
    assert score == pytest.approx(0.8526315789473684)


def test_known_brand_mismatch_is_zero_not_missing():
    engine = MatchingEngine()
    mismatch = engine._brand_factor("Sony", "Bose")
    unknown = engine._brand_factor("Sony", None)
    assert mismatch.available and mismatch.score == 0 and mismatch.conflict
    assert not unknown.available and unknown.conflict is None


def test_color_and_brand_are_scored_when_both_sides_are_filled():
    engine = MatchingEngine()
    query = make_item("lost", "LOST", "耳机", color_values=("黑色", "银色"), brand="Sony")
    candidate = make_item("found", "FOUND", "耳机", color_values=("黑色",), brand=" sony ")
    factors = engine.compute_factors(query, candidate, text_similarity=1.0, text_available=True)
    assert factors["color"].available and factors["color"].score > 0
    assert factors["brand"].available and factors["brand"].score == 1


def test_time_order_uses_lost_then_found_and_flags_real_conflict():
    engine = MatchingEngine(time_tolerance_hours=2)
    lost = make_item("lost", "LOST", "耳机", event_start=datetime(2026, 9, 3, tzinfo=timezone.utc))
    found = make_item("found", "FOUND", "耳机", event_start=datetime(2026, 9, 1, tzinfo=timezone.utc))
    value = engine._time_factor(lost, found)
    assert value.available and value.score == 0
    assert value.conflict == "拾取时间早于遗失时间"


def test_candidate_generation_filters_status_kind_and_availability_with_counts():
    query = make_item("q", "LOST", "耳机")
    documents = [
        make_item("good", "FOUND", "耳机"),
        make_item("same", "LOST", "耳机"),
        make_item("same-owner", "FOUND", "耳机", owner_id=query.owner_id),
        make_item("pending", "FOUND", "耳机", review_status="PENDING"),
        make_item("returned", "FOUND", "耳机", business_status="RETURNED"),
        make_item("wrong-category", "FOUND", "水杯", category_path=("其他", "水杯")),
        make_item(
            "too-early",
            "FOUND",
            "耳机",
            event_start=datetime(2026, 8, 31, 8, tzinfo=timezone.utc),
        ),
    ]
    eligible, counts = MatchingEngine().generate_candidates(query, documents)
    assert [item.id for item in eligible] == ["good"]
    assert counts == {
        "category_mismatch": 1,
        "not_approved": 1,
        "not_available": 1,
        "same_kind": 1,
        "same_owner": 1,
        "time_conflict": 1,
    }


def test_rank_is_stable_and_evidence_threshold_separates_browse_only():
    engine = MatchingEngine(min_coverage=0.60)
    query = make_item("q", "LOST", "校园卡", brand=None, color_values=(), location_path=())
    candidates = [
        make_item("b", "FOUND", "校园卡", brand=None, color_values=(), location_path=()),
        make_item("a", "FOUND", "校园卡", brand=None, color_values=(), location_path=()),
    ]
    results = engine.rank(query, engine.fit_index(candidates))
    assert [result.candidate_id for result in results] == ["a", "b"]
    assert all(result.coverage == pytest.approx(0.75) for result in results)
    assert all(result.actionable for result in results)


def test_rank_does_not_pad_results_below_similarity_threshold():
    engine = MatchingEngine(min_score=0.35)
    query = make_item("q", "LOST", "黑色钥匙串 三把钥匙", category_path=("钥匙",))
    strong = make_item(
        "strong",
        "FOUND",
        "拾到黑色钥匙串 三把钥匙",
        category_path=("钥匙",),
    )
    weak = make_item(
        "weak",
        "FOUND",
        "无共同特征的描述",
        category_path=("钥匙",),
        location_path=("其他校区", "南门"),
        color_values=("白色",),
        brand="Other",
    )
    results = engine.rank(query, engine.fit_index([strong, weak]), top_k=50)
    assert [result.candidate_id for result in results] == ["strong"]


def test_uncertain_location_uses_rank_decay_and_treats_unknown_as_missing():
    engine = MatchingEngine()
    found = make_item(
        "found",
        "FOUND",
        "钥匙",
        location_path=(),
        location_hypotheses=((('演示校区', '图书馆'), 1.0),),
    )
    second_choice = make_item(
        "lost",
        "LOST",
        "钥匙",
        location_path=(),
        location_hypotheses=(
            (('演示校区', '操场'), 1.0),
            (('演示校区', '图书馆'), 0.8),
        ),
    )
    value = engine._uncertain_location_factor(second_choice, found)
    assert value.available
    assert value.score == pytest.approx(0.8)
    assert value.conflict is None

    unknown = make_item("unknown", "LOST", "钥匙", location_path=(), location_hypotheses=())
    missing = engine._uncertain_location_factor(unknown, found)
    assert not missing.available
    assert missing.score == 0
    assert missing.conflict is None


def test_coordinate_candidates_use_distance_and_rank_decay():
    engine = MatchingEngine()
    found = make_item(
        "found-coordinate",
        "FOUND",
        "钥匙",
        location_path=(),
        location_points=((34.246000, 108.981000, 1.0),),
    )
    lost = make_item(
        "lost-coordinate",
        "LOST",
        "钥匙",
        location_path=(),
        location_points=(
            (34.250000, 108.990000, 1.0),
            (34.246000, 108.981000, 0.8),
        ),
    )

    value = engine._uncertain_location_factor(lost, found)

    assert value.available
    assert value.score == pytest.approx(0.8)
    assert value.conflict is None
    assert "可能顺序衰减" in value.detail


def test_private_fields_cannot_enter_feature_contract():
    fields = ItemFeature.__dataclass_fields__
    forbidden = {"phone", "private_answer", "serial_number", "contact", "message", "claim_label"}
    assert forbidden.isdisjoint(fields)


def test_evaluate_handles_short_results_and_no_relevant_items():
    engine = MatchingEngine()
    metrics = engine.evaluate(["a", "b"], {"b"}, k_values=(1, 3))
    assert metrics["precision@1"] == 0
    assert metrics["recall@3"] == 1
    assert metrics["mrr"] == 0.5
    no_relevant = engine.evaluate(["a"], set(), k_values=(3,))
    assert no_relevant["recall@3"] == 0
