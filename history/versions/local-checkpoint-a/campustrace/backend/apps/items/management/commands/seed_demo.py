"""生成可复现的校园演示数据。

数量合同：24 个校园地点、4 个服务站、180 条遗失、180 条招领，其中 100 对是
明确标注的合成正例。时间以 settings.DEMO_BASE_DATE 为唯一基准，禁止使用 now()
导致每次演示内容漂移。算法指标只能在 BenchmarkPair 上计算，并标注 synthetic。
"""
from __future__ import annotations

import random
import uuid
from collections import Counter, defaultdict
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.utils.dateparse import parse_datetime

from apps.accounts.models import User
from apps.administration.models import AbuseReport, PersistentTask
from apps.claims.models import ActiveReservation, Claim, ClaimEvent, HandoverAppointment, ReturnRecord
from apps.content.models import Announcement, HelpArticle, RecoveryStory
from apps.matching.engine import DEFAULT_WEIGHTS
from apps.matching.models import AlgorithmConfig, BenchmarkPair
from apps.messaging.models import Conversation, ConversationParticipant, Message
from apps.notifications.models import Notification
from apps.stations.models import CampusLocation, Station, StationMembership

from ...models import Category, Favorite, Item, ItemRevision, Subscription


SEED = 20261007
CATEGORY_SPECS = [
    ("digital", "数码设备", ["phone", "earphone", "computer-accessory", "charger"]),
    ("cards", "证件卡片", ["campus-card", "id-holder"]),
    ("study", "学习用品", ["book", "notebook", "pen-case"]),
    ("daily", "生活用品", ["umbrella", "bottle", "key"]),
    ("personal", "其他", ["clothing", "bag", "sports-item", "other"]),
]
LEAF_NAMES = {
    "phone": "手机", "earphone": "耳机", "computer-accessory": "电脑配件", "charger": "充电器",
    "campus-card": "校园卡", "id-holder": "卡套", "book": "书籍", "notebook": "纸质笔记本",
    "pen-case": "笔袋", "umbrella": "雨伞", "bottle": "水杯", "key": "钥匙",
    "clothing": "衣物", "bag": "包袋", "sports-item": "运动用品", "other": "其他物品",
}
LOCATION_NAMES = [
    "逸夫图书馆", "第一教学楼", "第二教学楼", "实验中心", "大学生活动中心", "东区食堂",
    "西区食堂", "体育馆", "田径场", "游泳馆", "一号宿舍", "二号宿舍", "三号宿舍",
    "研究生公寓", "校医院", "行政楼", "南门", "北门", "东门", "西门", "湖畔广场",
    "创新创业中心", "艺术中心",
]
# 演示物品必须按类别生成。品牌、颜色和外观特征如果全局随机组合，
# 会出现“华为书籍”“阿迪达斯校园卡”等明显失真的数据，同时污染 TF-IDF 词表。
# 每个叶子类别使用自己的实物原型，既保持样本多样性，又确保语义合理。
ITEM_PROFILES = {
    "phone": [
        {"name": "手机", "brands": ["华为", "小米", "苹果", "OPPO", "vivo"], "colors": ["黑色", "白色", "蓝色", "银色"], "feature": "装有透明保护壳，壳角有轻微使用痕迹"},
    ],
    "earphone": [
        {"name": "无线耳机充电盒", "brands": ["苹果", "华为", "索尼", "小米"], "colors": ["白色", "黑色", "蓝色"], "feature": "盒盖表面有细小划痕"},
        {"name": "蓝牙耳机", "brands": ["索尼", "华为", "小米"], "colors": ["黑色", "白色", "蓝色"], "feature": "收纳盒边缘有轻微磨损"},
    ],
    "computer-accessory": [
        {"name": "无线鼠标", "brands": ["罗技", "联想", "小米"], "colors": ["黑色", "白色", "灰色"], "feature": "底部贴有小型编号标签"},
        {"name": "U 盘", "brands": ["闪迪", "金士顿"], "colors": ["黑色", "银色", "蓝色"], "feature": "金属接口处有正常插拔痕迹"},
    ],
    "charger": [
        {"name": "Type-C 充电器", "brands": ["绿联", "倍思", "华为", "小米"], "colors": ["白色", "黑色"], "feature": "配有一条 Type-C 充电线"},
    ],
    "campus-card": [
        {"name": "校园卡", "brands": [""], "colors": ["蓝色", "红色", "绿色"], "feature": "放在不透明卡套内，公开页面已隐去姓名和学号"},
    ],
    "id-holder": [
        {"name": "挂绳卡套", "brands": [""], "colors": ["蓝色", "黑色", "透明"], "feature": "带挂绳，卡套边角有轻微磨损"},
    ],
    "book": [
        {"name": "《高等数学》教材", "brands": [""], "colors": ["蓝色", "白色"], "feature": "封面右下角有折痕，扉页信息已遮挡"},
        {"name": "《大学英语》教材", "brands": [""], "colors": ["红色", "蓝色"], "feature": "书脊处有轻微磨损，书内有少量笔记"},
        {"name": "《线性代数》教材", "brands": [""], "colors": ["绿色", "白色"], "feature": "外封套保存完整，页角有轻微卷曲"},
    ],
    "notebook": [
        {"name": "纸质笔记本", "brands": ["无印良品", "晨光", "得力", ""], "colors": ["黑色", "蓝色", "灰色", "粉色"], "feature": "硬壳封面，内页有少量课堂笔记"},
    ],
    "pen-case": [
        {"name": "笔袋", "brands": ["晨光", "得力", ""], "colors": ["黑色", "蓝色", "灰色", "粉色"], "feature": "帆布材质，拉链使用正常"},
    ],
    "umbrella": [
        {"name": "折叠伞", "brands": ["天堂", ""], "colors": ["黑色", "蓝色", "绿色", "粉色"], "feature": "伞柄处系有短挂绳"},
    ],
    "bottle": [
        {"name": "保温杯", "brands": ["膳魔师", "虎牌", "乐扣乐扣", ""], "colors": ["黑色", "白色", "银色", "粉色"], "feature": "杯身底部有轻微磕痕"},
    ],
    "key": [
        {"name": "钥匙串", "brands": [""], "colors": ["银色", "黑色"], "feature": "配有一枚小型挂件，钥匙齿形不在公开页面展示"},
    ],
    "clothing": [
        {"name": "连帽外套", "brands": ["优衣库", ""], "colors": ["黑色", "灰色", "蓝色"], "feature": "衣服内侧有可用于核验的非公开特征"},
    ],
    "bag": [
        {"name": "双肩包", "brands": ["耐克", "阿迪达斯", "JanSport", ""], "colors": ["黑色", "灰色", "蓝色"], "feature": "帆布材质，侧面有水杯收纳袋"},
    ],
    "sports-item": [
        {"name": "羽毛球拍", "brands": ["尤尼克斯", "李宁", ""], "colors": ["黑色", "蓝色", "红色"], "feature": "拍柄缠有防滑手胶"},
        {"name": "运动护腕", "brands": ["耐克", "阿迪达斯", "李宁", ""], "colors": ["黑色", "蓝色", "红色"], "feature": "布面有正常使用痕迹"},
    ],
    "other": [
        {"name": "眼镜盒", "brands": [""], "colors": ["黑色", "蓝色", "灰色"], "feature": "硬壳外观，内部放有擦镜布"},
        {"name": "手表表带", "brands": [""], "colors": ["黑色", "蓝色", "粉色"], "feature": "硅胶材质，扣环处有轻微使用痕迹"},
    ],
}


