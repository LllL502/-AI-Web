from datetime import timedelta

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User

from .media import delete_item_media, reorder_item_media, upload_item_media
from .models import Category, Favorite, Item, Subscription
from .serializers import FavoriteSerializer, ItemSerializer, MediaAssetSerializer, SubscriptionSerializer
from .services import close_item, delete_item, record_published_item_update, review_item, submit_item, withdraw_item
from apps.stations.models import Campus, CampusLocation, Station
from apps.stations.scope import selected_campus


class ItemMetadataView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        campus_id = selected_campus(request)
        campus = Campus.objects.select_related("school").get(pk=campus_id)
        return Response({"data": {
            "campus": {
                "id": campus.pk,
                "name": campus.name,
                "school": campus.school.name,
                "is_demo": campus.school.is_demo,
            },
            "categories": list(Category.objects.filter(is_active=True).values("id", "name", "code", "parent_id").order_by("name")),
            "locations": list(CampusLocation.objects.filter(is_active=True, campus_id=campus_id).values("id", "name", "code", "parent_id").order_by("name")),
            "stations": list(Station.objects.filter(is_active=True, approval_status=Station.ApprovalStatus.APPROVED, status=Station.Status.OPEN, location__campus_id=campus_id).values("id", "name", "code", "status").order_by("name")),
        }})


class ItemMapSummaryView(APIView):
    """按公开地点聚合线索数，并提供演示虚拟地图所需的服务站关系。

    接口只返回公开区域和服务站，不返回物品的精确标点。演示校区由前端根据
    这些真实演示数据生成虚拟布局；真实校区仍由高德地图负责展示。
    """
    permission_classes = [AllowAny]

    def get(self, request):
        campus_id = selected_campus(request)
        campus = Campus.objects.select_related("school").get(pk=campus_id)
        base_queryset = Item.objects.filter(
            review_status=Item.ReviewStatus.APPROVED,
            location__campus_id=campus_id,
        )
        kind_counts = {
            row["kind"]: row["count"]
            for row in base_queryset.values("kind").annotate(count=Count("id"))
        }
        queryset = base_queryset
        kind = request.query_params.get("kind")
        if kind in Item.Kind.values:
            queryset = queryset.filter(kind=kind)
        count_rows = list(
            queryset.values("location_id", "location__name")
            .annotate(count=Count("id"))
            .order_by("-count", "location__name")
        )
        counts = {row["location_id"]: row["count"] for row in count_rows}
        stations = list(
            Station.objects.filter(is_active=True, approval_status=Station.ApprovalStatus.APPROVED, location__campus_id=campus_id)
            .values("id", "name", "status", "address", "location_id")
            .order_by("name")
        )
        stations_by_location = {}
        for station in stations:
            stations_by_location.setdefault(station["location_id"], []).append({
                "id": station["id"],
                "name": station["name"],
                "status": station["status"],
                "address": station["address"],
            })

        # 地图节点取“有公开线索的地点”和“设有服务站的地点”的并集。
        # 因此切换遗失/招领图层时，服务站不会从虚拟地图上消失。
        location_ids = set(counts) | set(stations_by_location)
        if campus.school.is_demo:
            # 演示校区的虚拟地图同时承担“可能遗失地点”的选择器职责。
            # 即使某个区域当前没有公开线索，也要显示数据库中的校内区域；
            # 公开校区根节点本身不是精确地点，因此排除。
            location_ids.update(
                CampusLocation.objects.filter(
                    campus_id=campus_id, is_active=True, parent_id__isnull=False
                ).values_list("id", flat=True)
            )
        locations = CampusLocation.objects.filter(
            campus_id=campus_id,
            is_active=True,
            id__in=location_ids,
        ).values("id", "name", "code")
        return Response({"data": {
            "kind": kind if kind in Item.Kind.values else "ALL",
            "campus": {
                "id": campus.pk,
                "name": campus.name,
                "school": campus.school.name,
                "is_demo": campus.school.is_demo,
            },
            "total": sum(counts.values()),
            "kind_totals": {
                "LOST": kind_counts.get(Item.Kind.LOST, 0),
                "FOUND": kind_counts.get(Item.Kind.FOUND, 0),
            },
            "stations": [
                {
                    "id": station["id"],
                    "name": station["name"],
                    "status": station["status"],
                    "address": station["address"],
                }
                for station in stations
            ],
            "locations": [
                {
                    "id": location["id"],
                    "name": location["name"],
                    "code": location["code"],
                    "count": counts.get(location["id"], 0),
                    "stations": stations_by_location.get(location["id"], []),
                }
                for location in locations
            ],
        }})


