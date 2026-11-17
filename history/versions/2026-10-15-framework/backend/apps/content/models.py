from django.conf import settings
from django.db import models


class PublishableContent(models.Model):
    title = models.CharField(max_length=180)
    slug = models.SlugField(max_length=180, unique=True)
    body = models.TextField()
    is_published = models.BooleanField(default=False, db_index=True)
    published_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Announcement(PublishableContent):
    priority = models.PositiveSmallIntegerField(default=0)


class HelpArticle(PublishableContent):
    category = models.CharField(max_length=80)
    sort_order = models.PositiveIntegerField(default=0)


class RecoveryStory(PublishableContent):
    related_item = models.ForeignKey("items.Item", null=True, blank=True, on_delete=models.SET_NULL)
    consent_recorded = models.BooleanField(default=False)
    cover_image = models.ImageField(upload_to="stories/%Y/%m/", blank=True)