def demo_item_profile(category_code: str, *, index: int | None = None, randomizer=None) -> dict[str, str]:
    """返回与类别语义一致的演示物品特征。

    基准正例通过 ``index`` 可复现地轮换原型、品牌和颜色；非基准样本则使用
    注入的伪随机器抽样。品牌从类别专属候选集选择，不允许跨类别全局拼接。
    """
    profiles = ITEM_PROFILES[category_code]
    if randomizer is not None:
        profile = randomizer.choice(profiles)
        brand = randomizer.choice(profile["brands"])
        color = randomizer.choice(profile["colors"])
    else:
        if index is None:
            raise ValueError("index 和 randomizer 必须至少提供一个")
        profile = profiles[index % len(profiles)]
        brand = profile["brands"][(index // len(profiles)) % len(profile["brands"])]
        color = profile["colors"][index % len(profile["colors"])]
    return {"name": profile["name"], "brand": brand, "color": color, "feature": profile["feature"]}


def demo_item_text(kind: str, location_name: str, profile: dict[str, str]) -> tuple[str, str]:
    """用自然的中文句式组装标题和描述，避免机械的“品牌+类别”文案。"""
    color = profile["color"]
    brand = profile["brand"]
    name = profile["name"]
    brand_text = f"，品牌为{brand}" if brand else ""
    if kind == Item.Kind.LOST:
        title = f"遗失{color}{brand}{name}（{location_name}）"
        description = f"在{location_name}附近遗失一件{color}{name}{brand_text}，{profile['feature']}。"
    else:
        title = f"拾到{color}{brand}{name}（{location_name}）"
        description = f"在{location_name}拾到一件{color}{name}{brand_text}，{profile['feature']}。"
    return title, description


def distinguish_duplicate_titles(items: list[Item]) -> None:
    """只为同一类型、颜色与地点碰撞的演示线索增加日期区分。

    真实校园中可以同时存在多串钥匙或多把雨伞，因此不能删除样本；
    但公开列表不应出现完全相同的标题。日期仍不足以区分时再加入时段，
    极端情况才使用顺序标识。
    """
    grouped: dict[str, list[Item]] = defaultdict(list)
    for item in items:
        grouped[item.title].append(item)

    used_titles = {title for title, group in grouped.items() if len(group) == 1}
    for title, group in grouped.items():
        if len(group) == 1:
            continue
        stem = title[:-1] if title.endswith("）") else title
        closing = "）" if title.endswith("）") else ""
        for position, item in enumerate(sorted(group, key=lambda entry: (entry.occurred_at, str(entry.id))), start=1):
            date_label = f"{item.occurred_at.month}月{item.occurred_at.day}日"
            candidate = f"{stem}·{date_label}{closing}"
            if candidate in used_titles:
                candidate = f"{stem}·{date_label}{item.occurred_at.hour:02d}时{closing}"
            if candidate in used_titles:
                candidate = f"{stem}·{date_label}线索{position:02d}{closing}"
            item.title = candidate
            used_titles.add(candidate)


class Command(BaseCommand):
    help = "生成固定 360 条物品与 100 对合成正例；重复执行前需显式 --reset-demo"

    def add_arguments(self, parser):
        parser.add_argument("--reset-demo", action="store_true", help="仅清除 is_demo=True 的物品和关联基准后重建")

    @transaction.atomic
    def handle(self, *args, **options):
        existing = Item.objects.filter(is_demo=True)
        if existing.exists() and not options["reset_demo"]:
            raise CommandError("演示数据已存在；确认后使用 --reset-demo 可重建")
        if options["reset_demo"]:
            # 先清理受 PROTECT 约束的演示流程数据，再删除物品。
            demo_claims = Claim.objects.filter(Q(found_item__in=existing) | Q(related_lost_item__in=existing))
            Conversation.objects.filter(Q(item__in=existing) | Q(claim__in=demo_claims) | Q(subject__startswith="[演示]")).delete()
            ReturnRecord.objects.filter(Q(found_item__in=existing) | Q(claim__in=demo_claims)).delete()
            HandoverAppointment.objects.filter(claim__in=demo_claims).delete()
            ActiveReservation.objects.filter(Q(found_item__in=existing) | Q(claim__in=demo_claims)).delete()
            ClaimEvent.objects.filter(claim__in=demo_claims).delete()
            demo_claims.delete()
            RecoveryStory.objects.filter(slug__startswith="demo-").delete()
            Notification.objects.filter(category__startswith="DEMO_").delete()
            PersistentTask.objects.filter(payload__is_demo=True).delete()
            Subscription.objects.filter(name__startswith="演示·").delete()
            existing.delete()

        randomizer = random.Random(SEED)
        base_date = parse_datetime(settings.DEMO_BASE_DATE)
        if base_date is None:
            raise CommandError("DEMO_BASE_DATE 必须是带时区的 ISO 8601 时间")

        users = self._users()
        categories = self._categories()
        locations, stations = self._locations_and_stations()
        self._memberships(users, stations)
        self._algorithm_config(users["admin"])

        lost_items: list[Item] = []
        found_items: list[Item] = []
        positive_pairs: list[tuple[Item, Item]] = []
        leaf_categories = list(categories.values())

        for index in range(100):
            category = leaf_categories[index % len(leaf_categories)]
            location = locations[(index * 5) % len(locations)]
            profile = demo_item_profile(category.code, index=index)
            lost_title, lost_description = demo_item_text(Item.Kind.LOST, location.name, profile)
            found_title, found_description = demo_item_text(Item.Kind.FOUND, location.name, profile)
            lost_time = base_date + timedelta(days=index % 40, hours=index % 12)
            found_time = lost_time + timedelta(hours=1 + index % 72)
            lost = self._item(
                users[f"user{index % 8}"], Item.Kind.LOST, category, location, stations[index % 4],
                lost_title, lost_description,
                profile["color"], profile["brand"], lost_time,
            )
            found = self._item(
                users[f"user{(index + 3) % 8}"], Item.Kind.FOUND, category, location, stations[index % 4],
                found_title, found_description,
                profile["color"], profile["brand"], found_time,
            )
            lost_items.append(lost)
            found_items.append(found)
            positive_pairs.append((lost, found))

        for index in range(80):
            category = randomizer.choice(leaf_categories)
            lost_location = randomizer.choice(locations)
            found_location = randomizer.choice(locations)
            lost_profile = demo_item_profile(category.code, randomizer=randomizer)
            found_profile = demo_item_profile(category.code, randomizer=randomizer)
            lost_title, lost_description = demo_item_text(Item.Kind.LOST, lost_location.name, lost_profile)
            found_title, found_description = demo_item_text(Item.Kind.FOUND, found_location.name, found_profile)
            lost = self._item(
                users[f"user{index % 8}"], Item.Kind.LOST, category, lost_location, stations[index % 4],
                lost_title, lost_description,
                lost_profile["color"], lost_profile["brand"],
                base_date + timedelta(days=randomizer.randrange(42), hours=randomizer.randrange(12)),
            )
            found = self._item(
                users[f"user{(index + 4) % 8}"], Item.Kind.FOUND, category, found_location, stations[(index + 1) % 4],
                found_title,
                f"{found_description[:-1]}，已送至服务站保管，领取时需核对非公开特征。",
                found_profile["color"], found_profile["brand"],
                base_date + timedelta(days=randomizer.randrange(42), hours=randomizer.randrange(12)),
            )
            self._apply_demo_state(lost, index)
            self._apply_demo_state(found, index + 3)
            lost_items.append(lost)
            found_items.append(found)

        distinguish_duplicate_titles(lost_items)
        distinguish_duplicate_titles(found_items)
        for label, collection in (("遗失", lost_items), ("招领", found_items)):
            duplicate_titles = [title for title, count in Counter(item.title for item in collection).items() if count > 1]
            if duplicate_titles:
                raise CommandError(f"{label}演示数据出现重复标题：{duplicate_titles[:5]}")
            if any(item.category.parent_id is None for item in collection):
                raise CommandError(f"{label}演示物品必须归入具体子类别，不能直接归入一级类别")

        Item.objects.bulk_create(lost_items + found_items, batch_size=200)
        revisions = []
        for item in lost_items + found_items:
            snapshot = {
                "title": item.title, "description": item.description, "category_id": item.category_id,
                "brand": item.brand, "color": item.color, "occurred_at": item.occurred_at.isoformat(),
                "location_id": item.location_id, "location_detail": item.location_detail, "station_id": item.station_id,
            }
            revisions.append(ItemRevision(item=item, revision=1, snapshot=snapshot, created_by=item.owner))
        ItemRevision.objects.bulk_create(revisions, batch_size=200)

        benchmarks = []
        for index, (lost, found) in enumerate(positive_pairs):
            split = "TRAIN" if index < 60 else "VALIDATION" if index < 80 else "TEST"
            benchmarks.append(BenchmarkPair(lost_item=lost, found_item=found, is_match=True, split=split))
        BenchmarkPair.objects.bulk_create(benchmarks, batch_size=100)
        self._workflow_data(users, lost_items, found_items, stations, base_date)

        counts = {
            "locations": CampusLocation.objects.count(),
            "stations": Station.objects.count(),
            "lost": Item.objects.filter(is_demo=True, kind=Item.Kind.LOST).count(),
            "found": Item.objects.filter(is_demo=True, kind=Item.Kind.FOUND).count(),
            "positive_pairs": BenchmarkPair.objects.filter(is_synthetic=True, is_match=True).count(),
        }
        expected = {"locations": 24, "stations": 4, "lost": 180, "found": 180, "positive_pairs": 100}
        if counts != expected:
            raise CommandError(f"种子数量不满足合同：{counts}，期望 {expected}")
        self.stdout.write(self.style.SUCCESS(f"演示数据生成完成：{counts}；基准日 {base_date.isoformat()}；随机种子 {SEED}"))

    def _users(self):
        specs = {
            "admin": ("admin_demo", "演示管理员", User.Role.ADMIN),
            "staff0": ("staff_east", "东区协调员", User.Role.STAFF),
            "staff1": ("staff_west", "西区协调员", User.Role.STAFF),
        }
        specs.update({f"user{i}": (f"student_{i + 1:02d}", f"演示同学{i + 1:02d}", User.Role.USER) for i in range(8)})
        result = {}
        for key, (username, display_name, role) in specs.items():
            user, created = User.objects.get_or_create(username=username, defaults={"display_name": display_name, "role": role})
            if created:
                user.set_password("CampusTrace!2026")
                user.save(update_fields=["password"])
            result[key] = user
        return result

    def _categories(self):
        leaves = {}
        for root_code, root_name, child_codes in CATEGORY_SPECS:
            root, _ = Category.objects.update_or_create(code=root_code, defaults={"name": root_name})
            for child_code in child_codes:
                child, _ = Category.objects.update_or_create(
                    code=child_code,
                    defaults={"name": LEAF_NAMES[child_code], "parent": root},
                )
                leaves[child_code] = child
        return leaves

    def _locations_and_stations(self):
        campus, _ = CampusLocation.objects.get_or_create(code="main-campus", defaults={"name": "主校区", "aliases": ["本部"]})
        locations = []
        for index, name in enumerate(LOCATION_NAMES):
            location, _ = CampusLocation.objects.get_or_create(
                code=f"zone-{index + 1:02d}",
                defaults={"name": name, "parent": campus, "aliases": [name.replace("逸夫", "校")] if index == 0 else []},
            )
            locations.append(location)
        station_specs = [("east", "东区拾光站", 4), ("west", "西区拾光站", 6), ("library", "图书馆服务点", 0), ("south", "南门值班点", 16)]
        stations = []
        for code, name, location_index in station_specs:
            station, _ = Station.objects.get_or_create(
                code=code,
                defaults={"name": name, "location": locations[location_index], "address": f"{locations[location_index].name}服务台", "opening_hours": {"weekdays": "08:00-20:00"}},
            )
            stations.append(station)
        return locations, stations

    @staticmethod
    def _memberships(users, stations):
        StationMembership.objects.get_or_create(user=users["staff0"], station=stations[0])
        StationMembership.objects.get_or_create(user=users["staff0"], station=stations[2])
        StationMembership.objects.get_or_create(user=users["staff1"], station=stations[1])
        StationMembership.objects.get_or_create(user=users["staff1"], station=stations[3])

    @staticmethod
    def _algorithm_config(admin):
        AlgorithmConfig.objects.get_or_create(
            version="tfidf-six-factor-v1.0.0",
            defaults={
                "name": "TF-IDF 六因子初始配置",
                "weights": DEFAULT_WEIGHTS,
                "thresholds": {"min_coverage": 0.60, "time_tau_days": 7, "time_tolerance_hours": 6},
                "preprocessing": {
                    "dictionary_version": "campus-dict-v1",
                    "aliases": {"校图": "图书馆", "校园一卡通": "校园卡", "索尼": "sony"},
                    "stop_words": ["的", "一个", "物品", "东西"],
                    "custom_words": ["图书馆", "校园卡", "充电盒"],
                },
                "is_published": True,
                "created_by": admin,
                "published_at": parse_datetime(settings.DEMO_BASE_DATE),
            },
        )

    @staticmethod
    def _item(owner, kind, category, location, station, title, description, color, brand, occurred_at):
        return Item(
            id=uuid.uuid4(), owner=owner, kind=kind, category=category, title=title, description=description,
            brand=brand, color=color, occurred_at=occurred_at, location=location,
            location_detail=f"{location.name}演示精确位置（受保护）", station=station,
            review_status=Item.ReviewStatus.APPROVED, business_status=Item.BusinessStatus.OPEN,
            published_revision=1, approved_at=occurred_at + timedelta(hours=2), is_demo=True,
        )

    @staticmethod
    def _apply_demo_state(item, index):
        """为非基准样本构造全流程状态，但不伪造公开日期。"""
        state_cycle = [
            (Item.ReviewStatus.DRAFT, Item.BusinessStatus.OPEN),
            (Item.ReviewStatus.PENDING, Item.BusinessStatus.OPEN),
            (Item.ReviewStatus.REJECTED, Item.BusinessStatus.OPEN),
            (Item.ReviewStatus.APPROVED, Item.BusinessStatus.OPEN),
            (Item.ReviewStatus.APPROVED, Item.BusinessStatus.CLOSED),
            (Item.ReviewStatus.APPROVED, Item.BusinessStatus.EXPIRED),
            (Item.ReviewStatus.APPROVED, Item.BusinessStatus.RETURNED),
            (Item.ReviewStatus.APPROVED, Item.BusinessStatus.OPEN),
        ]
        review_status, business_status = state_cycle[index % len(state_cycle)]
        item.review_status = review_status
        item.business_status = business_status
        if review_status == Item.ReviewStatus.DRAFT:
            item.submitted_at = None
            item.approved_at = None
            item.published_revision = None
        elif review_status == Item.ReviewStatus.PENDING:
            item.submitted_at = item.occurred_at + timedelta(hours=1)
            item.approved_at = None
            item.published_revision = None
        elif review_status == Item.ReviewStatus.REJECTED:
            item.submitted_at = item.occurred_at + timedelta(hours=1)
            item.approved_at = None
            item.published_revision = None
            item.review_note = "演示：图片或描述信息需要补充"

    @staticmethod
    def _workflow_data(users, lost_items, found_items, stations, base_date):
        """构造可直接演示的认领、交接、通知和运维闭环。"""
        workflow_specs = [
            (Claim.Status.SUBMITTED, 101),
            (Claim.Status.NEEDS_INFO, 102),
            (Claim.Status.APPROVED, 103),
            (Claim.Status.HANDOVER_PENDING, 104),
            (Claim.Status.COMPLETED, 105),
            (Claim.Status.REJECTED, 106),
            (Claim.Status.CANCELLED, 107),
        ]
        claims = []
        for offset, (status, item_index) in enumerate(workflow_specs):
            found_item = found_items[item_index]
            lost_item = lost_items[item_index]
            claimant = users[f"user{(offset + 1) % 8}"]
            decided = status in {
                Claim.Status.NEEDS_INFO, Claim.Status.APPROVED, Claim.Status.HANDOVER_PENDING,
                Claim.Status.COMPLETED, Claim.Status.REJECTED,
            }
            claim = Claim.objects.create(
                found_item=found_item,
                claimant=claimant,
                related_lost_item=lost_item,
                statement="我可以说明物品的非公开特征及遗失时间，请由服务站人员进行私密核验。",
                evidence={"private_answers_submitted": True, "public_secret": False},
                status=status,
                reviewed_by=users["staff0"] if decided else None,
                decision_note="演示流程记录，不包含真实个人信息。" if decided else "",
                submitted_at=base_date + timedelta(days=36, hours=offset),
                decided_at=base_date + timedelta(days=37, hours=offset) if decided else None,
            )
            ClaimEvent.objects.create(
                claim=claim, actor=claimant, from_status=Claim.Status.DRAFT,
                to_status=status, note="固定演示状态",
            )
            claims.append(claim)

        for claim in claims[2:4]:
            ActiveReservation.objects.create(
                found_item=claim.found_item, claim=claim, expires_at=base_date + timedelta(days=45)
            )
            Item.objects.filter(pk=claim.found_item_id).update(business_status=Item.BusinessStatus.RESERVED)

        pending_claim = claims[3]
        HandoverAppointment.objects.create(
            claim=pending_claim, station=stations[0], scheduled_at=base_date + timedelta(days=40, hours=2),
            code_digest=make_password("654321"), code_expires_at=base_date + timedelta(days=40, hours=3),
        )

        completed_claim = claims[4]
        completed_at = base_date + timedelta(days=39, hours=4)
        HandoverAppointment.objects.create(
            claim=completed_claim, station=stations[2], scheduled_at=completed_at - timedelta(hours=1),
            code_digest=make_password("已核销的演示口令"), code_expires_at=completed_at,
            verified_at=completed_at - timedelta(minutes=20), claimant_confirmed_at=completed_at,
            staff_confirmed_at=completed_at,
        )
        ReturnRecord.objects.create(
            claim=completed_claim, found_item=completed_claim.found_item, completed_by=users["staff0"],
            receipt_number="DEMO-RETURN-0001", completed_at=completed_at,
            metadata={"synthetic": True, "dual_confirmation": True},
        )
        Item.objects.filter(pk=completed_claim.found_item_id).update(business_status=Item.BusinessStatus.RETURNED)

        conversation = Conversation.objects.create(
            subject="[演示]认领材料补充", item=claims[1].found_item, claim=claims[1]
        )
        ConversationParticipant.objects.bulk_create([
            ConversationParticipant(conversation=conversation, user=claims[1].claimant),
            ConversationParticipant(conversation=conversation, user=users["staff0"]),
        ])
        Message.objects.create(
            conversation=conversation, sender=users["staff0"],
            body="请在认领页补充非公开特征，请勿在消息中发送密码或身份证号。",
        )
        Message.objects.create(
            conversation=conversation, sender=None, is_system=True,
            body="系统已记录该补充请求。",
        )

        for index, claim in enumerate(claims[:5]):
            Notification.objects.create(
                user=claim.claimant, category="DEMO_CLAIM", title="认领状态更新",
                body=f"演示认领已进入“{claim.get_status_display()}”阶段。",
                target_path=f"/claims/{claim.id}", metadata={"synthetic": True, "sequence": index},
            )

        AbuseReport.objects.create(
            reporter=users["user7"], item=found_items[8], reason="信息可能重复",
            detail="用于演示后台举报审核流程。", status="OPEN",
        )
        Favorite.objects.get_or_create(user=users["user0"], item=found_items[3])
        Favorite.objects.get_or_create(user=users["user0"], item=found_items[19])
        Subscription.objects.update_or_create(
            user=users["user0"], name="演示·图书馆数码线索",
            defaults={
                "criteria": {"kind": "FOUND", "q": "耳机", "location": "图书馆"},
                "minimum_score": 0.65, "is_active": True,
            },
        )
        RecoveryStory.objects.update_or_create(
            slug="demo-recovery-story",
            defaults={
                "title": "从线索到双方确认的演示找回故事",
                "body": "该内容由固定合成数据生成，用于说明匹配、认领、交接与归还闭环。",
                "is_published": True, "published_at": completed_at, "created_by": users["admin"],
                "related_item": completed_claim.found_item, "consent_recorded": True,
            },
        )
        Announcement.objects.update_or_create(
            slug="demo-privacy-announcement",
            defaults={
                "title": "认领时请使用私密核验通道", "body": "请勿在公开描述中填写姓名、学号或联系方式。",
                "is_published": True, "published_at": base_date, "created_by": users["admin"], "priority": 10,
            },
        )
        HelpArticle.objects.update_or_create(
            slug="demo-safe-claim-guide",
            defaults={
                "title": "如何安全认领物品", "body": "通过服务站核对非公开特征，完成口令核销与双方确认。",
                "is_published": True, "published_at": base_date, "created_by": users["admin"],
                "category": "认领安全", "sort_order": 1,
            },
        )
        PersistentTask.objects.create(
            task_type="benchmark_evaluation", status=PersistentTask.Status.FAILED, progress=35,
            payload={"is_demo": True, "split": "TEST"}, result={},
            error_code="benchmark_invalid_config",
            error_message="演示失败任务：配置版本校验未通过，可安全重试。",
            requested_by=users["admin"], started_at=base_date + timedelta(days=41),
            finished_at=base_date + timedelta(days=41, minutes=2),
        )
