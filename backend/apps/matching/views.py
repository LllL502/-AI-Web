from django.db.models import Q
from django.db import transaction
from django.utils.decorators import method_decorator
from rest_framework import mixins, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.administration.models import AuditLog
from apps.items.models import Item
from apps.stations.scope import selected_campus

from .models import MatchCandidate, MatchRun
from .serializers import MatchRunSerializer
from .services import execute_match_run


class ComparisonView(APIView):
    """读取当前账号已有匹配运行的持久化快照，不现场伪造或重算分数。"""

    def get(self, request):
        lost_id = request.query_params.get("lost_id")
        found_id = request.query_params.get("found_id")
        queryset = MatchCandidate.objects.select_related(
            "run__query_item__category", "run__query_item__location", "run__config", "run__index_version",
            "candidate_item__category", "candidate_item__location",
        ).filter(run__query_item_id=lost_id, candidate_item_id=found_id)
        queryset = queryset.filter(run__query_item__location__campus_id=selected_campus(request), candidate_item__location__campus_id=selected_campus(request))
        if request.user.role != User.Role.ADMIN:
            queryset = queryset.filter(run__requested_by=request.user)
        candidate = queryset.order_by("-run__created_at", "rank").first()
        if candidate is None:
            return Response(
                {
                    "error": {
                        "code": "comparison_not_found",
                        "message": "未找到属于当前账号的匹配快照，请先运行智能匹配",
                        "fields": {},
                        "request_id": request.request_id,
                    }
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        source = candidate.run.query_item
        target = candidate.candidate_item
        return Response({"data": {
            "run_id": candidate.run_id,
            "rank": candidate.rank,
            "final_score": candidate.final_score,
            "coverage": candidate.coverage,
            "factors": candidate.factors,
            "explanation": candidate.explanation,
            "weights": candidate.run.config.weights,
            "config_version": candidate.run.config.version,
            "index_version": candidate.run.index_version.version,
            "source": {
                "id": str(source.pk), "title": source.title, "category": source.category.name,
                "location": source.location.name, "occurred_at": source.occurred_at,
            },
            "candidate": {
                "id": str(target.pk), "title": target.title, "category": target.category.name,
                "location": target.location.name, "occurred_at": target.occurred_at,
                "business_status": target.business_status,
            },
        }})


@method_decorator(transaction.non_atomic_requests, name="dispatch")
class MatchRunViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = MatchRunSerializer

    def get_queryset(self):
        queryset = MatchRun.objects.select_related("config", "index_version", "query_item").prefetch_related(
            "candidates__candidate_item__category", "candidates__candidate_item__location"
        )
        if self.request.user.role == User.Role.ADMIN:
            return queryset.filter(query_item__location__campus_id=selected_campus(self.request)).order_by("-created_at")
        queryset = queryset.filter(query_item__location__campus_id=selected_campus(self.request))
        return queryset.filter(requested_by=self.request.user).order_by("-created_at")

    def create(self, request, *args, **kwargs):
        try:
            item = Item.objects.get(pk=request.data.get("query_item_id"), location__campus_id=selected_campus(request))
        except (Item.DoesNotExist, ValueError, TypeError):
            return Response({"error": {"code": "item_not_found", "message": "未找到查询源物品", "fields": {}, "request_id": request.request_id}}, status=status.HTTP_404_NOT_FOUND)
        run = execute_match_run(item, request.user)
        return Response({"data": self.get_serializer(run).data}, status=status.HTTP_201_CREATED)

    def retrieve(self, request, *args, **kwargs):
        return Response({"data": self.get_serializer(self.get_object()).data})

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        """删除当前账号的一次匹配快照。

        候选结果随 MatchRun 级联删除，但物品和算法配置不受影响。
        get_queryset 已限制为当前账号/当前校区，不能跨账号删除。
        """
        run = self.get_object()
        before = {
            "query_item_id": str(run.query_item_id),
            "candidate_count": run.candidate_count,
            "status": run.status,
        }
        run_id = str(run.pk)
        run.delete()
        AuditLog.objects.create(
            actor=request.user,
            action="matching.run.delete",
            target_type="matching.MatchRun",
            target_id=run_id,
            before=before,
            after={},
            request_id=request.request_id,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
