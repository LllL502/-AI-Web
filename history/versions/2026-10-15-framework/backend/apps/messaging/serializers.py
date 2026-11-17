from rest_framework import serializers

from .models import Conversation, Message


class MessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.CharField(source="sender.display_name", read_only=True, allow_null=True)

    class Meta:
        model = Message
        fields = ["id", "sender_name", "body", "is_system", "created_at"]


class ConversationSerializer(serializers.ModelSerializer):
    participants = serializers.SerializerMethodField()
    messages = MessageSerializer(many=True, read_only=True)
    item_title = serializers.CharField(source="item.title", read_only=True, allow_null=True)

    class Meta:
        model = Conversation
        fields = ["id", "subject", "item_id", "item_title", "claim_id", "participants", "messages", "created_at", "updated_at"]

    @staticmethod
    def get_participants(instance):
        return [
            {"id": membership.user_id, "display_name": membership.user.display_name}
            for membership in instance.participants.all()
        ]
