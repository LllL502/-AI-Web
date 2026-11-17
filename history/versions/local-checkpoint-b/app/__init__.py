"""CampusLink 应用工厂与全局安全配置。"""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta
from pathlib import Path

import click
from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import generate_password_hash

from . import database
from .models import get_user


def _persistent_secret(instance_path: str) -> str:
    """开发/自托管时生成并复用本机密钥，避免服务重启后所有会话失效。"""
    secret_path = Path(instance_path) / ".secret_key"
    if secret_path.exists():
        return secret_path.read_text(encoding="utf-8").strip()
    secret = secrets.token_hex(32)
    secret_path.parent.mkdir(parents=True, exist_ok=True)
    secret_path.write_text(secret, encoding="utf-8")
    return secret


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("CAMPUSLINK_SECRET") or _persistent_secret(app.instance_path),
        DATABASE=str(Path(app.instance_path) / "campuslink.sqlite3"),
        PERMANENT_SESSION_LIFETIME=timedelta(days=7),
        MAX_CONTENT_LENGTH=1 * 1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("CAMPUSLINK_SECURE_COOKIES") == "1",
    )
    if test_config:
        app.config.update(test_config)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    database.init_app(app)
    if os.environ.get("CAMPUSLINK_BEHIND_PROXY") == "1":
        # 仅信任最靠近应用的一层隧道/反向代理所写入的转发头。
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    from .auth import bp as auth_bp
    from .items import bp as items_bp
    from .main import bp as main_bp
    from .matching import bp as matching_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(items_bp)
    app.register_blueprint(matching_bp)

    @app.before_request
    def load_context_and_protect_csrf() -> None:
        user_id = session.get("user_id")
        g.user = get_user(user_id) if user_id else None
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_urlsafe(24)
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            submitted = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
            if not submitted or not secrets.compare_digest(submitted, session["csrf_token"]):
                abort(400, "表单安全令牌无效，请刷新页面后重试。")

    @app.context_processor
    def inject_globals() -> dict:
        return {
            "csrf_token": session.get("csrf_token", ""),
            "now_year": datetime.now().year,
            "category_options": ["证件卡类", "数码电子", "箱包服饰", "书籍文具", "生活用品", "钥匙挂件", "其他"],
        }

    @app.template_filter("date_cn")
    def date_cn(value: str) -> str:
        try:
            return datetime.fromisoformat(value).strftime("%Y年%m月%d日 %H:%M")
        except (TypeError, ValueError):
            return value

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("404.html"), 404

    @app.errorhandler(400)
    def bad_request(error):
        return render_template("400.html", message=getattr(error, "description", "请求无效")), 400

    @app.cli.command("seed-demo")
    def seed_demo() -> None:
        """插入可直接演示算法与业务闭环的数据。"""
        database.init_db()
        db = database.get_db()
        if db.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
            click.echo("数据库已有用户，为防止覆盖已跳过演示数据。")
            return
        db.executemany(
            "INSERT INTO users(username, email, password_hash) VALUES(?, ?, ?)",
            [
                ("演示同学", "demo@campus.edu", generate_password_hash("Demo1234")),
                ("志愿服务站", "helper@campus.edu", generate_password_hash("Helper1234")),
            ],
        )
        items = [
            (1, "lost", "寻找黑色双肩包", "箱包服饰", "包上有小熊挂件，内有高等数学教材和蓝色笔记本", "图书馆二楼自习室", "2026-09-16T19:30", "黑色", "耐克", "13800000001"),
            (2, "found", "图书馆发现黑色书包", "箱包服饰", "双肩包侧面挂着小熊挂件，里面有教材", "图书馆2楼东侧自习室", "2026-09-16T20:10", "黑色", "耐克", "校园服务站"),
            (2, "found", "拾到灰色帆布袋", "箱包服饰", "袋内有水杯和文件夹", "第一食堂门口", "2026-09-14T12:20", "灰色", "", "校园服务站"),
            (1, "lost", "蓝色校园卡", "证件卡类", "卡面姓名李明，学号尾号0721", "教学楼A座三楼", "2026-09-15T09:00", "蓝色", "", "13800000001"),
            (2, "found", "A座捡到校园卡", "证件卡类", "蓝色一卡通，姓名李明，编号末尾0721", "教学楼A座3楼走廊", "2026-09-15T09:25", "蓝色", "", "校园服务站"),
            (2, "found", "白色蓝牙耳机盒", "数码电子", "苹果耳机盒，右下角有轻微划痕", "体育馆一楼", "2026-09-12T18:10", "白色", "苹果", "校园服务站"),
        ]
        db.executemany(
            """INSERT INTO items(user_id,item_type,title,category,description,location,event_time,color,brand,contact)
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
            items,
        )
        db.commit()
        click.echo("演示数据已创建。账号：demo@campus.edu / Demo1234")

    with app.app_context():
        database.init_db()
    return app
