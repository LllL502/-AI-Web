from rest_framework import serializers

from .models import Claim, ClaimEvent, HandoverAppointment


class ClaimEventSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.display_name", read_only=True)

    class Meta:
        model = ClaimEvent
        fields = ["id", "actor_name", "from_status", "to_status", "note", "created_at"]


class HandoverAppointmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = HandoverAppointment
        fields = [
            "station_id", "scheduled_at", "code_expires_at", "failed_attempts", "verified_at",
            "claimant_confirmed_at", "staff_confirmed_at",
        ]


class ClaimSerializer(serializers.ModelSerializer):
    events = ClaimEventSerializer(many=True, read_only=True)
    appointment = HandoverAppointmentSerializer(read_only=True)
    allowed_actions = serializers.SerializerMethodField()
    item_title = serializers.CharField(source="found_item.title", read_only=True)
    custody_mode = serializers.SerializerMethodField()
    viewer_role = serializers.SerializerMethodField()
    conversation_id = serializers.SerializerMethodField()

    class Meta:
        model = Claim
        fields = [
            "id", "found_item_id", "item_title", "related_lost_item_id", "statement", "evidence", "status",
            "decision_note", "submitted_at", "decided_at", "created_at", "updated_at", "events", "appointment",
            "handover_method", "claimant_confirmed_at", "finder_confirmed_at", "custody_mode", "viewer_role",
            "conversation_id", "allowed_actions",
        ]
        read_only_fields = [
            "status", "decision_note", "submitted_at", "decided_at", "handover_method",
            "claimant_confirmed_at", "finder_confirmed_at", "created_at", "updated_at",
        ]

    @staticmethod
    def get_custody_mode(instance):
        return "STATION" if instance.found_item.station_id else "FINDER"

    def get_viewer_role(self, instance):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return ""
        if request.user.id == instance.claimant_id:
            return "CLAIMANT"
        if request.user.id == instance.found_item.owner_id:
            return "FINDER"
        return "STAFF"

    @staticmethod
    def get_conversation_id(instance):
        conversation = next(iter(instance.conversations.all()), None)
        return conversation.id if conversation else None

    def get_allowed_actions(self, instance):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return []
        actions = []
        is_claimant = request.user.id == instance.claimant_id
        is_finder = request.user.id == instance.found_item.owner_id
        if is_claimant and instance.status == Claim.Status.APPROVED:
            actions.append("schedule_handover")
        if (is_claimant or is_finder) and instance.status == Claim.Status.APPROVED:
            actions.append("start_direct_handover")
        can_review_at_station = request.user.role == "ADMIN" or (
            request.user.role == "STAFF"
            and instance.found_item.station_id
            and request.user.station_memberships.filter(
                station_id=instance.found_item.station_id, is_active=True, can_review=True
            ).exists()
        )
        can_review_as_finder = not instance.found_item.station_id and is_finder
        if (can_review_at_station or can_review_as_finder) and instance.status in {Claim.Status.SUBMITTED, Claim.Status.NEEDS_INFO}:
            actions.append("decide")
        if instance.status == Claim.Status.HANDOVER_PENDING and instance.handover_method == Claim.HandoverMethod.DIRECT:
            if is_claimant and not instance.claimant_confirmed_at:
                actions.append("confirm_direct_handover")
            if is_finder and not instance.finder_confirmed_at:
                actions.append("confirm_direct_handover")
        can_handover_at_station = request.user.role == "ADMIN" or (
            request.user.role == "STAFF"
            and instance.found_item.station_id
            and request.user.station_memberships.filter(
                station_id=instance.found_item.station_id, is_active=True, can_handover=True
            ).exists()
        )
        if (
            instance.status == Claim.Status.HANDOVER_PENDING
            and instance.handover_method == Claim.HandoverMethod.STATION
            and (is_claimant or can_handover_at_station)
        ):
            actions.extend(["verify_code", "confirm_handover"])
        return actions
