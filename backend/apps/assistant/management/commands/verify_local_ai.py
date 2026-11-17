"""Run real local inference and save synthetic-demo-only evidence."""
import json
import time
from pathlib import Path
from types import SimpleNamespace

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.assistant.local_models import describe_image, embeddings, cosine
from apps.assistant.providers import extract_structured_description
from apps.assistant.tools import semantic_public_items
from apps.stations.models import Campus


class Command(BaseCommand):
    help = "使用真实本地视觉和向量模型验收合成演示案例，不修改业务记录"

    def handle(self, *args, **options):
        root = Path(settings.BASE_DIR).parent
        evidence = {"vision_model": settings.AI_LOCAL_VISION_MODEL,
            "embedding_model": settings.AI_LOCAL_EMBEDDING_MODEL, "synthetic_demo_only": True,
            "checks": []}
        for filename, expected in [("black-earbuds.png", "耳机"), ("black-umbrella.png", "伞")]:
            started = time.monotonic()
            path = root / "data" / "demo-images" / filename
            observation = describe_image(SimpleUploadedFile(filename, path.read_bytes(), content_type="image/png"))
            evidence["checks"].append({"check": "vision", "image": filename,
                "observation": observation, "seconds": round(time.monotonic()-started, 2),
                "passed": expected in observation})
            self.stdout.write(f"{filename}: {observation}")
        texts = ["听音乐用的黑色入耳设备，装在一个充电小盒子里", "黑色无线耳机和充电盒", "黑色折叠雨伞"]
        vectors = embeddings(texts)
        same, unrelated = cosine(vectors[0], vectors[1]), cosine(vectors[0], vectors[2])
        evidence["checks"].append({"check": "semantic_paraphrase", "dimension": len(vectors[0]),
            "related_cosine": same, "unrelated_cosine": unrelated, "passed": same > unrelated})
        campus = Campus.objects.get(code="demo-campus", school__is_demo=True)
        request = SimpleNamespace(headers={"X-Campus-ID": str(campus.pk)}, query_params={},
            build_absolute_uri=lambda value: "http://127.0.0.1:8000" + value)
        started = time.monotonic()
        candidates = semantic_public_items(request, kind="FOUND", query=texts[0], limit=5)
        evidence["checks"].append({"check": "demo_retrieval", "seconds": round(time.monotonic()-started, 2),
            "candidates": [{"id": c["id"], "title": c["title"], "score": c["semantic_similarity"]} for c in candidates],
            "passed": bool(candidates) and "耳机" in candidates[0]["description"]})
        started = time.monotonic()
        structured = extract_structured_description("昨天在图书馆丢了一副黑色耳机，充电盒上有划痕。", "LOST")
        evidence["checks"].append({"check": "real_structured_extraction", "model": structured.model,
            "simulated": structured.simulated, "draft": structured.payload,
            "seconds": round(time.monotonic()-started, 2), "passed": not structured.simulated})
        evidence["passed"] = all(row["passed"] for row in evidence["checks"])
        output = root / "artifacts" / "local-ai-verification.json"
        output.parent.mkdir(exist_ok=True)
        output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        self.stdout.write(f"Evidence: {output}")
        if not evidence["passed"]:
            raise CommandError("部分真实模型检查未通过，请查看 evidence，不能宣称验收完成。")
        self.stdout.write(self.style.SUCCESS("真实本地模型演示案例全部通过。"))
