#!/usr/bin/env python
"""R02 真实验收：5 条代表语料走 StepFun 生产合成路径 + 技术 QA + Fish A/B 清单。

- 只调用 StepFun；key 从 data/.tmp/stepfun_api_key.txt 读入内存，绝不落盘/打印/回传。
- 合成走 tts._synthesize_with_qa（生产同路径：逐行角色音色 + 44.1kHz 标准化 + 母带 + QA），
  输出到 data/.tmp/r02_acceptance/（gitignored），不触碰 data/ 正式语料。
- 技术门：QA verdict=pass；与 Fish 成品时长比 0.55–2.0（出界即疑变速/截断）。

用法：.venv/Scripts/python scripts/r02_acceptance.py [--only N]
"""
import json
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from server import (  # noqa: E402
    audioqa,  # noqa: E402
    library,
    stepfun,
    tts,
)
from server.config import load_settings  # noqa: E402

KEY_FILE = BASE / "data" / ".tmp" / "stepfun_api_key.txt"
OUT = BASE / "data" / ".tmp" / "r02_acceptance"
FREE_TIER_SPACING = 6.5  # 免费档 10 RPM，预先匀速，少挨 429

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
    if not KEY_FILE.exists():
        print("缺少 data/.tmp/stepfun_api_key.txt（先放入 StepFun key）")
        return 1
    key = KEY_FILE.read_text(encoding="utf-8").strip()
    settings = load_settings()
    settings.update(tts_provider="stepfun", stepfun_api_key=key, dry_run=False)

    # 免费档匀速节流（脚本层；产品代码保持 Retry-After/退避语义）
    real_synth = stepfun.synthesize
    last = 0.0

    def throttled(*args, **kwargs):
        nonlocal last
        wait = last + FREE_TIER_SPACING - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        last = time.monotonic()
        return real_synth(*args, **kwargs)

    stepfun.synthesize = throttled

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
        fish_path = library.item_path(topic_id, item_id) / (
            "audio_monologue.mp3" if track == "monologue" else "audio_podcast.mp3"
        )
        out = OUT / f"{idx:02d}-{label}.mp3"
        print(f"[{idx}/5] {label} voice={settings.get('answer_voice_id')} "
              f"q={settings.get('question_voice_id')} chars={len(src)}")
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
        fish_dur = ffprobe_duration(fish_path) if fish_path.exists() else 0.0
        ratio = dur / fish_dur if fish_dur else 0.0
        checks = {
            "qa_verdict": qa.get("verdict"),
            "duration_sec": round(dur, 2),
            "fish_duration_sec": round(fish_dur, 2),
            "ratio_vs_fish": round(ratio, 3) if fish_dur else None,
            "segments": result[1],
            "mode": result[3],
        }
        ok = qa.get("verdict") == "pass" and dur > 3 and (not fish_dur or 0.55 <= ratio <= 2.0)
        (passed if ok else failed).append((label, json.dumps(checks, ensure_ascii=False)))
        print(f"    {'PASS' if ok else 'FAIL'} {json.dumps(checks, ensure_ascii=False)}")

    print("\n===== R02 A/B 对照（两边都已 -16 LUFS 母带）=====")
    for idx, (label, topic_id, item_id, track) in enumerate(CASES, 1):
        if only and only != label:
            continue
        fish_path = library.item_path(topic_id, item_id) / (
            "audio_monologue.mp3" if track == "monologue" else "audio_podcast.mp3"
        )
        print(f"\n{label}\n  FISH    : {fish_path}\n  STEPFUN : {OUT / f'{idx:02d}-{label}.mp3'}")

    print(f"\n结果: {len(passed)} PASS / {len(failed)} FAIL")
    if failed:
        for label, why in failed:
            print(f"  FAIL {label}: {why}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
