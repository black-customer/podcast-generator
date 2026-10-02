"""Q04 合成体验基线：临时语料、无密钥、无网络调用。"""
import argparse
import json
import statistics
import sys
import tempfile
import time
from contextlib import ExitStack
from datetime import date
from pathlib import Path
from unittest.mock import patch

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
from server import library, oral_review, study_progress  # noqa: E402
from tests.test_oral_review import add_sentence  # noqa: E402


def benchmark(count: int) -> dict:
    with tempfile.TemporaryDirectory(prefix="ielts-q04-") as folder, ExitStack() as stack:
        root = Path(folder)
        topics = root / "topics"
        topics.mkdir()
        private = root / "study_private"
        for obj, name, value in ((library, "TOPICS_DIR", topics),
                                 (study_progress, "PRIVATE_DIR", private),
                                 (oral_review, "REVIEW_FILE", private / "oral_review.json")):
            stack.enter_context(patch.object(obj, name, value))
        stack.enter_context(patch.object(oral_review, "_today", lambda: date(2026, 10, 2)))
        env = {"topic": library.create_topic("Synthetic daily life")["id"]}
        for n in range(count):
            add_sentence(env, n, legacy=True)
        result = {"items": count, "measurements": {}}
        for name, fn in (("topics", library.list_topics), ("today", oral_review.today_overview),
                         ("history", oral_review.get_history)):
            started = time.perf_counter()
            fn()
            first = (time.perf_counter() - started) * 1000
            values = []
            for _ in range(20):
                started = time.perf_counter()
                fn()
                values.append((time.perf_counter() - started) * 1000)
            result["measurements"][name] = {
                "first_ms": round(first, 2), "p50_ms": round(statistics.median(values), 2),
                "p95_ms": round(sorted(values)[18], 2), "runs": 20,
            }
        return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    results = [benchmark(n) for n in (100, 500)]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))
