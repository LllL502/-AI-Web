import json
import uuid
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.accounts.permissions import IsAdminRole, IsManagementUser
from apps.claims.models import Claim, ReturnRecord
from apps.content.models import Announcement, HelpArticle
from apps.items.models import Item
from apps.matching.models import AlgorithmConfig
from apps.stations.models import Station, StationAccessApplication, StationMembership
from apps.stations.scope import selected_campus

from .models import AbuseReport, AuditLog, PersistentTask
from .serializers import (
    AbuseReportSerializer, AdminUserSerializer, AlgorithmConfigSerializer, AnnouncementAdminSerializer,
    AdminStationSerializer, AdminStationApplicationSerializer, HelpArticleAdminSerializer, PersistentTaskSerializer,
)


def scoped_items(user):
    queryset = Item.objects.all()
    if user.role == User.Role.STAFF:
        station_ids = user.station_memberships.filter(is_active=True).values_list("station_id", flat=True)
        queryset = queryset.filter(station_id__in=station_ids)
    return queryset


def scoped_claims(user):
    queryset = Claim.objects.all()
    if user.role == User.Role.STAFF:
        station_ids = user.station_memberships.filter(is_active=True).values_list("station_id", flat=True)
        queryset = queryset.filter(found_item__station_id__in=station_ids)
    return queryset


class OverviewView(APIView):
    permission_classes = [IsManagementUser]

    def get(self, request):
        campus_id = selected_campus(request)
        items = scoped_items(request.user).filter(location__campus_id=campus_id)
        claims = scoped_claims(request.user).filter(found_item__location__campus_id=campus_id)
        status_rows = list(items.values("review_status").annotate(count=Count("id")).order_by("review_status"))
        claim_rows = list(claims.values("status").annotate(count=Count("id")).order_by("status"))
        returned = ReturnRecord.objects.filter(found_item__in=items).count()
        data = {
            "pending_reviews": items.filter(review_status=Item.ReviewStatus.PENDING).count(),
            "open_items": items.filter(review_status=Item.ReviewStatus.APPROVED, business_status=Item.BusinessStatus.OPEN).count(),
            "active_claims": claims.exclude(status__in=[Claim.Status.COMPLETED, Claim.Status.REJECTED, Claim.Status.CANCELLED]).count(),
            "completed_returns": returned,
            "failed_tasks": PersistentTask.objects.filter(status=PersistentTask.Status.FAILED).count() if request.user.role == User.Role.ADMIN else None,
            "item_review_statuses": status_rows,
            "claim_statuses": claim_rows,
            "stations": (
                Station.objects.filter(is_active=True, approval_status=Station.ApprovalStatus.APPROVED, location__campus_id=campus_id).count()
                if request.user.role == User.Role.ADMIN
                else request.user.station_memberships.filter(is_active=True, station__is_active=True, station__location__campus_id=campus_id).count()
            ),
            "scope": "ALL" if request.user.role == User.Role.ADMIN else "ASSIGNED_STATIONS",
        }
        return Response({"data": data})


class BenchmarkEvidenceView(APIView):
    permission_classes = [IsManagementUser]

    def get(self, request):
        path = Path(settings.BASE_DIR).parent / "artifacts" / "experiment-results" / "demo-benchmark.json"
        if not path.exists():
            return Response(
                {"error": {"code": "benchmark_not_run", "message": "基准评测尚未运行", "fields": {}, "request_id": request.request_id}},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response({"data": json.loads(path.read_text(encoding="utf-8"))})


class AdminUserViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAdminRole]
    serializer_class = AdminUserSerializer
    http_method_names = ["get", "patch", "head", "options"]
    queryset = User.objects.order_by("-created_at")


class PersistentTaskViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAdminRole]
    serializer_class = PersistentTaskSerializer
    queryset = PersistentTask.objects.select_related("requested_by").order_by("-created_at")


class AdminStationViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAdminRole]
    serializer_class = AdminStationSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        queryset = Station.objects.select_related("location").order_by("name")
        queryset = queryset.filter(location__campus_id=selected_campus(self.request))
        return queryset.prefetch_related("memberships__user")

    def perform_create(self, serializer):
        station = serializer.save(code=f"station-{uuid.uuid4().hex[:12]}")
        AuditLog.objects.create(
            actor=self.request.user, action="station.create", target_type="stations.Station",
            target_id=str(station.pk), after={"name": station.name}, request_id=self.request.request_id,
        )

    def perform_update(self, serializer):
        before = AdminStationSerializer(serializer.instance, context=self.get_serializer_context()).data
        station = serializer.save()
        AuditLog.objects.create(
            actor=self.request.user, action="station.update", target_type="stations.Station",
            target_id=str(station.pk), before=before, after={"name": station.name, "status": station.status},
            request_id=self.request.request_id,
        )

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        station = self.get_object()
        if station.approval_status not in {Station.ApprovalStatus.DRAFT, Station.ApprovalStatus.REJECTED}:
            return Response({"error": {"message": "当前站点不能重复提交"}}, status=400)
        station.approval_status = Station.ApprovalStatus.PENDING
        station.review_note = ""
        station.save(update_fields=["approval_status", "review_note", "updated_at"])
        return Response({"data": self.get_serializer(station).data})

    @action(detail=True, methods=["post"])
    def decision(self, request, pk=None):
        station = self.get_object()
        decision = request.data.get("decision")
        if station.approval_status != Station.ApprovalStatus.PENDING or decision not in {"APPROVE", "REJECT"}:
            return Response({"error": {"message": "站点审核状态或决定无效"}}, status=400)
        station.approval_status = Station.ApprovalStatus.APPROVED if decision == "APPROVE" else Station.ApprovalStatus.REJECTED
        station.review_note = str(request.data.get("note", ""))[:500]
        station.approved_by = request.user if decision == "APPROVE" else None
        station.approved_at = timezone.now() if decision == "APPROVE" else None
        station.save(update_fields=["approval_status", "review_note", "approved_by", "approved_at", "updated_at"])
        AuditLog.objects.create(actor=request.user, action=f"station.{decision.lower()}", target_type="stations.Station", target_id=str(station.pk), after={"approval_status": station.approval_status}, request_id=request.request_id)
        return Response({"data": self.get_serializer(station).data})

    @action(detail=True, methods=["post", "delete"], url_path="members")
    def members(self, request, pk=None):
        station = self.get_object()
        if request.method == "DELETE":
            membership = StationMembership.objects.filter(station=station, pk=request.data.get("membership_id")).first()
            if not membership:
                return Response({"error": {"message": "未找到工作人员授权"}}, status=404)
            membership.delete()
        else:
            user = User.objects.filter(pk=request.data.get("user_id")).exclude(role=User.Role.ADMIN).first()
            if not user:
                return Response({"error": {"message": "请选择可授权的校内工作人员账号"}}, status=400)
            if user.role != User.Role.STAFF:
                user.role = User.Role.STAFF
                user.save(update_fields=["role", "updated_at"])
            StationMembership.objects.update_or_create(
                station=station, user=user,
                defaults={"can_review": bool(request.data.get("can_review", True)), "can_handover": bool(request.data.get("can_handover", True)), "is_active": True},
            )
            AuditLog.objects.create(actor=request.user, action="station.member.authorize", target_type="accounts.User", target_id=str(user.pk), after={"station_id": station.pk, "role": user.role, "can_review": bool(request.data.get("can_review", True)), "can_handover": bool(request.data.get("can_handover", True))}, request_id=request.request_id)
        station = self.get_queryset().get(pk=station.pk)
        return Response({"data": self.get_serializer(station).data})


class AdminStationApplicationViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAdminRole]
    serializer_class = AdminStationApplicationSerializer
    queryset = StationAccessApplication.objects.select_related("applicant", "school", "campus", "reviewed_by")

    @action(detail=True, methods=["post"])
    def decision(self, request, pk=None):
        application = self.get_object()
        decision = request.data.get("decision")
        if application.status != StationAccessApplication.Status.PENDING or decision not in {"APPROVE", "REJECT"}:
            return Response({"error": {"message": "申请状态或审核决定无效"}}, status=400)
        application.status = StationAccessApplication.Status.APPROVED if decision == "APPROVE" else StationAccessApplication.Status.REJECTED
        application.reviewed_by = request.user
        application.reviewed_at = timezone.now()
        application.review_note = str(request.data.get("note", ""))[:500]
        application.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_note", "updated_at"])
        AuditLog.objects.create(actor=request.user, action=f"station_application.{decision.lower()}", target_type="stations.StationAccessApplication", target_id=str(application.pk), after={"status": application.status}, request_id=request.request_id)
        return Response({"data": self.get_serializer(application).data})


class AbuseReportViewSet(viewsets.ModelViewSet):
    permission_classes = [IsManagementUser]
    serializer_class = AbuseReportSerializer
    http_method_names = ["get", "patch", "head", "options"]

    def get_queryset(self):
        return AbuseReport.objects.filter(item__in=scoped_items(self.request.user), item__location__campus_id=selected_campus(self.request)).select_related("reporter", "item").order_by("-created_at")


class AlgorithmConfigViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAdminRole]
    serializer_class = AlgorithmConfigSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]
    queryset = AlgorithmConfig.objects.select_related("created_by").order_by("-created_at")

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def publish(self, request, pk=None):
        config = self.get_object()
        AlgorithmConfig.objects.filter(is_published=True).exclude(pk=config.pk).update(is_published=False)
        config.is_published = True
        config.published_at = timezone.now()
        config.save(update_fields=["is_published", "published_at"])
        AuditLog.objects.create(
            actor=request.user, action="algorithm_config.publish", target_type="AlgorithmConfig",
            target_id=str(config.pk), after={"version": config.version}, request_id=request.request_id,
        )
        return Response({"data": self.get_serializer(config).data})


class AdminContentViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAdminRole]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class AnnouncementAdminViewSet(AdminContentViewSet):
    serializer_class = AnnouncementAdminSerializer
    queryset = Announcement.objects.order_by("-created_at")


class HelpArticleAdminViewSet(AdminContentViewSet):
    serializer_class = HelpArticleAdminSerializer
    queryset = HelpArticle.objects.order_by("sort_order", "title")
