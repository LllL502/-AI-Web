from django.db import transaction
from rest_framework import serializers

from apps.stations.models import CampusLocation

from .models import (
    Category,
    Favorite,
    Item,
    ItemCoordinateCandidate,
    ItemLocationCandidate,
    MediaAsset,
    Subscription,
)


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "code", "parent_id"]


class MediaAssetSerializer(serializers.ModelSerializer):
    def to_representation(self, instance):
        data = super().to_representation(instance)
        for key in ('file', 'thumbnail'):
            if data.get(key):
                data[key] += '?campus=' + str(instance.item.location.campus_id)
        return data

    class Meta:
        model = MediaAsset
        fields = ["id", "thumbnail", "file", "width", "height", "sort_order"]


class ItemSerializer(serializers.ModelSerializer):
    owner_display_name = serializers.CharField(source="owner.display_name", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)
    location_name = serializers.CharField(source="location.name", read_only=True)
    station_name = serializers.CharField(source="station.name", read_only=True, allow_null=True)
    media = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()
    image_note = serializers.SerializerMethodField()
    allowed_actions = serializers.SerializerMethodField()
    campus = serializers.IntegerField(source="location.campus_id", read_only=True)
    campus_name = serializers.CharField(source="location.campus.name", read_only=True)
    school_name = serializers.CharField(source="location.campus.school.name", read_only=True)
    location_candidates = serializers.SerializerMethodField()
    coordinate_candidates = serializers.SerializerMethodField()
    location_candidate_ids = serializers.PrimaryKeyRelatedField(
        queryset=CampusLocation.objects.filter(is_active=True), many=True, write_only=True, required=False
    )
    location_candidate_points = serializers.ListField(
        child=serializers.DictField(), write_only=True, required=False
    )

    class Meta:
        model = Item
        fields = [
            "id", "campus", "campus_name", "school_name", "owner_display_name", "kind", "category", "category_name", "title", "description",
            "brand", "color", "occurred_at", "location", "location_name", "location_detail",
            "location_candidates", "coordinate_candidates", "location_candidate_ids", "location_candidate_points", "latitude",
            "longitude", "coordinate_system", "station", "station_name", "review_status", "business_status", "review_note", "published_revision",
            "is_demo", "media", "image_url", "image_note", "allowed_actions", "created_at", "updated_at", "submitted_at", "approved_at",
        ]
        read_only_fields = [
            "review_status", "business_status", "review_note", "published_revision", "is_demo", "created_at",
            "updated_at", "submitted_at", "approved_at",
        ]

    def _public_media(self, instance):
        # get_queryset 已预取 media；在 Python 中排序可避免 SerializerMethodField
        # 重新查询，从而保持广场列表的固定查询次数。
        return sorted(
            (asset for asset in instance.media.all() if asset.is_public),
            key=lambda asset: (asset.sort_order, asset.pk),
        )

    def get_media(self, instance):
        return MediaAssetSerializer(self._public_media(instance), many=True, context=self.context).data

    def get_image_url(self, instance):
        assets = self._public_media(instance)
        if not assets:
            return None
        asset = assets[0]
        image = asset.thumbnail or asset.file
        if not image:
            return None
        request = self.context.get("request")
        url = image.url + '?campus=' + str(instance.location.campus_id)
        return request.build_absolute_uri(url) if request else url

    def get_image_note(self, instance):
        assets = self._public_media(instance)
        if instance.is_demo and assets and '/demo-reference/' in assets[0].file.name:
            return '同类实物参考照片（演示），非该失物现场实拍'
        return ''

    def _can_view_sensitive(self, instance):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        cache = getattr(self, "_sensitive_access_cache", {})
        cache_key = (user.pk, instance.pk)
        if cache_key in cache:
            return cache[cache_key]
        if user.pk == instance.owner_id or user.role == "ADMIN":
            allowed = True
        else:
            station_scope = getattr(self, "_station_scope_ids", None)
            if station_scope is None:
                station_scope = set(
                    user.station_memberships.filter(is_active=True).values_list("station_id", flat=True)
                )
                self._station_scope_ids = station_scope
            allowed = bool(user.role == "STAFF" and instance.station_id and instance.station_id in station_scope)
        cache[cache_key] = allowed
        self._sensitive_access_cache = cache
        return allowed

    def get_location_candidates(self, instance):
        """只返回授权用户可见的结构化地点；公开请求会在
        ``to_representation`` 中整体移除该字段。
        """
        # 匿名/非授权请求不触发关联查询，既避免数据泄露，也保持公开列表的查询预算。
        if not self._can_view_sensitive(instance):
            return []
        return [
            {
                "id": candidate.pk,
                "location": candidate.location_id,
                "name": candidate.location.name,
                "rank": candidate.rank,
            }
            for candidate in instance.location_candidates.all()
        ]

    def get_coordinate_candidates(self, instance):
        """真实地图候选点同样属于受保护信息，只向有权限的用户返回。"""
        if not self._can_view_sensitive(instance):
            return []
        return [
            {
                "id": candidate.pk,
                "label": candidate.label,
                "latitude": candidate.latitude,
                "longitude": candidate.longitude,
                "coordinate_system": candidate.coordinate_system,
                "rank": candidate.rank,
            }
            for candidate in instance.coordinate_candidates.all()
        ]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if not self._can_view_sensitive(instance):
            for field in (
                "location_detail", "location_candidates", "coordinate_candidates", "latitude", "longitude", "coordinate_system", "review_note"
            ):
                data.pop(field, None)
        return data

    def get_allowed_actions(self, instance):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return []
        actions = []
        if instance.owner_id == user.id and instance.review_status in {Item.ReviewStatus.DRAFT, Item.ReviewStatus.REJECTED}:
            actions.extend(["edit", "submit", "delete"])
        if instance.owner_id == user.id and instance.review_status == Item.ReviewStatus.PENDING:
            actions.append("withdraw")
        if (
            instance.owner_id == user.id
            and instance.review_status == Item.ReviewStatus.APPROVED
            and instance.business_status == Item.BusinessStatus.OPEN
        ):
            actions.extend(["edit", "delete", "close"])
        elif (
            instance.owner_id == user.id
            and instance.review_status == Item.ReviewStatus.APPROVED
            and instance.business_status in {Item.BusinessStatus.CLOSED, Item.BusinessStatus.EXPIRED}
        ):
            actions.append("delete")
        if (
            instance.owner_id != user.id
            and instance.kind == Item.Kind.FOUND
            and instance.review_status == Item.ReviewStatus.APPROVED
            and instance.business_status == Item.BusinessStatus.OPEN
        ):
            actions.append("claim")
        return actions

    def validate(self, attrs):
        instance = getattr(self, "instance", None)
        from apps.stations.scope import selected_campus
        location = attrs.get("location", getattr(instance, "location", None))
        station = attrs.get("station", getattr(instance, "station", None))
        kind = attrs.get("kind", getattr(instance, "kind", None))
        candidates = attrs.get("location_candidate_ids")
        candidate_points = attrs.get("location_candidate_points")
        if any(field in attrs for field in ('latitude','longitude','coordinate_system')):
            latitude=attrs.get('latitude',getattr(instance,'latitude',None))
            longitude=attrs.get('longitude',getattr(instance,'longitude',None))
            if latitude is None or longitude is None:
                raise serializers.ValidationError('地图标点必须同时提供经纬度')
            if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                raise serializers.ValidationError('地图坐标超出有效范围')
            if attrs.get('coordinate_system',getattr(instance,'coordinate_system',''))!='GCJ02':
                raise serializers.ValidationError('地图标点需明确使用高德GCJ-02坐标')
        if location and location.campus_id != selected_campus(self.context["request"]):
            raise serializers.ValidationError("地点不属于当前校区")
        if station and location and station.location.campus_id != location.campus_id:
            raise serializers.ValidationError("服务站与物品地点必须属于同一校区")
        if candidate_points is not None:
            normalized_points = []
            seen_points = set()
            for index, point in enumerate(candidate_points, start=1):
                try:
                    latitude = round(float(point.get("latitude")), 6)
                    longitude = round(float(point.get("longitude")), 6)
                except (TypeError, ValueError):
                    raise serializers.ValidationError(
                        {"location_candidate_points": f"第 {index} 个候选地点缺少有效经纬度"}
                    )
                if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                    raise serializers.ValidationError(
                        {"location_candidate_points": f"第 {index} 个候选地点坐标超出有效范围"}
                    )
                coordinate_system = str(point.get("coordinate_system") or "GCJ02")
                if coordinate_system != "GCJ02":
                    raise serializers.ValidationError(
                        {"location_candidate_points": "真实地图候选地点必须使用高德 GCJ-02 坐标"}
                    )
                point_key = (latitude, longitude)
                if point_key in seen_points:
                    raise serializers.ValidationError({"location_candidate_points": "候选地点不能重复"})
                seen_points.add(point_key)
                normalized_points.append(
                    {
                        "latitude": latitude,
                        "longitude": longitude,
                        "label": str(point.get("label") or "地图选点").strip()[:160],
                        "coordinate_system": coordinate_system,
                    }
                )
            attrs["location_candidate_points"] = normalized_points

        if candidates is not None or candidate_points is not None:
            candidate_count = len(candidates or []) if candidates is not None else (
                instance.location_candidates.count() if instance else 0
            )
            point_count = len(candidate_points or []) if candidate_points is not None else (
                instance.coordinate_candidates.count() if instance else 0
            )
            if candidate_count and point_count:
                raise serializers.ValidationError(
                    {"location_candidate_points": "结构化地点与真实地图坐标不能混用，请保留一种地点来源"}
                )
            limit = 5 if kind == Item.Kind.LOST else 1
            if candidate_count + point_count > limit:
                message = "遗失线索最多可选 5 个可能地点" if kind == Item.Kind.LOST else "招领线索只能选择 1 个拾获地点"
                raise serializers.ValidationError({"location_candidate_points": message})

        if candidates is not None:
            candidate_ids = [candidate.pk for candidate in candidates]
            if len(candidate_ids) != len(set(candidate_ids)):
                raise serializers.ValidationError({"location_candidate_ids": "受保护地点不能重复"})
            if location and any(candidate.campus_id != location.campus_id for candidate in candidates):
                raise serializers.ValidationError({"location_candidate_ids": "受保护地点必须属于当前校区"})
            if any(candidate.parent_id is None for candidate in candidates):
                raise serializers.ValidationError({"location_candidate_ids": "请选择校区内的具体区域，不要重复选择公开校区"})
        if instance:
            editable_draft = instance.review_status in {Item.ReviewStatus.DRAFT, Item.ReviewStatus.REJECTED}
            editable_publication = (
                instance.review_status == Item.ReviewStatus.APPROVED
                and instance.business_status == Item.BusinessStatus.OPEN
            )
            if not (editable_draft or editable_publication):
                raise serializers.ValidationError("只能编辑草稿、被驳回或仍在开放的已发布信息")
        return attrs

    @staticmethod
    def _sync_location_candidates(item, candidates):
        item.location_candidates.all().delete()
        ItemLocationCandidate.objects.bulk_create(
            [
                ItemLocationCandidate(item=item, location=location, rank=rank)
                for rank, location in enumerate(candidates, start=1)
            ]
        )

    @staticmethod
    def _sync_coordinate_candidates(item, points):
        item.coordinate_candidates.all().delete()
        ItemCoordinateCandidate.objects.bulk_create(
            [
                ItemCoordinateCandidate(item=item, rank=rank, **point)
                for rank, point in enumerate(points, start=1)
            ]
        )
        # Item 上的单坐标字段作为向后兼容镜像，只保存第一候选；真正的
        # 多点及其顺序以 ItemCoordinateCandidate 为准。
        first = points[0] if points else None
        item.latitude = first["latitude"] if first else None
        item.longitude = first["longitude"] if first else None
        item.coordinate_system = first["coordinate_system"] if first else ""
        item.save(update_fields=["latitude", "longitude", "coordinate_system", "updated_at"])

    @transaction.atomic
    def create(self, validated_data):
        candidates = validated_data.pop("location_candidate_ids", [])
        points = validated_data.pop("location_candidate_points", [])
        item = super().create(validated_data)
        self._sync_location_candidates(item, candidates)
        self._sync_coordinate_candidates(item, points)
        return item

    @transaction.atomic
    def update(self, instance, validated_data):
        instance = Item.objects.select_for_update().get(pk=instance.pk)
        self.instance = instance
        self.validate(validated_data)
        candidates = validated_data.pop("location_candidate_ids", None)
        points = validated_data.pop("location_candidate_points", None)
        item = super().update(instance, validated_data)
        if candidates is not None:
            self._sync_location_candidates(item, candidates)
        if points is not None:
            self._sync_coordinate_candidates(item, points)
        return item


