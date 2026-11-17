"""演示数据语义质量回归测试。"""
import random
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

from apps.items.management.commands.seed_demo import (
    CATEGORY_SPECS,
    ITEM_PROFILES,
    LEAF_NAMES,
    demo_item_profile,
    demo_item_text,
    distinguish_duplicate_titles,
)
from apps.items.models import Item


def test_every_leaf_category_has_a_realistic_profile():
    expected = {
        "phone", "earphone", "computer-accessory", "charger", "campus-card", "id-holder",
        "book", "notebook", "pen-case", "umbrella", "bottle", "key", "clothing", "bag",
        "sports-item", "other",
    }
    assert set(ITEM_PROFILES) == expected
    for category_code in expected:
        profile = demo_item_profile(category_code, index=7)
        assert profile["name"]
        assert profile["color"]
        assert profile["feature"]


def test_non_branded_categories_never_receive_random_commercial_brands():
    for category_code in ("campus-card", "id-holder", "book", "key", "other"):
        for index in range(30):
            assert demo_item_profile(category_code, index=index)["brand"] == ""


def test_book_copy_uses_a_book_title_instead_of_a_device_brand():
    profile = demo_item_profile("book", index=1)
    title, description = demo_item_text(Item.Kind.FOUND, "逸夫图书馆", profile)
    assert "教材" in title
    assert "Huawei" not in title
    assert "华为" not in title
    assert "逸夫图书馆" in description


def test_random_profiles_are_reproducible_with_a_fixed_seed():
    first = random.Random(20261007)
    second = random.Random(20261007)
    assert [demo_item_profile("sports-item", randomizer=first) for _ in range(20)] == [
        demo_item_profile("sports-item", randomizer=second) for _ in range(20)
    ]


def test_personal_root_is_presented_as_other_without_duplicate_leaf_label():
    root_names = {code: name for code, name, _children in CATEGORY_SPECS}
    assert root_names["personal"] == "其他"
    assert LEAF_NAMES["other"] == "其他物品"


def test_duplicate_demo_titles_receive_stable_human_readable_distinctions():
    items = [
        SimpleNamespace(
            id=UUID(int=1),
            title="遗失黑色钥匙串（体育馆）",
            occurred_at=datetime(2026, 9, 20, 8, tzinfo=UTC),
        ),
        SimpleNamespace(
            id=UUID(int=2),
            title="遗失黑色钥匙串（体育馆）",
            occurred_at=datetime(2026, 9, 21, 9, tzinfo=UTC),
        ),
    ]

    distinguish_duplicate_titles(items)

    assert len({item.title for item in items}) == 2
    assert all("月" in item.title and "日" in item.title for item in items)
