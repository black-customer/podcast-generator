#!/usr/bin/env python
"""离线试听验收：用既有语料生成本地样片，与历史成品对照。

用法：.venv/Scripts/python scripts/r02_acceptance.py [--only 样本名]
所有输出写入 data/.tmp/r02_acceptance/。
"""
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from server import (  # noqa: E402
    audioqa,  # noqa: E402
    library,
    tts,
)
from server.config import load_settings, speech_engine_available  # noqa: E402

OUT = BASE / "data" / ".tmp" / "r02_acceptance"

# (label, topic_id, item_id, track)
CASES = [
    ("monologue-studies", "01-my-studies",
     "001-do-you-work-or-are-you-a-student", "monologue"),
    ("monologue-hometown", "01-my-studies",
     "002-where-is-your-hometown", "monologue"),
    ("dialogue-sleep", "02-sleep-healthy-eating",
     "001-sleep-and-healthy-eating-dialogue", "podcast"),
    ("dialogue-house", "01-part-1-hometown-homes-bruce-真实回答-女问男答",
     "001-what-kind-of-house-or-apartment-do-you-want-to-live-in-in-th", "podcast"),
    ("dialogue-science", "01-part-1-science-mirrors-space-bruce-真实回答",
     "001-do-you-like-science", "podcast"),
]


def ffprobe_duration(path: Path) -> float:
    import subprocess

    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
         str(path)],
        capture_output=True, text=True, timeout=60,
    )
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def main() -> int:
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else ""
    settings = load_settings()
    if not speech_engine_available(settings):
        print("本地语音引擎不可用，请检查 ChineseAccent 目录")
        return 1
    settings["dry_run"] = False

    OUT.mkdir(parents=True, exist_ok=True)
    passed, failed = [], []
    for idx, (label, topic_id, item_id, track) in enumerate(CASES, 1):
        if only and only != label:
            continue
        full = library.get_item_full(topic_id, item_id)
        src, field = library.get_track_source_text(full, track)
        if not src:
            print(f"[{idx}] {label}: 无 {track} 源文本（{field}），跳过")
            failed.append((label, "无源文本"))
            continue
        previous_path = library.item_path(topic_id, item_id) / (
            "audio_monologue.mp3" if track == "monologue" else "audio_podcast.mp3"
        )
        out = OUT / f"{idx:02d}-{label}.mp3"
        print(f"[{idx}/5] {label} voice={settings.get('kokoro_answer_voice')} "
              f"q={settings.get('kokoro_question_voice')} chars={len(src)}")
        try:
            result, qa, _eff, _words = tts._synthesize_with_qa(
                src, out, settings, force_monologue=(track == "monologue")
            )
        except tts.TTSError as exc:
            print(f"    合成失败: {exc}")
            failed.append((label, str(exc)[:200]))
            continue
        dur = result[0]
        qa_path = OUT / f"{idx:02d}-{label}.qa.json"
        audioqa.save_qa_report(qa, qa_path)
        previous_dur = ffprobe_duration(previous_path) if previous_path.exists() else 0.0
        ratio = dur / previous_dur if previous_dur else 0.0
        checks = {
            "qa_verdict": qa.get("verdict"),
            "duration_sec": round(dur, 2),
            "previous_duration_sec": round(previous_dur, 2),
            "ratio_vs_previous": round(ratio, 3) if previous_dur else None,
            "segments": result[1],
            "mode": result[3],
        }
        ok = qa.get("verdict") == "pass" and dur > 3 and (not previous_dur or 0.55 <= ratio <= 2.0)
        (passed if ok else failed).append((label, json.dumps(checks, ensure_ascii=False)))
        print(f"    {'PASS' if ok else 'FAIL'} {json.dumps(checks, ensure_ascii=False)}")

    print("\n===== R02 A/B 对照（两边都已 -16 LUFS 母带）=====")
    for idx, (label, topic_id, item_id, track) in enumerate(CASES, 1):
        if only and only != label:
            continue
        previous_path = library.item_path(topic_id, item_id) / (
            "audio_monologue.mp3" if track == "monologue" else "audio_podcast.mp3"
        )
        local_path = OUT / f"{idx:02d}-{label}.mp3"
        print(f"\n{label}\n  历史音频 : {previous_path}\n  本地音频 : {local_path}")

    print(f"\n结果: {len(passed)} PASS / {len(failed)} FAIL")
    if failed:
        for label, why in failed:
            print(f"  FAIL {label}: {why}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