class FavoriteSerializer(serializers.ModelSerializer):
    item = serializers.SerializerMethodField()
    item_id = serializers.PrimaryKeyRelatedField(source="item", queryset=Item.objects.all(), write_only=True)

    class Meta:
        model = Favorite
        fields = ["id", "item_id", "item", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate_item_id(self, item):
        """防止通过猜测 UUID 收藏他人的未公开草稿并读取摘要。"""
        request = self.context.get("request")
        user = getattr(request, "user", None)
        from apps.stations.scope import selected_campus
        if item.location.campus_id != selected_campus(request):
            raise serializers.ValidationError("不能收藏其他校区的物品")
        can_view = (item.review_status == Item.ReviewStatus.APPROVED and item.business_status == Item.BusinessStatus.OPEN) or (
            user and user.is_authenticated and (item.owner_id == user.pk or user.role == "ADMIN")
        )
        if not can_view:
            raise serializers.ValidationError("该物品尚未公开，不能收藏")
        return item

    @staticmethod
    def get_item(instance):
        item = instance.item
        return {
            "id": str(item.pk), "title": item.title, "kind": item.kind,
            "category_name": item.category.name, "location_name": item.location.name,
            "business_status": item.business_status, "occurred_at": item.occurred_at,
        }


class SubscriptionSerializer(serializers.ModelSerializer):
    def validate_criteria(self, value):
        from apps.stations.scope import selected_campus
        if not isinstance(value, dict) or set(value) - {'kind', 'q', 'category', 'location'}:
            raise serializers.ValidationError('订阅条件包含不支持的字段。')
        if value.get('kind') and value['kind'] not in Item.Kind.values:
            raise serializers.ValidationError('请选择有效信息类型。')
        if 'q' in value and (not isinstance(value['q'], str) or len(value['q']) > 200):
            raise serializers.ValidationError('关键词最多200字。')
        for field, model in [('category', Category), ('location', CampusLocation)]:
            entry = value.get(field)
            if entry in (None, ''):
                continue
            query = model.objects.filter(is_active=True)
            if field == 'location':
                query = query.filter(campus_id=selected_campus(self.context['request']))
            if isinstance(entry, bool) or not isinstance(entry, (str, int)):
                raise serializers.ValidationError('请选择有效类别或地点。')
            query = query.filter(pk=int(entry)) if str(entry).isdigit() else query.filter(name=entry)
            if not query.exists():
                raise serializers.ValidationError('类别或地点不属于当前校区的有效选项。')
        return value

    class Meta:
        model = Subscription
        fields = ["id", "campus", "name", "criteria", "minimum_score", "is_active", "created_at", "updated_at"]
        read_only_fields = ["id", "campus", "created_at", "updated_at"]
