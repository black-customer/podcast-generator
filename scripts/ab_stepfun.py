#!/usr/bin/env python
"""A/B 对比：StepFun TTS 2.5 vs Fish Audio（Bruce 2026-09-20 指定）。

控制变量：同文本、同角色性别、同母带响度链（-16 LUFS / 44.1k / mono）。
唯一自变量：TTS 引擎（与随之而来的音色映射——fish 的 reference_id 无法跨引擎复刻，
StepFun 侧用官方音色表中性别对应的近似音色，并提供两个男声变体供同时评音色）。

用法：.venv/Scripts/python scripts/ab_stepfun.py
Key：读 data/.tmp/stepfun_api_key.txt（gitignored，绝不入 git/日志/回显）。
产物：data/.tmp/ab_stepfun/（gitignored），打印 fish vs stepfun 对照清单。
"""
import sys
import time
from pathlib import Path

import httpx

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from server import tts  # noqa: E402 复用 parse_dialogue
from server.audio import concat_mp3, normalize_loudness  # noqa: E402
from server.audioqa import strip_all_tags  # noqa: E402

API = "https://api.stepfun.com/v1/audio/speech"
KEY_FILE = BASE / "data" / ".tmp" / "stepfun_api_key.txt"
OUT = BASE / "data" / ".tmp" / "ab_stepfun"
MODEL = "stepaudio-2.5-tts"
INSTRUCTION = (
    "Speak in a warm, natural, conversational podcast tone, like chatting with "
    "a close friend. Relaxed pacing, genuine emotion."
)
DLG_INSTRUCTION = (
    "This is one person's line in an ongoing friendly two-person chat. Speak "
    "naturally as if mid-conversation: flow into the line, no formal ending tone."
)
MAX_CHARS = 950  # 官方上限 1000，留余量

# 音色映射：fish 女提问 → lively-girl；男回答两个变体
FEMALE_VOICE = "lively-girl"
MALE_VARIANTS = {"vibrant": "vibrant-youth", "gentleman": "soft-spoken-gentleman"}

# 对比条目（真实语料，双轨）
MONO_ITEM = ("01-my-studies", "001-do-you-work-or-are-you-a-student")  # 独白轨
DLG_ITEM = ("02-sleep-healthy-eating", "001-sleep-and-healthy-eating-dialogue")  # 对话轨


_last_call = 0.0


def synth(text: str, voice: str, key: str, instruction: str = INSTRUCTION) -> bytes:
    """单段合成。StepFun 免费档限 10 RPM → 强制 6.5s 间隔 + 429 退避重试。"""
    global _last_call
    for attempt in range(6):
        wait = _last_call + 6.5 - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_call = time.monotonic()
        try:
            r = httpx.post(
                API,
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": MODEL,
                    "input": text,
                    "voice": voice,
                    "response_format": "mp3",
                    "sample_rate": 24000,
                    "instruction": instruction,
                },
                timeout=120,
            )
            if r.status_code == 200 and len(r.content) > 1000:
                return r.content
            if r.status_code == 429:
                print(f"    429 限流，等 45s 再试（attempt {attempt + 1}）")
                time.sleep(45)
                continue
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:150]}")
        except httpx.HTTPError as e:
            print(f"    网络重试 {attempt + 1}/6 ({voice}): {e}")
    raise RuntimeError(f"StepFun 合成失败: voice={voice}")


def _clean(text: str) -> str:
    cleaned, _removed = strip_all_tags(text)
    return cleaned.strip()


def _clean_dlg_line(text: str) -> str:
    """对话行专用：除 [tag] 外，还清掉 fish 表演层专属拖腔标记。

    em-dash/省略号是 fish 模型的演绎标记（会拖腔）；StepFun 不认识，
    急收听感像"话讲一半没了"。替换成逗号保留停顿语义。
    """
    cleaned, _ = strip_all_tags(text)
    cleaned = cleaned.replace("—", ",").replace("—", ",")
    cleaned = cleaned.replace("...", ", ").replace("…", ", ")
    import re as _re

    cleaned = _re.sub(r",\s*,+", ",", cleaned)
    cleaned = _re.sub(r"\s+", " ", cleaned)
    return cleaned.strip().strip(",").strip()


def synth_long(text: str, voice: str, key: str, tag: str, out_dir: Path) -> list[Path]:
    """超长文本按句切 ≤MAX_CHARS 分段，返回分段文件列表。"""
    text = _clean(text)
    parts: list[str] = []
    cur = ""
    for sent in text.replace("!", ".").replace("?", ".").split("."):
        sent = sent.strip()
        if not sent:
            continue
        piece = (sent + ". ") if not sent.endswith(("!", "?")) else (sent + " ")
        if len(cur) + len(piece) > MAX_CHARS and cur:
            parts.append(cur.strip())
            cur = piece
        else:
            cur += piece
    if cur.strip():
        parts.append(cur.strip())
    files = []
    for i, part in enumerate(parts):
        f = out_dir / f"{tag}_p{i}.mp3"
        f.write_bytes(synth(part, voice, key))
        files.append(f)
    return files


