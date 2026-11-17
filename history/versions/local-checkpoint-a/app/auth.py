"""用户注册、登录与会话认证。"""

from __future__ import annotations

import functools
import re

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from .database import get_db

bp = Blueprint("auth", __name__, url_prefix="/auth")


def login_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            flash("请先登录后继续操作。", "info")
            return redirect(url_for("auth.login", next=request.path))
        return view(**kwargs)
    return wrapped_view


@bp.route("/register", methods=("GET", "POST"))
def register():
    if g.user:
        return redirect(url_for("items.dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        error = None
        if not 2 <= len(username) <= 20:
            error = "用户名长度应为 2–20 个字符。"
        elif not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            error = "请输入有效的邮箱地址。"
        elif len(password) < 8 or not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
            error = "密码至少 8 位，且需同时包含字母和数字。"
        elif password != confirm:
            error = "两次输入的密码不一致。"
        elif get_db().execute("SELECT id FROM users WHERE email=? OR username=?", (email, username)).fetchone():
            error = "邮箱或用户名已被注册。"
        if error:
            flash(error, "error")
        else:
            cursor = get_db().execute(
                "INSERT INTO users(username,email,password_hash) VALUES(?,?,?)",
                (username, email, generate_password_hash(password)),
            )
            get_db().commit()
            session.clear()
            session["user_id"] = cursor.lastrowid
            session.permanent = True
            flash("注册成功，欢迎加入 CampusLink。", "success")
            return redirect(url_for("items.dashboard"))
    return render_template("register.html")


@bp.route("/login", methods=("GET", "POST"))
def login():
    if g.user:
        return redirect(url_for("items.dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = get_db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if not user or not check_password_hash(user["password_hash"], password):
            flash("邮箱或密码错误。", "error")
        else:
            session.clear()
            session["user_id"] = user["id"]
            session.permanent = True
            flash(f"欢迎回来，{user['username']}。", "success")
            next_path = request.args.get("next", "")
            return redirect(next_path if next_path.startswith("/") and not next_path.startswith("//") else url_for("items.dashboard"))
    return render_template("login.html")


@bp.post("/logout")
def logout():
    session.clear()
    flash("你已安全退出。", "info")
    return redirect(url_for("main.home"))

