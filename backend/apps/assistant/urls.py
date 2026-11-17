from django.urls import path

from .views import (
    AssistantCapabilitiesView,
    AssistantDraftPreviewView,
    AssistantPrepareView,
    AssistantSearchView,
    AssistantImageView,
    AssistantJobView,
    AssistantHealthView,
    AssistantJobLookupView,
    AssistantConversationView,
    AssistantAgentActionView,
    AssistantSpeechView,
)


urlpatterns = [
    path('speech/', AssistantSpeechView.as_view(), name='assistant-speech'),
    path('agent/actions/', AssistantAgentActionView.as_view(), name='assistant-agent-actions'),
    path('conversation/', AssistantConversationView.as_view(), name='assistant-conversation'),
    path('health/', AssistantHealthView.as_view(), name='assistant-health'),
    path('jobs/', AssistantJobLookupView.as_view(), name='assistant-job-lookup'),
    path('jobs/<uuid:job_id>/', AssistantJobView.as_view(), name='assistant-job'),
    path("image/", AssistantImageView.as_view(), name="assistant-image"),
    path("capabilities/", AssistantCapabilitiesView.as_view(), name="assistant-capabilities"),
    path("prepare/", AssistantPrepareView.as_view(), name="assistant-prepare"),
    path("search/", AssistantSearchView.as_view(), name="assistant-search"),
    path("draft-preview/", AssistantDraftPreviewView.as_view(), name="assistant-draft-preview"),
]

