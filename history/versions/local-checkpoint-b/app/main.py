"""门户首页与公开算法实验室。"""

from __future__ import annotations

from flask import Blueprint, render_template, request

from .algorithms.ranking import rank_candidates
from .database import get_db
from .models import get_item, get_open_opposite_items

bp = Blueprint("main", __name__)


@bp.get("/")
def home():
    db = get_db()
    stats = {
        "open": db.execute("SELECT COUNT(*) FROM items WHERE status='open'").fetchone()[0],
        "matched": db.execute("SELECT COUNT(*) FROM items WHERE status='matched'").fetchone()[0],
        "users": db.execute("SELECT COUNT(*) FROM users").fetchone()[0],
    }
    recent = db.execute(
        """SELECT items.*, users.username FROM items JOIN users ON users.id=items.user_id
           WHERE items.status='open' ORDER BY items.created_at DESC LIMIT 6"""
    ).fetchall()
    # 首页英雄卡也调用生产匹配引擎，杜绝“写死一个漂亮分数”的展示造假。
    source_row = db.execute(
        "SELECT id FROM items WHERE item_type='lost' AND status='open' ORDER BY created_at LIMIT 1"
    ).fetchone()
    hero_match = None
    if source_row:
        source = get_item(source_row["id"])
        ranked = rank_candidates(source, get_open_opposite_items(source))
        if ranked:
            hero_match = {"source": source, "result": ranked[0]}
    return render_template("home.html", stats=stats, recent=recent, hero_match=hero_match)


@bp.route("/algorithm-lab", methods=("GET", "POST"))
def algorithm_lab():
    result = None
    values = {
        "left_text": "黑色双肩包，上面有小熊挂件，内有高数教材",
        "right_text": "图书馆捡到黑色书包，侧面有小熊挂件",
        "left_location": "图书馆二楼自习室",
        "right_location": "图书馆2楼东侧自习室",
    }
    if request.method == "POST":
        values = {key: request.form.get(key, "").strip() for key in values}
        source = {
            "title": values["left_text"], "description": values["left_text"],
            "category": request.form.get("left_category", "箱包服饰"),
            "location": values["left_location"], "event_time": request.form.get("left_time", ""),
            "color": request.form.get("left_color", ""), "brand": "",
        }
        candidate = {
            "title": values["right_text"], "description": values["right_text"],
            "category": request.form.get("right_category", "箱包服饰"),
            "location": values["right_location"], "event_time": request.form.get("right_time", ""),
            "color": request.form.get("right_color", ""), "brand": "",
        }
        result = rank_candidates(source, [candidate])[0]
    return render_template("algorithm_lab.html", result=result, values=values)