class ItemViewSet(viewsets.ModelViewSet):
    serializer_class = ItemSerializer
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_permissions(self):
        return [AllowAny()] if self.action in {"list", "retrieve"} else [IsAuthenticated()]

    def get_queryset(self):
        # 列表序列化会展示学校与校区。一次性连接到 school，避免每条物品各触发
        # campus、school 查询（20 条列表原先最多会多出 40 次数据库往返）。
        user = self.request.user
        queryset = Item.objects.select_related(
            "owner", "category", "location__campus__school", "station"
        ).prefetch_related("media")
        # 匿名列表不返回受保护地点，不为其增加无意义的预取查询。
        # 已登录用户的本人/管理详情则批量预取，避免 N+1。
        if user.is_authenticated:
            queryset = queryset.prefetch_related("location_candidates__location", "coordinate_candidates")
        queryset = queryset.filter(location__campus_id=selected_campus(self.request))
        public_filter = Q(
            review_status=Item.ReviewStatus.APPROVED,
            business_status=Item.BusinessStatus.OPEN,
        )
        mine = self.request.query_params.get("mine", "").lower() in {"1", "true", "yes"}
        if mine and not user.is_authenticated:
            return queryset.none()
        if mine:
            queryset = queryset.filter(owner=user)
        if not user.is_authenticated:
            queryset = queryset.filter(public_filter)
        elif user.role == User.Role.ADMIN:
            pass
        elif user.role == User.Role.STAFF:
            station_ids = user.station_memberships.filter(is_active=True).values_list("station_id", flat=True)
            queryset = queryset.filter(public_filter | Q(owner=user) | Q(station_id__in=station_ids)).distinct()
        else:
            if self.action == "list" and not mine:
                queryset = queryset.filter(public_filter)
            else:
                queryset = queryset.filter(public_filter | Q(owner=user)).distinct()
        kind = self.request.query_params.get("kind")
        category = self.request.query_params.get("category")
        location = self.request.query_params.get("location")
        station = self.request.query_params.get("station")
        review_status = self.request.query_params.get("review_status")
        business_status = self.request.query_params.get("business_status")
        days = self.request.query_params.get("days")
        query = self.request.query_params.get("q")
        if kind in Item.Kind.values:
            queryset = queryset.filter(kind=kind)
        if category:
            # 前台统一展示一级类别，物品则保存在叶子类别下。
            # 选中“数码设备”等一级类别时，必须同时筛选手机、耳机、
            # 电脑配件和充电器等直接子类。叶子类别仍然可以精确筛选。
            if str(category).isdigit():
                category_ids = Category.objects.filter(is_active=True).filter(
                    Q(pk=category) | Q(parent_id=category)
                ).values_list("id", flat=True)
                queryset = queryset.filter(category_id__in=category_ids)
            else:
                queryset = queryset.none()
        if location:
            queryset = queryset.filter(location_id=location)
        if station:
            queryset = queryset.filter(station_id=station)
        if review_status in Item.ReviewStatus.values:
            queryset = queryset.filter(review_status=review_status)
        if business_status in Item.BusinessStatus.values:
            queryset = queryset.filter(business_status=business_status)
        if days in {"7", "30"}:
            queryset = queryset.filter(occurred_at__gte=timezone.now() - timedelta(days=int(days)))
        if query:
            queryset = queryset.filter(Q(title__icontains=query) | Q(description__icontains=query))
        return queryset.order_by("-occurred_at", "-created_at")

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user, review_status=Item.ReviewStatus.DRAFT)

    def create(self, request, *args, **kwargs):
        """创建接口也遵循全站 `{data: ...}` 响应契约。

        DRF 默认会直接返回序列化对象，而项目的其他详情、
       5217表和业务接口都使用 data 包装。若不在这里统一，
        前端会在数据库已成功创建草稿后误判为保存失败。
        """
        response = super().create(request, *args, **kwargs)
        response.data = {"data": response.data}
        return response

    def retrieve(self, request, *args, **kwargs):
        return Response({"data": self.get_serializer(self.get_object()).data})

    @transaction.atomic
    def perform_update(self, serializer):
        if serializer.instance.owner_id != self.request.user.id:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("只能编辑自己的物品")
        was_published = serializer.instance.review_status == Item.ReviewStatus.APPROVED
        before = {
            "title": serializer.instance.title,
            "description": serializer.instance.description,
            "category_id": serializer.instance.category_id,
            "brand": serializer.instance.brand,
            "color": serializer.instance.color,
            "occurred_at": serializer.instance.occurred_at.isoformat(),
            "location_id": serializer.instance.location_id,
            "station_id": serializer.instance.station_id,
        }
        item = serializer.save()
        if was_published:
            record_published_item_update(item, self.request.user, before, request_id=self.request.request_id)

    def update(self, request, *args, **kwargs):
        """编辑接口沿用项目统一的 `{data: ...}` 响应结构。"""
        response = super().update(request, *args, **kwargs)
        response.data = {"data": response.data}
        return response

    def destroy(self, request, *args, **kwargs):
        delete_item(self.get_object(), request.user, request_id=request.request_id)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        item = submit_item(self.get_object(), request.user, request_id=request.request_id)
        return Response({"data": self.get_serializer(item).data})

    @action(detail=True, methods=["post"])
    def withdraw(self, request, pk=None):
        item = withdraw_item(self.get_object(), request.user, request_id=request.request_id)
        return Response({"data": self.get_serializer(item).data})

    @action(detail=True, methods=["post"], url_path="review")
    def review(self, request, pk=None):
        decision = request.data.get("decision")
        if decision not in {"APPROVE", "REJECT"}:
            return Response(
                {
                    "error": {
                        "code": "invalid_decision",
                        "message": "decision 必须为 APPROVE 或 REJECT",
                        "fields": {},
                        "request_id": request.request_id,
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        item = review_item(
            self.get_object(),
            request.user,
            approve=decision == "APPROVE",
            note=request.data.get("note", ""),
            request_id=request.request_id,
        )
        return Response({"data": self.get_serializer(item).data})

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        item = close_item(self.get_object(), request.user, request_id=request.request_id)
        return Response({"data": self.get_serializer(item).data})

    @action(
        detail=True,
        methods=["post"],
        url_path="media",
        parser_classes=[MultiPartParser, FormParser],
    )
    def upload_media(self, request, pk=None):
        """上传并安全重编码最多三张实拍照片。"""
        item = self.get_object()
        created = upload_item_media(item.pk, request.user, request.FILES.getlist("files"))
        refreshed = self.get_queryset().get(pk=item.pk)
        return Response(
            {
                "data": {
                    "created": MediaAssetSerializer(created, many=True, context={"request": request}).data,
                    "media": self.get_serializer(refreshed).data["media"],
                }
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["delete"], url_path=r"media/(?P<media_id>[^/.]+)")
    def delete_media(self, request, pk=None, media_id=None):
        item = self.get_object()
        delete_item_media(item.pk, media_id, request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["patch"], url_path="media-order")
    def media_order(self, request, pk=None):
        item = self.get_object()
        ordered = reorder_item_media(item.pk, request.data.get("media_ids", []), request.user)
        return Response({
            "data": {
                "media": MediaAssetSerializer(ordered, many=True, context={"request": request}).data,
            }
        })


class FavoriteViewSet(viewsets.ModelViewSet):
    serializer_class = FavoriteSerializer
    http_method_names = ["get", "post", "delete", "head", "options"]

    def get_queryset(self):
        return Favorite.objects.filter(user=self.request.user, item__location__campus_id=selected_campus(self.request)).select_related(
            "item__category", "item__location"
        ).order_by("-created_at")

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class SubscriptionViewSet(viewsets.ModelViewSet):
    serializer_class = SubscriptionSerializer
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        return Subscription.objects.filter(user=self.request.user).order_by("-created_at")

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
