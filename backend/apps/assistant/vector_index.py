"""Persistent exact vectors; eligibility always comes from live business rows."""
import hashlib
import math
from django.conf import settings
from django.db import transaction
from .models import ItemVector
from .providers import ProviderUnavailable
from .runtime import check_budget


class IndexPending(ProviderUnavailable):
    default_code = 'ai_index_pending'
    default_detail = '线索索引尚未就绪，请稍后再试。'


def model_key():
    identity = '\n'.join([settings.AI_LOCAL_EMBEDDING_URL, settings.AI_LOCAL_EMBEDDING_MODEL,
        settings.AI_LOCAL_EMBEDDING_REVISION, 'public-item-text-v1'])
    return hashlib.sha256(identity.encode()).hexdigest()


def public_text(item):
    return f'{item.category.name} {item.brand} {item.color} {item.title} {item.description}'


def content_hash(item):
    return hashlib.sha256(public_text(item).encode()).hexdigest()


def valid_vector(vector, dimension):
    if not isinstance(vector, list) or not vector or len(vector) != dimension:
        return False
    if not all(type(x) in (int, float) and math.isfinite(x) for x in vector):
        return False
    norm = sum(x*x for x in vector)
    return math.isfinite(norm) and norm > 0


def load_vectors(items):
    key = model_key()
    vectors, missing = {}, []
    for offset in range(0, len(items), 400):
        check_budget()
        batch = items[offset:offset+400]
        rows = {row.item_id: row for row in ItemVector.objects.filter(model_key=key, item_id__in=[item.pk for item in batch])}
        for item in batch:
            row = rows.get(item.pk)
            if row and row.content_hash == content_hash(item) and valid_vector(row.vector, row.dimension):
                vectors[item.pk] = row.vector
            else:
                missing.append(item)
    return vectors, missing


def build_vectors(items, eligible_queryset):
    from .local_models import embeddings
    key = model_key()
    saved = {}
    for offset in range(0, len(items), 16):
        check_budget()
        batch = items[offset:offset+16]
        # Eligibility is checked again immediately before sending text to the model.
        live = {item.pk: item for item in eligible_queryset.filter(pk__in=[item.pk for item in batch])}
        batch = [item for item in batch if item.pk in live and content_hash(live[item.pk]) == content_hash(item)]
        if not batch:
            continue
        result = embeddings([public_text(item) for item in batch])
        for item, vector in zip(batch, result):
            check_budget()
            # Lock only while comparing/persisting; never during inference.
            with transaction.atomic():
                current = eligible_queryset.select_for_update().filter(pk=item.pk).first()
                if current is None or content_hash(current) != content_hash(item):
                    continue
                ItemVector.objects.update_or_create(item=current, model_key=key, defaults={
                    'content_hash': content_hash(item), 'dimension': len(vector), 'vector': vector})
                saved[item.pk] = vector
    return saved


def ensure_vectors(items, eligible_queryset):
    vectors, missing = load_vectors(items)
    if len(missing) > settings.AI_INDEX_SYNC_LIMIT:
        raise IndexPending()
    vectors.update(build_vectors(missing, eligible_queryset))
    return vectors
