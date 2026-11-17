from django.utils import timezone
from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.models import User

from .models import Conversation, ConversationParticipant, Message
from .serializers import ConversationSerializer, MessageSerializer, MessageInputSerializer
from apps.stations.scope import selected_campus


class ConversationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ConversationSerializer

    def get_queryset(self):
        queryset = Conversation.objects.select_related("item", "claim").prefetch_related(
            "participants__user", "messages__sender"
        )
        campus = selected_campus(self.request)
        queryset = queryset.filter(Q(item__location__campus_id=campus) | Q(item__isnull=True, claim__found_item__location__campus_id=campus) | Q(item__isnull=True, claim__isnull=True, campus_id=campus))
        if self.request.user.role == User.Role.ADMIN:
            return queryset.order_by("-updated_at")
        return queryset.filter(participants__user=self.request.user).distinct().order_by("-updated_at")

    def retrieve(self, request, *args, **kwargs):
        conversation = self.get_object()
        ConversationParticipant.objects.filter(conversation=conversation, user=request.user).update(last_read_at=timezone.now())
        return Response({"data": self.get_serializer(conversation).data})

    @action(detail=True, methods=["post"])
    def messages(self, request, pk=None):
        conversation = self.get_object()
        serializer = MessageInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        body = serializer.validated_data['body']
        if not body:
            return Response(
                {"error": {"code": "empty_message", "message": "消息内容不能为空", "fields": {}, "request_id": request.request_id}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        message = Message.objects.create(conversation=conversation, sender=request.user, body=body)
        from apps.notifications.services import notify_message
        notify_message(message)
        conversation.updated_at = timezone.now()
        conversation.save(update_fields=["updated_at"])
        ConversationParticipant.objects.filter(conversation=conversation, user=request.user).update(last_read_at=timezone.now())
        return Response({"data": MessageSerializer(message).data}, status=status.HTTP_201_CREATED)
