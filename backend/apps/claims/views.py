from django.db.models import Q
from django.db import transaction
from django.utils.decorators import method_decorator
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.models import User
from apps.administration.models import AuditLog
from apps.items.models import Item
from apps.stations.models import Station
from apps.stations.scope import selected_campus

from .models import Claim
from .serializers import ClaimSerializer, HandoverAppointmentSerializer
from .services import (
    confirm_direct_handover,
    confirm_handover,
    complete_station_pickup,
    decide_claim,
    schedule_handover,
    start_direct_handover,
    submit_claim,
    verify_handover_code,
)


@method_decorator(transaction.non_atomic_requests, name="dispatch")
class ClaimViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ClaimSerializer

    def get_queryset(self):
        queryset = Claim.objects.select_related(
            "found_item__station", "found_item__owner", "claimant", "related_lost_item"
        ).prefetch_related("events__actor", "conversations")
        user = self.request.user
        queryset = queryset.filter(found_item__location__campus_id=selected_campus(self.request))
        if user.role == User.Role.ADMIN:
            return queryset.order_by("-created_at")
        if user.role == User.Role.STAFF:
            station_ids = user.station_memberships.filter(is_active=True).values_list("station_id", flat=True)
            return queryset.filter(Q(claimant=user) | Q(found_item__station_id__in=station_ids)).distinct().order_by("-created_at")
        return queryset.filter(
            Q(claimant=user, claimant_deleted_at__isnull=True) | Q(found_item__owner=user)
        ).distinct().order_by("-created_at")

    def create(self, request, *args, **kwargs):
        try:
            found_item = Item.objects.get(pk=request.data.get("found_item_id"), location__campus_id=selected_campus(request))
            related = Item.objects.filter(pk=request.data.get("related_lost_item_id")).first()
        except (Item.DoesNotExist, ValueError, TypeError):
            return Response({"error": {"code": "item_not_found", "message": "未找到招领物品", "fields": {}, "request_id": request.request_id}}, status=status.HTTP_404_NOT_FOUND)
        claim = submit_claim(
            found_item,
            request.user,
            statement=str(request.data.get("statement", "")).strip(),
            evidence=request.data.get("evidence", {}),
            related_lost_item=related,
        )
        return Response({"data": self.get_serializer(claim).data}, status=status.HTTP_201_CREATED)

    def retrieve(self, request, *args, **kwargs):
        return Response({"data": self.get_serializer(self.get_object()).data})

    @action(detail=True, methods=["post"])
    def decision(self, request, pk=None):
        claim = decide_claim(self.get_object(), request.user, request.data.get("decision", ""), request.data.get("note", ""), request.request_id)
        return Response({"data": self.get_serializer(claim).data})

    @action(detail=True, methods=["post"])
    def appointment(self, request, pk=None):
        station = Station.objects.filter(
            pk=request.data.get("station_id"), is_active=True,
            approval_status=Station.ApprovalStatus.APPROVED, status=Station.Status.OPEN,
        ).first()
        scheduled_at = parse_datetime(request.data.get("scheduled_at", ""))
        if not station or not scheduled_at:
            return Response({"error": {"code": "invalid_appointment", "message": "站点或预约时间无效", "fields": {}, "request_id": request.request_id}}, status=status.HTTP_400_BAD_REQUEST)
        appointment, one_time_code = schedule_handover(self.get_object(), request.user, station, scheduled_at)
        return Response({"data": {"appointment": HandoverAppointmentSerializer(appointment).data, "one_time_code": one_time_code, "notice": "交接码仅显示本次，请妥善保管"}})

    @action(detail=True, methods=["delete"], url_path="mine")
    @transaction.atomic
    def delete_mine(self, request, pk=None):
        claim = self.get_object()
        if claim.claimant_id != request.user.id:
            return Response(
                {"error": {"code": "permission_denied", "message": "只能删除自己的认领记录", "fields": {}, "request_id": request.request_id}},
                status=status.HTTP_403_FORBIDDEN,
            )
        if not claim.claimant_deleted_at:
            claim.claimant_deleted_at = timezone.now()
            claim.save(update_fields=["claimant_deleted_at", "updated_at"])
            AuditLog.objects.create(
                actor=request.user,
                action="claim.hide_by_claimant",
                target_type="claims.Claim",
                target_id=str(claim.pk),
                before={"claimant_deleted_at": None},
                after={"claimant_deleted_at": claim.claimant_deleted_at.isoformat()},
                request_id=request.request_id,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="direct-handover")
    def direct_handover(self, request, pk=None):
        claim = start_direct_handover(self.get_object(), request.user)
        return Response({"data": self.get_serializer(claim).data})

    @action(detail=True, methods=["post"], url_path="direct-handover/confirm")
    def confirm_direct(self, request, pk=None):
        claim = confirm_direct_handover(self.get_object(), request.user)
        return Response({"data": self.get_serializer(claim).data})

    @action(detail=True, methods=["post"], url_path="handover/verify")
    def verify_handover(self, request, pk=None):
        appointment = verify_handover_code(self.get_object(), request.user, str(request.data.get("code", "")))
        return Response({"data": HandoverAppointmentSerializer(appointment).data})

    @action(detail=True, methods=["post"], url_path="handover/confirm")
    def confirm(self, request, pk=None):
        claim = confirm_handover(self.get_object(), request.user)
        return Response({"data": self.get_serializer(claim).data})

    @action(detail=True, methods=["post"], url_path="station-pickup/complete")
    def complete_station(self, request, pk=None):
        claim = complete_station_pickup(self.get_object(), request.user)
        return Response({"data": self.get_serializer(claim).data})


ClaimViewSet.http_method_names = ["get", "post", "delete", "head", "options"]
