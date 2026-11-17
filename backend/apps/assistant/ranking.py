"""Read-only six-factor reranking using public fields and a confirmed draft."""
import re
from dataclasses import replace

from django.utils.dateparse import parse_datetime
from django.utils import timezone

from apps.items.models import Category
from apps.matching.engine import ChinesePreprocessor, ItemFeature, MatchingEngine, FactorValue
from apps.matching.models import AlgorithmConfig

VERSION = "semantic_six_factor_v2"
# Initial conservative gate checked on development cases; not a probability.
ACCEPTANCE_POLICY = {"version": "evidence_gate_v1", "min_score": .6,
                     "blocking_factors": ["category", "time"]}
# Initial explicit engineering policy, not fitted probabilities.
PENALTIES = {"category": .25, "color": .55, "brand": .65, "time": .35}
LABELS = {"text": "语义", "category": "类别", "location": "地点", "time": "时间", "color": "颜色", "brand": "品牌"}


def hierarchy(obj):
    names = []
    while obj is not None:
        names.append(obj.name)
        obj = obj.parent
    return tuple(reversed(names))


def resolve_hint(hint, entries, normalize):
    """Only resolve an unambiguous dictionary substring; never guess a category."""
    hint = normalize(hint)
    matches = [(len(normalize(name)), path) for name, path in entries
               if normalize(name) and normalize(name) in hint]
    if not matches:
        return ()
    longest = max(length for length, _ in matches)
    paths = {path for length, path in matches if length == longest}
    return next(iter(paths)) if len(paths) == 1 else ()


def public_feature(item):
    # Do not use item_to_feature: it includes protected location hypotheses.
    return ItemFeature(id=str(item.pk), kind=item.kind, public_text=item.searchable_text,
        category_path=hierarchy(item.category),
        location_path=hierarchy(item.location) if item.location.parent_id else (),
        color_values=tuple(x.strip() for x in re.split(r"[,，、/]+", item.color or "") if x.strip()),
        brand=item.brand or None, event_start=item.occurred_at, event_end=item.occurred_at)


def rerank(draft, semantic_rows):
    config = AlgorithmConfig.objects.filter(is_published=True).order_by("-published_at", "-id").first()
    prep = config.preprocessing if config else {}
    preprocessor = ChinesePreprocessor(aliases=prep.get("aliases", {}), stop_words=prep.get("stop_words", []))
    engine = MatchingEngine(preprocessor=preprocessor, weights=config.weights if config else None,
        time_tau_days=config.thresholds.get("time_tau_days", 7) if config else 7,
        time_tolerance_hours=config.thresholds.get("time_tolerance_hours", 6) if config else 6)
    category_entries = [(name, hierarchy(c)) for c in Category.objects.filter(is_active=True, children__isnull=True).select_related("parent")
                        for name in [c.name, *c.synonyms]]
    public_locations = [(item.location.name, hierarchy(item.location)) for _, item in semantic_rows if item.location.parent_id]
    event = draft.get("occurred_at")
    if isinstance(event, str):
        event = parse_datetime(event)
    if event is not None and timezone.is_naive(event):
        event = timezone.make_aware(event)
    query = ItemFeature(id="confirmed-draft", kind=draft["kind"], public_text=draft["public_description"],
        category_path=resolve_hint(draft.get("category_hint", ""), category_entries, preprocessor.normalize_text),
        location_path=resolve_hint(draft.get("location_hint", ""), public_locations, preprocessor.normalize_text),
        color_values=tuple(draft.get("colors", [])), brand=draft.get("brand") or None,
        event_start=event, event_end=event)
    results = []
    for semantic, item in semantic_rows:
        candidate = public_feature(item)
        evidence = score_candidate(query, candidate, semantic, engine)
        evidence.update({"version": VERSION, "config_version": config.version if config else "engine-defaults",
                         "semantic_similarity": round(semantic, 6)})
        results.append((evidence["score"], semantic, item, evidence))
    return sorted(results, key=lambda row: (-row[0], -row[1], str(row[2].pk)))


def accept_candidate(evidence):
    """Unknown fields do not block; explicit category/time conflicts do."""
    return (evidence['score'] >= ACCEPTANCE_POLICY['min_score']
            and not any(name in evidence['penalties'] for name in ACCEPTANCE_POLICY['blocking_factors']))


def score_candidate(query, candidate, semantic, engine):
    """Shared production/benchmark scoring, without ORM or gold labels."""
    factors = engine.compute_factors(query, candidate, semantic, True)
    factors['text'] = replace(factors['text'], detail='本地向量余弦相似度')
    if query.category_path and candidate.category_path and query.category_path[-1] != candidate.category_path[-1]:
        factors['category'] = FactorValue(0, True, conflict='类别已知不同')
    return score_factors(factors, engine.weights)


def score_factors(factors, weights):
    coverage = sum(weights[name] for name, factor in factors.items() if factor.available)
    effective = {name: weights[name] / coverage if factor.available and coverage else 0 for name, factor in factors.items()}
    base = sum(effective[name] * factor.score for name, factor in factors.items())
    multiplier = 1.0
    conflicts, explanations, penalties = [], [], {}
    for name, factor in factors.items():
        if not factor.available:
            explanations.append(f"{LABELS[name]}信息不足，未参与评分")
        elif factor.conflict:
            conflicts.append(factor.conflict)
            if name in PENALTIES:
                penalties[name] = PENALTIES[name]
                multiplier *= PENALTIES[name]
            explanations.append(f"{factor.conflict}，已降分")
        elif name != "text":
            explanations.append(f"{LABELS[name]}证据相符" if factor.score >= .99 else f"{LABELS[name]}证据部分相符")
    return {"score": round(base * multiplier, 6), "base_score": round(base, 6),
        "coverage": round(coverage, 6), "penalty_multiplier": round(multiplier, 6), "penalties": penalties,
        "factors": {name: round(factor.score, 6) if factor.available else None for name, factor in factors.items()},
        "effective_weights": effective, "conflicts": conflicts,
        "missing_factors": [name for name, factor in factors.items() if not factor.available],
        "explanations": explanations}
