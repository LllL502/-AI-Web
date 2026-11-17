"""In-app notifications are committed with their business event, never before it.

No external delivery, model inference, or network calls run inside these transactions.
"""
from apps.items.models import Subscription
from apps.matching.engine import ChinesePreprocessor
from .models import Notification


def notify(user, *, category, key, campus_id, title, body, path, metadata=None):
    preferences = user.notification_preferences if isinstance(user.notification_preferences, dict) else {}
    preference = {'MATCH':'match', 'CLAIM':'claim', 'MESSAGE':'claim', 'REVIEW':'claim'}[category]
    if not user.is_active or user.account_status != 'ACTIVE' or preferences.get(preference) is False:
        return None
    return Notification.objects.get_or_create(event_key=f'{key}:{user.pk}', defaults={
        'user':user, 'campus_id':campus_id, 'category':category, 'title':title,
        'body':body[:1000], 'target_path':path, 'metadata':metadata or {}})[0]


def subscription_score(subscription, item):
    """Literal keyword token coverage, not a probability or six-factor match score."""
    criteria = subscription.criteria
    if not isinstance(criteria, dict) or criteria.get('kind') not in (None, '', item.kind):
        return None
    for field, obj in [('category',item.category), ('location',item.location)]:
        value = criteria.get(field)
        if value not in (None, '') and str(value) not in (str(obj.pk), obj.name):
            return None
    raw_query = criteria.get('q', '')
    if not isinstance(raw_query, str):
        return None
    query = raw_query.strip()
    if not query:
        return 1.0  # A structured-only subscription exactly matches its filters.
    preprocessor = ChinesePreprocessor()
    tokens = set(preprocessor.tokenize(query))
    text = preprocessor.normalize_text(' '.join([item.title,item.description,item.brand,item.color,item.category.name]))
    return sum(token in text for token in tokens) / len(tokens) if tokens else 0.0


def notify_public_item(item):
    if item.review_status != 'APPROVED' or item.business_status != 'OPEN':
        return
    for subscription in Subscription.objects.filter(campus_id=item.location.campus_id, is_active=True).exclude(user_id=item.owner_id).select_related('user').iterator():
        score = subscription_score(subscription, item)
        if score is None or score <= 0 or score < float(subscription.minimum_score):
            continue
        notify(subscription.user, category='MATCH', key=f'subscription:{subscription.pk}:item:{item.pk}',
            campus_id=item.location.campus_id, title='有新的订阅线索',
            body=f'“{subscription.name}”匹配到一条新线索，请查看实物特征。', path=f'/items/{item.pk}',
            metadata={'subscription_id':subscription.pk,'item_id':str(item.pk),'score':round(score,4),'score_method':'keyword_token_coverage_v1'})


def notify_review(item):
    notify(item.owner, category='REVIEW', key=f'item:{item.pk}:review:{item.review_status}:{item.published_revision or item.revisions.count()}',
        campus_id=item.location.campus_id, title='发布审核状态更新',
        body=f'你的信息已更新为“{item.get_review_status_display()}”。', path=f'/items/{item.pk}')
    notify_public_item(item)


def notify_claim(claim, actor, event_id):
    # Never copy private statements, evidence, or review notes into a notification preview.
    users = {claim.claimant_id:claim.claimant, claim.found_item.owner_id:claim.found_item.owner}
    for user_id, user in users.items():
        if user_id != actor.pk:
            notify(user, category='CLAIM', key=f'claim-event:{event_id}', campus_id=claim.found_item.location.campus_id,
                title='认领进度更新', body=f'认领记录已更新为“{claim.get_status_display()}”。', path=f'/claims/{claim.pk}')


def notify_message(message):
    conversation = message.conversation
    campus_id = (conversation.item.location.campus_id if conversation.item_id else
        conversation.claim.found_item.location.campus_id if conversation.claim_id else conversation.campus_id)
    if campus_id is None:
        return
    for membership in conversation.participants.exclude(user_id=message.sender_id).select_related('user'):
        notify(membership.user, category='MESSAGE', key=f'message:{message.pk}', campus_id=campus_id,
            title='收到新的沟通消息', body='对方发来一条消息，请进入会话查看。', path=f'/messages/{conversation.pk}')
