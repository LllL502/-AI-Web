"""轻量领域模型与仓储查询函数。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .database import get_db


@dataclass(slots=True)
class User:
    id: int
    username: str
    email: str
    password_hash: str
    created_at: str


@dataclass(slots=True)
class Item:
    id: int
    user_id: int
    item_type: str
    title: str
    category: str
    description: str
    location: str
    event_time: str
    color: str
    brand: str
    contact: str
    status: str
    views: int
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def row_to_user(row) -> User | None:
    return User(**dict(row)) if row else None


def row_to_item(row) -> Item | None:
    if not row:
        return None
    keys = Item.__dataclass_fields__.keys()
    return Item(**{key: row[key] for key in keys})


def get_user(user_id: int) -> User | None:
    return row_to_user(get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())


def get_item(item_id: int) -> Item | None:
    return row_to_item(get_db().execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone())


def get_open_opposite_items(source: Item) -> list[Item]:
    rows = get_db().execute(
        """SELECT * FROM items
           WHERE item_type != ? AND status = 'open' AND id != ?
           ORDER BY event_time DESC""",
        (source.item_type, source.id),
    ).fetchall()
    return [row_to_item(row) for row in rows]

