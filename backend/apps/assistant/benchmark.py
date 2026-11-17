"""Frozen synthetic retrieval evaluation; gold labels never enter inference."""
from datetime import datetime
from apps.matching.engine import ItemFeature, MatchingEngine, ChinesePreprocessor, DEFAULT_WEIGHTS
from .ranking import score_candidate, accept_candidate
from .tools import _search_tokens
from .local_models import cosine


def validate_dataset(dataset):
    candidates = {row['id']: row for row in dataset['candidates']}
    queries = dataset['queries']
    if len(candidates) != len(dataset['candidates']) or len({q['id'] for q in queries}) != len(queries):
        raise ValueError('Duplicate IDs')
    groups = {'development': set(), 'validation': set()}
    eligible = {row['id'] for row in eligible_candidates(dataset)}
    for query in queries:
        if query['split'] not in groups or not isinstance(query['gold'], list):
            raise ValueError('Invalid split or gold labels')
        if not set(query['gold']) <= eligible:
            raise ValueError('A gold target is outside the common eligible corpus')
        groups[query['split']].update(query['gold'])
    if groups['development'] & groups['validation']:
        raise ValueError('Target object leakage between splits')


def eligible_candidates(dataset):
    return [row for row in dataset['candidates']
        if row.get('campus', dataset['campus']) == dataset['campus'] and row['kind'] == 'FOUND'
        and row.get('review_status', 'APPROVED') == 'APPROVED' and row.get('business_status', 'OPEN') == 'OPEN']


def feature(row, query=False):
    event = datetime.fromisoformat(row['time']) if row.get('time') else None
    return ItemFeature(id=row['id'], kind='LOST' if query else row['kind'], public_text=row['text'],
        category_path=(row['category'],) if row.get('category') else (),
        color_values=tuple(row.get('colors', [])) if query else ((row['color'],) if row.get('color') else ()),
        brand=row.get('brand') or None, location_path=(row['location'],) if row.get('location') else (),
        event_start=event, event_end=event)


def candidate_text(row):
    return f"{row['category']} {row.get('brand', '')} {row.get('color', '')} {row['text']}"


def query_text(row):
    return ' '.join([row['text'], row.get('category', ''), row.get('brand', ''), ' '.join(row.get('colors', []))])


def evaluate_rankings(dataset, queries, document_vectors, query_vectors):
    corpus = eligible_candidates(dataset)
    engine = MatchingEngine(preprocessor=ChinesePreprocessor(aliases={'sony': '索尼', 'apple': '苹果'}), weights=DEFAULT_WEIGHTS)
    rows = []
    for query, vector in zip(queries, query_vectors):
        text = query_text(query)
        tokens = _search_tokens(text)
        keyword = [row for row in corpus if any(token.lower() in candidate_text(row).lower() for token in tokens)]
        keyword.sort(key=lambda row: (row['time'], row['id']), reverse=True)
        semantic = [(cosine(vector, document_vectors[row['id']]), row) for row in corpus]
        semantic = sorted((entry for entry in semantic if entry[0] > 0), key=lambda entry: (-entry[0], entry[1]['id']))[:50]
        hybrid = [(score_candidate(feature(query, True), feature(row), score, engine), score, row) for score, row in semantic]
        hybrid.sort(key=lambda entry: (-entry[0]['score'], -entry[1], entry[2]['id']))
        rankings = {
            'keyword': [{'id': row['id']} for row in keyword[:5]],
            'semantic': [{'id': row['id'], 'score': round(score, 6)} for score, row in semantic[:5]],
            'semantic_six_factor': [{'id': row['id'], **evidence} for evidence, _, row in hybrid[:5]],
            'semantic_six_factor_gated': [{'id': row['id'], **evidence} for evidence, _, row in hybrid if accept_candidate(evidence)][:5],
        }
        rows.append({'id': query['id'], 'split': query['split'], 'scenario': query['scenario'],
            'gold': query['gold'], 'rankings': rankings})
    return rows


def metrics(rows, method):
    positives = [row for row in rows if row['gold']]
    negatives = [row for row in rows if not row['gold']]
    result = {'positive_queries': len(positives), 'no_answer_queries': len(negatives)}
    for k in (1, 3, 5):
        values = [len(set(row['gold']) & {item['id'] for item in row['rankings'][method][:k]}) / len(set(row['gold'])) for row in positives]
        result[f'recall_at_{k}'] = sum(values)/len(values) if values else None
    reciprocal = []
    for row in positives:
        rank = next((i for i, item in enumerate(row['rankings'][method], 1) if item['id'] in row['gold']), None)
        reciprocal.append(1/rank if rank else 0)
    result['mrr_at_5'] = sum(reciprocal)/len(reciprocal) if reciprocal else None
    result['no_answer_false_return_rate'] = sum(bool(row['rankings'][method]) for row in negatives)/len(negatives) if negatives else None
    return result