def main() -> int:
    key = KEY_FILE.read_text(encoding="utf-8").strip()
    OUT.mkdir(parents=True, exist_ok=True)
    results: list[tuple[str, Path, Path]] = []  # (label, fish_path, stepfun_path)
    only = sys.argv[1] if len(sys.argv) > 1 else ""  # "--only dlg" / "--only mono" 可跳过

    # ---------- 1) 独白轨：同文本 × 两个男声变体 ----------
    tid, iid = MONO_ITEM
    d = BASE / "data" / "topics" / tid / "items" / iid
    fish_mono = d / "audio_monologue.mp3"
    if only != "dlg":
        mono_text = (d / "natural_english.txt").read_text(encoding="utf-8")
        for vname, voice in MALE_VARIANTS.items():
            out = OUT / f"mono_stepfun_{vname}.mp3"
            print(f"[mono/{vname}] voice={voice} chars={len(mono_text)}")
            parts = synth_long(mono_text, voice, key, f"mono_{vname}", OUT)
            concat_mp3([{"path": p, "gap_before": 0.0} for p in parts], out)
            normalize_loudness(out)
            results.append(
                (f"独白 Do you work or are you a student? · 男声={vname}", fish_mono, out)
            )
    else:
        results.append(("独白（沿用上次产物）", fish_mono, OUT / "mono_stepfun_vibrant.mp3"))
        results.append(("独白（沿用上次产物）", fish_mono, OUT / "mono_stepfun_gentleman.mp3"))

    # ---------- 2) 对话轨：A(女)/B(男) 逐行合成 × 两个男声变体 ----------
    # 源用 fish_script.txt（表演层）——fish 生成对话轨时用的就是它，控制变量必须同文本
    tid, iid = DLG_ITEM
    d = BASE / "data" / "topics" / tid / "items" / iid
    dlg_text = (d / "fish_script.txt").read_text(encoding="utf-8")
    lines = tts.parse_dialogue(dlg_text)
    if not lines:
        dlg_text = (d / "natural_english.txt").read_text(encoding="utf-8")
        lines = tts.parse_dialogue(dlg_text)
    if not lines:
        print("对话解析失败（未识别 A:/B: 行）")
        return 1
    fish_dlg = d / "audio_podcast.mp3"
    for vname, male_voice in MALE_VARIANTS.items():
        out = OUT / f"dlg_stepfun_{vname}.mp3"
        print(f"[dialog/{vname}] A={FEMALE_VOICE} B={male_voice} lines={len(lines)}")
        entries = []
        for i, (spk, body) in enumerate(lines):
            voice = FEMALE_VOICE if spk == "a" else male_voice
            f = OUT / f"dlg_{vname}_l{i:02d}.mp3"
            f.write_bytes(synth(_clean(body), voice, key))
            # 行间 0.3s 自然停顿（fish 单次生成时模型自己演绎节奏）
            entries.append({"path": f, "gap_before": 0.3 if i else 0.0})
        concat_mp3(entries, out)
        normalize_loudness(out)
        results.append((f"对话 Sleep & healthy eating · A=女 B={vname}", fish_dlg, out))

    # ---------- 2.5) v2：拼接质量上限实验（Bruce 喜欢的 gentleman 男声） ----------
    # 清拖腔标记 + 行内语境指令 + 更紧的行间停顿——验证逐行拼接最好能做到什么程度
    if only in ("", "dlg", "v2"):
        male_voice = MALE_VARIANTS["gentleman"]
        out = OUT / "dlg_stepfun_gentleman_v2.mp3"
        print(f"[dialog/v2] A={FEMALE_VOICE} B={male_voice} 清标记+语境指令+0.22s gap")
        entries = []
        for i, (spk, body) in enumerate(lines):
            voice = FEMALE_VOICE if spk == "a" else male_voice
            f = OUT / f"dlg_v2_l{i:02d}.mp3"
            f.write_bytes(synth(_clean_dlg_line(body), voice, key, instruction=DLG_INSTRUCTION))
            entries.append({"path": f, "gap_before": 0.22 if i else 0.0})
        concat_mp3(entries, out)
        normalize_loudness(out)
        results.append(("对话 v2 拼接上限实验 · gentleman", fish_dlg, out))

    # ---------- 清单 ----------
    print("\n===== A/B 对照清单（均已 -16 LUFS 归一，直接对听） =====")
    for label, fish_path, sf_path in results:
        print(f"\n{label}")
        print(f"  FISH    : {fish_path}")
        print(f"  STEPFUN : {sf_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
