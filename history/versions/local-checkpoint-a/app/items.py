"""物品发布、浏览、认领核验与个人中心。"""

from __future__ import annotations

from datetime import datetime

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .auth import login_required
from .database import get_db
from .models import get_item

bp = Blueprint("items", __name__)


@bp.get("/items")
def browse():
    item_type = request.args.get("type", "all")
    category = request.args.get("category", "")
    query = request.args.get("q", "").strip()
    conditions = ["items.status = 'open'"]
    params: list[str] = []
    if item_type in {"lost", "found"}:
        conditions.append("items.item_type = ?")
        params.append(item_type)
    if category:
        conditions.append("items.category = ?")
        params.append(category)
    if query:
        conditions.append("(items.title LIKE ? OR items.description LIKE ? OR items.location LIKE ?)")
        params.extend([f"%{query}%"] * 3)
    rows = get_db().execute(
        f"""SELECT items.*, users.username FROM items JOIN users ON users.id=items.user_id
            WHERE {' AND '.join(conditions)} ORDER BY items.created_at DESC""",
        params,
    ).fetchall()
    return render_template("items.html", items=rows, filters={"type": item_type, "category": category, "q": query})


@bp.get("/items/<int:item_id>")
def detail(item_id: int):
    db = get_db()
    item = db.execute(
        "SELECT items.*, users.username FROM items JOIN users ON users.id=items.user_id WHERE items.id=?",
        (item_id,),
    ).fetchone()
    if not item:
        abort(404)
    db.execute("UPDATE items SET views=views+1 WHERE id=?", (item_id,))
    db.commit()
    has_claimed = bool(g.user and db.execute(
        "SELECT id FROM claims WHERE item_id=? AND claimant_id=?", (item_id, g.user.id)
    ).fetchone())
    return render_template("item_detail.html", item=item, has_claimed=has_claimed)


@bp.route("/publish/<item_type>", methods=("GET", "POST"))
@login_required
def publish(item_type: str):
    if item_type not in {"lost", "found"}:
        abort(404)
    if request.method == "POST":
        fields = {name: request.form.get(name, "").strip() for name in (
            "title", "category", "description", "location", "event_time", "color", "brand", "contact"
        )}
        required = ("title", "category", "description", "location", "event_time", "contact")
        if any(not fields[name] for name in required):
            flash("请完整填写所有必填项。", "error")
        elif len(fields["description"]) < 10:
            flash("描述至少 10 个字符，细节越充分匹配越准确。", "error")
        else:
            cursor = get_db().execute(
                """INSERT INTO items(user_id,item_type,title,category,description,location,event_time,color,brand,contact)
                   VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (g.user.id, item_type, *(fields[name] for name in fields)),
            )
            get_db().commit()
            flash("信息发布成功，智能匹配已就绪。", "success")
            return redirect(url_for("matching.matches", item_id=cursor.lastrowid))
    return render_template("publish.html", item_type=item_type, max_time=datetime.now().strftime("%Y-%m-%dT%H:%M"))


@bp.get("/dashboard")
@login_required
def dashboard():
    db = get_db()
    mine = db.execute("SELECT * FROM items WHERE user_id=? ORDER BY created_at DESC", (g.user.id,)).fetchall()
    incoming = db.execute(
        """SELECT claims.*, items.title, users.username AS claimant_name
           FROM claims JOIN items ON items.id=claims.item_id JOIN users ON users.id=claims.claimant_id
           WHERE items.user_id=? ORDER BY claims.created_at DESC""",
        (g.user.id,),
    ).fetchall()
    outgoing = db.execute(
        """SELECT claims.*, items.title FROM claims JOIN items ON items.id=claims.item_id
           WHERE claims.claimant_id=? ORDER BY claims.created_at DESC""",
        (g.user.id,),
    ).fetchall()
    stats = {
        "published": len(mine),
        "open": sum(row["status"] == "open" for row in mine),
        "resolved": sum(row["status"] != "open" for row in mine),
        "views": sum(row["views"] for row in mine),
    }
    return render_template("dashboard.html", items=mine, incoming=incoming, outgoing=outgoing, stats=stats)


@bp.post("/items/<int:item_id>/claim")
@login_required
def claim(item_id: int):
    item = get_item(item_id)
    if not item or item.status != "open":
        abort(404)
    if item.user_id == g.user.id:
        flash("不能认领自己发布的信息。", "error")
        return redirect(url_for("items.detail", item_id=item_id))
    evidence = request.form.get("evidence", "").strip()
    if len(evidence) < 10:
        flash("请提供至少 10 个字符的私密特征，便于发布者核验。", "error")
    else:
        get_db().execute(
            """INSERT INTO claims(item_id,claimant_id,evidence) VALUES(?,?,?)
               ON CONFLICT(item_id,claimant_id) DO UPDATE SET evidence=excluded.evidence,status='pending'""",
            (item_id, g.user.id, evidence),
        )
        get_db().commit()
        flash("认领申请已提交，私密特征仅向发布者展示。", "success")
    return redirect(url_for("items.detail", item_id=item_id))


@bp.post("/claims/<int:claim_id>/<decision>")
@login_required
def decide_claim(claim_id: int, decision: str):
    if decision not in {"approved", "rejected"}:
        abort(400)
    claim_row = get_db().execute(
        """SELECT claims.*, items.user_id FROM claims JOIN items ON items.id=claims.item_id
           WHERE claims.id=?""",
        (claim_id,),
    ).fetchone()
    if not claim_row or claim_row["user_id"] != g.user.id:
        abort(404)
    get_db().execute("UPDATE claims SET status=? WHERE id=?", (decision, claim_id))
    if decision == "approved":
        get_db().execute("UPDATE items SET status='matched' WHERE id=?", (claim_row["item_id"],))
        get_db().execute(
            "UPDATE claims SET status='rejected' WHERE item_id=? AND id!=? AND status='pending'",
            (claim_row["item_id"], claim_id),
        )
    get_db().commit()
    flash("认领已确认，物品状态已同步。" if decision == "approved" else "已驳回该认领申请。", "success")
    return redirect(url_for("items.dashboard"))


@bp.post("/items/<int:item_id>/status")
@login_required
def change_status(item_id: int):
    item = get_item(item_id)
    status = request.form.get("status")
    if not item or item.user_id != g.user.id or status not in {"open", "closed"}:
        abort(404)
    get_db().execute("UPDATE items SET status=? WHERE id=?", (status, item_id))
    get_db().commit()
    flash("信息状态已更新。", "success")
    return redirect(url_for("items.dashboard"))

