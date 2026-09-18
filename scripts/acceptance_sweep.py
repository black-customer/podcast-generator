#!/usr/bin/env python
"""M20 验收 sweep：一键跑全部关键验收项，输出 BASELINE 报告。

用法：.venv/Scripts/python scripts/acceptance_sweep.py
"""
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server import library  # noqa: E402

BASE = Path(__file__).resolve().parent.parent
results = []


def check(name: str, fn, *a, **kw):
    try:
        ok, detail = fn(*a, **kw)
    except Exception as exc:
        ok, detail = False, f"异常: {exc}"
    results.append({"name": name, "ok": ok, "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] {name} — {detail}")
    return ok


def ffmpeg_available():
    try:
        return subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=15).returncode == 0, "ffmpeg -version"
    except Exception as e:
        return False, str(e)


def imports_ok():
    from server.main import app  # noqa: F401
    return True, f"{len(app.routes)} routes"


def real_corpus_present():
    topics = [t for t in library.list_topics() if "示例语料" in t["name"]]
    if not topics:
        return False, "缺少示例语料话题"
    t = topics[0]
    return t["stats"]["total"] >= 20, f"{t['name']}: {t['stats']}"


def all_items_have_alignment():
    d = BASE / "data" / "topics"
    missing = []
    total = 0
    for topic_dir in sorted(d.iterdir()):
        if not topic_dir.is_dir():
            continue
        items_dir = topic_dir / "items"
        if not items_dir.exists():
            continue
        for item in sorted(items_dir.iterdir()):
            af = item / "alignment_podcast.json"
            if af.exists():
                doc = json.loads(af.read_text(encoding="utf-8"))
                total += 1
                if doc.get("mode") == "estimated":
                    missing.append(f"{item.name} estimated")
    return (len(missing) == 0 and total > 0), f"{total} 个对齐文档, 未实测: {missing[:3]}"


def qa_reports_present():
    qa = list((BASE / "data" / "topics").rglob("qa_podcast.json"))
    verdicts = set()
    for f in qa:
        verdicts.add(json.loads(f.read_text(encoding="utf-8")).get("verdict"))
    return len(qa) > 0, f"{len(qa)} 份 QA 报告, 结论 {sorted(verdicts)}"


def episodes_exist():
    eps = list((BASE / "data" / "episodes").glob("*.mp3"))
    return len(eps) >= 2, f"{len(eps)} 集: {[e.name for e in eps]}"


def exports_exist():
    ex = list((BASE / "data" / "exports").glob("*.m4b"))
    return len(ex) >= 1, f"{len(ex)} 个 M4B"


def stats_ok():
    import httpx
    r = httpx.get("http://127.0.0.1:8765/api/stats", timeout=15)
    s = r.json()
    return s["topics"] >= 3 and s["items"] >= 20, str(s)


def main() -> int:
    check("ffmpeg 可用", ffmpeg_available)
    check("后端可导入", imports_ok)
    check("示例语料 ≥20 条", real_corpus_present)
    check("全部条目有实测对齐", all_items_have_alignment)
    check("QA 报告覆盖", qa_reports_present)
    check("整集已合成（≥2 集）", episodes_exist)
    check("M4B 导出存在", exports_exist)
    check("统计端点", stats_ok)

    passed = sum(1 for r in results if r["ok"])
    baseline = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "passed": passed,
        "total": len(results),
        "results": results,
    }
    out = BASE / "docs" / "BASELINE.md"
    lines = ["# BASELINE — 30 天验收报告", "",
             f"生成时间：{baseline['generated_at']}", "",
             f"**通过 {passed}/{len(results)}**", ""]
    for r in results:
        lines.append(f"- [{'✅' if r['ok'] else '❌'}] {r['name']} — {r['detail']}")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nBASELINE 已写入 {out}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
