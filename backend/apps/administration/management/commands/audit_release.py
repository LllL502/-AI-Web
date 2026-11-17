"""生成发布验收审计证据。

该命令只读取项目文件和演示数据库，不修改业务数据。审计范围对应 G10：
文档、页面清单、截图、算法指标、运行日志、公开文本隐私和前端离线资源。
任何一项失败都会以非零退出码结束，避免把“文件存在”误报成验收通过。
"""

from __future__ import annotations

import csv
import json
import math
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.items.models import Item


class Command(BaseCommand):
    help = "审计 G10 发布证据并写入 artifacts/release-audit.json"

    def handle(self, *args, **options):
        project_root = Path(settings.BASE_DIR).parent
        artifacts = project_root / "artifacts"
        checks: list[dict] = []

        def record(check_id: str, name: str, passed: bool, details: dict):
            checks.append({"id": check_id, "name": name, "status": "PASS" if passed else "FAIL", "details": details})

        # 文档不是只数文件：要求 12 份 Markdown 均非空，防止空壳占位。
        doc_paths = sorted((project_root / "docs").glob("*.md"))
        short_docs = [path.name for path in doc_paths if path.stat().st_size < 200]
        record(
            "documentation",
            "申报与工程文档",
            len(doc_paths) >= 12 and not short_docs,
            {"count": len(doc_paths), "minimum": 12, "short_or_empty": short_docs},
        )

        # 页面清单须覆盖 40 个业务页与 8 个系统页；清单声明的证据也必须真实存在。
        manifest_path = artifacts / "page-manifest.json"
        manifest = self._load_json(manifest_path)
        pages = manifest.get("pages", [])
        system_pages = manifest.get("system_pages", [])
        missing_evidence = []
        for page in pages:
            for relative in page.get("evidence", []):
                if not (artifacts / relative).is_file():
                    missing_evidence.append({"page_id": page.get("page_id"), "path": relative})
        manifest_ok = (
            len(pages) == 40
            and len(system_pages) == 8
            and all(page.get("status") == "VERIFIED" for page in [*pages, *system_pages])
            and not missing_evidence
        )
        record(
            "page_manifest",
            "页面清单与证据引用",
            manifest_ok,
            {
                "business_pages": len(pages),
                "system_pages": len(system_pages),
                "verified": sum(page.get("status") == "VERIFIED" for page in pages),
                "missing_evidence": missing_evidence,
            },
        )

        # 截图索引与 PNG 文件逐项核对；不把损坏文件或零字节文件记为证据。
        screenshot_index = artifacts / "screenshot-index.csv"
        screenshot_rows = []
        if screenshot_index.is_file():
            with screenshot_index.open(encoding="utf-8-sig", newline="") as file:
                screenshot_rows = list(csv.DictReader(file))
        invalid_screenshots = []
        for row in screenshot_rows:
            screenshot = artifacts / row.get("file", "")
            valid_png = screenshot.is_file() and screenshot.stat().st_size >= 1024
            if valid_png:
                with screenshot.open("rb") as file:
                    valid_png = file.read(8) == b"\x89PNG\r\n\x1a\n"
            if row.get("status") != "PASS" or not valid_png:
                invalid_screenshots.append(row.get("file", ""))
        record(
            "screenshots",
            "截图索引与文件完整性",
            len(screenshot_rows) >= 6 and not invalid_screenshots,
            {"indexed": len(screenshot_rows), "minimum": 6, "invalid": invalid_screenshots},
        )

        # 基准必须明确标注为合成证据，并保留局限性，防止将演示结果表述成真实准确率。
        benchmark_path = artifacts / "experiment-results" / "demo-benchmark.json"
        benchmark = self._load_json(benchmark_path)
        metrics = [
            value
            for method in benchmark.get("methods", {}).values()
            for value in method.get("metrics", {}).values()
        ]
        metric_values_ok = bool(metrics) and all(
            isinstance(value, (int, float)) and math.isfinite(value) and 0 <= value <= 1 for value in metrics
        )
        split_count = sum(benchmark.get("split_counts", {}).values())
        benchmark_ok = (
            benchmark.get("evidence_kind") == "synthetic_demo_benchmark"
            and split_count == 100
            and benchmark.get("test_query_count") == 20
            and len(benchmark.get("limitations", [])) >= 3
            and metric_values_ok
        )
        record(
            "benchmark",
            "算法指标与适用边界",
            benchmark_ok,
            {
                "evidence_kind": benchmark.get("evidence_kind"),
                "pair_count": split_count,
                "test_query_count": benchmark.get("test_query_count"),
                "limitations": len(benchmark.get("limitations", [])),
            },
        )

        # 仅报告命中的文件和规则名，不把可能的敏感原文写入审计 JSON。
        log_paths = sorted((artifacts / "logs").glob("*.log"))
        log_findings = []
        log_rules = {
            "server_error": re.compile(r"Traceback|Internal Server Error|\]\s+\"[^\"]+\"\s+500\s", re.I),
            "session_cookie": re.compile(r"(?:sessionid|csrftoken)\s*=", re.I),
            "password_field": re.compile(r"(?:\"password\"|'password')\s*[:=]", re.I),
            "demo_password": re.compile(r"CampusTrace!2026", re.I),
        }
        for path in log_paths:
            content = path.read_text(encoding="utf-8", errors="replace")
            for rule_name, pattern in log_rules.items():
                if pattern.search(content):
                    log_findings.append({"file": path.name, "rule": rule_name})
        record(
            "runtime_logs",
            "运行日志错误与敏感信息扫描",
            len(log_paths) >= 6 and not log_findings,
            {"files": len(log_paths), "findings": log_findings},
        )

        # 公开文本不得携带种子配对编号、手机号或邮箱；只输出命中数量，不落原文。
        all_items = Item.objects.all()
        public_items = all_items.filter(review_status=Item.ReviewStatus.APPROVED)
        privacy_rules = {
            "synthetic_pair_identifier": re.compile(r"(?<![A-Za-z0-9])(?:CT|U|V)[-_]?\d{3,}(?![A-Za-z0-9])", re.I),
            "mainland_phone": re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
            "email_address": re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I),
        }
        privacy_counts = {name: 0 for name in privacy_rules}
        for title, description, brand, color in public_items.values_list("title", "description", "brand", "color"):
            text = " ".join(filter(None, (title, description, brand, color)))
            for rule_name, pattern in privacy_rules.items():
                if pattern.search(text):
                    privacy_counts[rule_name] += 1
        record(
            "public_privacy",
            "公开文本隐私与合成标签扫描",
            all_items.count() == 360
            and all_items.filter(kind=Item.Kind.LOST).count() == 180
            and all_items.filter(kind=Item.Kind.FOUND).count() == 180
            and public_items.count() == 300
            and not any(privacy_counts.values()),
            {
                "total_items": all_items.count(),
                "lost_items": all_items.filter(kind=Item.Kind.LOST).count(),
                "found_items": all_items.filter(kind=Item.Kind.FOUND).count(),
                "approved_public_items": public_items.count(),
                "matches": privacy_counts,
            },
        )

        # 检查源文件及生产包中真正会触发网络加载的语法；npm 锁文件中的仓库地址不属于运行时资源。
        frontend = project_root / "frontend"
        source_paths = [frontend / "index.html", *sorted((frontend / "src").rglob("*"))]
        source_paths = [path for path in source_paths if path.is_file() and path.suffix in {".html", ".vue", ".ts", ".css"}]
        dist_paths = [path for path in (frontend / "dist").rglob("*") if path.is_file() and path.suffix in {".html", ".js", ".css"}]
        remote_load_rules = {
            "remote_html_asset": re.compile(r"(?:src|href)\s*=\s*[\"']https?://", re.I),
            "remote_css_asset": re.compile(r"url\(\s*[\"']?https?://", re.I),
            "remote_runtime_request": re.compile(r"(?:fetch|EventSource|WebSocket)\s*\(\s*[\"']https?://", re.I),
            "remote_dynamic_import": re.compile(r"import\s*\(\s*[\"']https?://", re.I),
        }
        remote_findings = self._scan_files([*source_paths, *dist_paths], remote_load_rules, frontend)
        record(
            "offline_assets",
            "前端禁网与本地资源扫描",
            bool(dist_paths) and not remote_findings,
            {
                "source_files": len(source_paths),
                "dist_files": len(dist_paths),
                "remote_runtime_references": remote_findings,
            },
        )

        # 三个进程的启动参数和 Django 主机白名单必须保持 loopback 边界。
        start_script = (project_root / "scripts" / "start.ps1").read_text(encoding="utf-8")
        common_script = (project_root / "scripts" / "common.ps1").read_text(encoding="utf-8")
        package = self._load_json(frontend / "package.json")
        allowed_hosts = set(settings.ALLOWED_HOSTS)
        binding_ok = (
            '"127.0.0.1:8000"' in start_script
            and "--bind-address=127.0.0.1" in common_script
            and "--host 127.0.0.1" in package.get("scripts", {}).get("dev", "")
            and allowed_hosts <= {"127.0.0.1", "localhost"}
        )
        record(
            "loopback_binding",
            "服务仅绑定本机回环地址",
            binding_ok,
            {"allowed_hosts": sorted(allowed_hosts), "ports": [3307, 5173, 8000]},
        )

        passed = all(check["status"] == "PASS" for check in checks)
        report = {
            "schema_version": 1,
            "generated_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds"),
            "gate": "G10",
            "status": "PASS" if passed else "FAIL",
            "checks_passed": sum(check["status"] == "PASS" for check in checks),
            "checks_total": len(checks),
            "checks": checks,
            "scope_note": "该证据只覆盖列出的发布审计范围，不替代渗透测试、压力测试或真实校园准确率评估。",
        }
        output_path = artifacts / "release-audit.json"
        output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        for check in checks:
            self.stdout.write(f"[{check['status']}] {check['id']}: {check['name']}")
        self.stdout.write(f"Evidence: {output_path}")
        if not passed:
            failed_ids = ", ".join(check["id"] for check in checks if check["status"] == "FAIL")
            raise CommandError(f"G10 audit failed: {failed_ids}")
        self.stdout.write(self.style.SUCCESS(f"G10 audit passed ({len(checks)}/{len(checks)} checks)."))

    @staticmethod
    def _load_json(path: Path) -> dict:
        if not path.is_file():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    @staticmethod
    def _scan_files(paths: list[Path], rules: dict[str, re.Pattern], relative_root: Path) -> list[dict]:
        findings = []
        for path in paths:
            content = path.read_text(encoding="utf-8", errors="replace")
            for rule_name, pattern in rules.items():
                if pattern.search(content):
                    findings.append({"file": str(path.relative_to(relative_root)).replace("\\", "/"), "rule": rule_name})
        return findings
