"""SQLite 数据访问基础设施。

这里刻意使用 Python 标准库 sqlite3，而非重量级 ORM：既保持模型层清晰，
又让项目在竞赛答辩电脑上只安装 Flask 即可运行。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from flask import current_app, g


def get_db() -> sqlite3.Connection:
    """按请求创建连接，并用 Row 支持列名访问。"""
    if "db" not in g:
        db_path = Path(current_app.config["DATABASE"])
        db_path.parent.mkdir(parents=True, exist_ok=True)
        g.db = sqlite3.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_error: BaseException | None = None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    """执行幂等建表脚本。"""
    schema_path = Path(current_app.root_path).parent / "schema.sql"
    get_db().executescript(schema_path.read_text(encoding="utf-8"))


def init_app(app) -> None:
    app.teardown_appcontext(close_db)

    @app.cli.command("init-db")
    def init_db_command() -> None:
        init_db()
        print("数据库初始化完成。")

