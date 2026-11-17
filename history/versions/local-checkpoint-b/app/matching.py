"""智能匹配页面、JSON API 与反馈闭环。"""

from __future__ import annotations

from flask import Blueprint, abort, flash, g, jsonify, redirect, render_template, request, url_for

from .algorithms import rank_candidates
from .auth import login_required
from .database import get_db
from .models import get_item, get_open_opposite_items

bp = Blueprint("matching", __name__)


def _results_for(item_id: int):
    source = get_item(item_id)
    if not source:
        abort(404)
    return source, rank_candidates(source, get_open_opposite_items(source))


@bp.get("/matches/<int:item_id>")
@login_required
def matches(item_id: int):
    source, results = _results_for(item_id)
    if source.user_id != g.user.id:
        abort(404)
    feedback = {
        row["candidate_item_id"]: row["label"]
        for row in get_db().execute(
            "SELECT candidate_item_id,label FROM match_feedback WHERE user_id=? AND source_item_id=?",
            (g.user.id, item_id),
        ).fetchall()
    }
    return render_template("matches.html", source=source, results=results, feedback=feedback)


@bp.get("/api/matches/<int:item_id>")
@login_required
def match_api(item_id: int):
    source, results = _results_for(item_id)
    if source.user_id != g.user.id:
        abort(404)
    payload = []
    for result in results:
        row = {**result, "item": result["item"].to_dict()}
        payload.append(row)
    return jsonify({"algorithm": "tfidf-cosine-adaptive-linear-v1", "source_id": item_id, "results": payload})


@bp.post("/matches/<int:source_id>/feedback/<int:candidate_id>")
@login_required
def feedback(source_id: int, candidate_id: int):
    source, candidate = get_item(source_id), get_item(candidate_id)
    if not source or not candidate or source.user_id != g.user.id or source.item_type == candidate.item_type:
        abort(404)
    label = request.form.get("label")
    if label not in {"0", "1"}:
        abort(400)
    get_db().execute(
        """INSERT INTO match_feedback(user_id,source_item_id,candidate_item_id,label) VALUES(?,?,?,?)
           ON CONFLICT(user_id,source_item_id,candidate_item_id) DO UPDATE SET label=excluded.label,created_at=datetime('now','localtime')""",
        (g.user.id, source_id, candidate_id, int(label)),
    )
    get_db().commit()
    flash("感谢反馈，它将用于后续权重离线评估。", "success")
    return redirect(url_for("matching.matches", item_id=source_id))

