"""Bruce 个性化口语学习包：7 集训练音频生成器。

读取 bruce_kit/episodes/EP*.json 文稿，用 Fish 免费档（s2.1-pro-free）真实合成：
- dlg 块：A(教练 Mia/中文) + B(母语男声) 多说话人单次生成
- shadow 块：母语男声单句 + 等比例跟读停顿
- warmup 块：教练中文提示 → 提示音 → 5 秒检索窗口 → 母语者答案

每块合成结果按内容哈希缓存于 data/.tmp/bruce_kit_cache/，中断重跑不重复计费。
输出：bruce_kit/audio/EP{n}_{slug}.mp3（-16 LUFS 响度归一）。
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from server.audio import _run, concat_mp3, make_silence, probe_duration  # noqa: E402
from server.config import TMP_DIR, load_settings  # noqa: E402
from server.tts import estimate_seconds, fish_tts_dialogue, fish_tts_segment  # noqa: E402

EPISODES_DIR = BASE_DIR / "bruce_kit" / "episodes"
OUTPUT_DIR = BASE_DIR / "bruce_kit" / "audio"
CACHE_DIR = TMP_DIR / "bruce_kit_cache"

BLOCK_GAP_S = 0.35
RETRIEVAL_WINDOW_S = 8.0
WARMUP_WINDOW_S = 5.0


def _cached_tts(kind: str, voice: str, text: str, settings: dict) -> Path:
    """按内容哈希缓存每次 TTS 输出；命中则零成本复用。"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    fingerprint = json.dumps(
        {
            "kind": kind,
            "voice": voice,
            "text": text,
            "model": settings.get("model"),
            "speed": settings.get("speed"),
            "temperature": settings.get("temperature"),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    digest = hashlib.sha1(fingerprint.encode("utf-8")).hexdigest()
    path = CACHE_DIR / f"{digest}.mp3"
    if not path.exists():
        if kind == "dlg":
            lines = [(part[0], part[1]) for part in json.loads(text)]
            path.write_bytes(fish_tts_dialogue(lines, settings))
        else:
            reference = (
                settings.get("reference_id_b") if voice == "mia" else settings.get("reference_id")
            )
            path.write_bytes(fish_tts_segment(text, settings, reference_id=str(reference)))
        print(f"    [tts] {kind}/{voice}: {len(text)} 字符 -> 缓存 {digest[:10]}")
    return path


def _make_beep(freq: int, duration: float) -> Path:
    """柔和提示音（淡入淡出），按参数确定性命名缓存。"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    out = CACHE_DIR / f"beep_{freq}_{duration:.2f}s.mp3"
    if not out.exists():
        _run([
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", f"sine=frequency={freq}:duration={duration}",
            "-af",
            f"afade=t=in:ss=0:d=0.03,afade=t=out:st={duration - 0.05}:d=0.05,volume=0.35",
            "-ar", "44100", "-ac", "1", "-b:a", "128k", str(out),
        ])
    return out


def _blocks_to_entries(blocks: list[dict], settings: dict) -> list[dict]:
    """把文稿块展开成 concat 条目 [{path, gap_before}]。"""
    entries: list[dict] = []
    for block in blocks:
        kind = block["t"]
        if kind == "dlg":
            serialized = json.dumps(block["lines"], ensure_ascii=False)
            entries.append({
                "path": _cached_tts("dlg", "duo", serialized, settings),
                "gap_before": 0.5,
            })
        elif kind == "sil":
            entries.append({"path": make_silence(float(block["sec"])), "gap_before": 0.0})
        elif kind == "beep":
            entries.append({
                "path": _make_beep(int(block["freq"]), float(block["dur"])),
                "gap_before": 0.2,
            })
        elif kind == "shadow":
            text = block["text"]
            entries.append({
                "path": _cached_tts("seg", "native", text, settings),
                "gap_before": 0.6,
            })
            pause = min(6.0, max(2.0, estimate_seconds(text) * 1.25))
            entries.append({"path": make_silence(pause), "gap_before": 0.0})
        elif kind == "warmup":
            window = float(WARMUP_WINDOW_S)
            entries.append({
                "path": _cached_tts("seg", "mia", block["cue"], settings),
                "gap_before": 0.5,
            })
            entries.append({"path": _make_beep(660, 0.25), "gap_before": 0.1})
            entries.append({"path": make_silence(window), "gap_before": 0.0})
            entries.append({"path": _make_beep(880, 0.25), "gap_before": 0.0})
            entries.append({
                "path": _cached_tts("seg", "native", block["answer"], settings),
                "gap_before": 0.0,
            })
        else:
            raise ValueError(f"未知块类型: {kind}")
    return entries


def render_episode(episode_path: Path, settings: dict) -> float:
    """渲染单集并返回时长（秒）。"""
    episode = json.loads(episode_path.read_text(encoding="utf-8"))
    out_file = OUTPUT_DIR / f"{episode['id']}_{episode['slug']}.mp3"
    print(f"  渲染 {episode['id']}《{episode['title']}》...")
    entries = _blocks_to_entries(episode["blocks"], settings)
    concat_mp3(entries, out_file)
    duration = probe_duration(out_file)
    print(f"  完成 {out_file.name}，时长 {duration:.1f}s")
    return duration


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 Bruce 个性化学习包音频")
    parser.add_argument("--only", help="只生成指定集，逗号分隔，如 EP1,EP3")
    parser.add_argument("--force", action="store_true", help="已存在的集也重新生成")
    args = parser.parse_args()

    settings = load_settings()
    if not (settings.get("fish_api_key") or "").strip():
        print("未配置 fish_api_key（data/settings.json），拒绝静默 dry-run。", file=sys.stderr)
        return 2

    only = {part.strip().upper() for part in args.only.split(",")} if args.only else None
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    episode_paths = sorted(EPISODES_DIR.glob("EP*.json"))
    if not episode_paths:
        print(f"未找到文稿: {EPISODES_DIR}", file=sys.stderr)
        return 2

    failed: list[str] = []
    for episode_path in episode_paths:
        episode = json.loads(episode_path.read_text(encoding="utf-8"))
        if only and episode["id"].upper() not in only:
            continue
        out_file = OUTPUT_DIR / f"{episode['id']}_{episode['slug']}.mp3"
        if out_file.exists() and not args.force:
            print(f"  跳过 {out_file.name}（已存在，--force 可重生成）")
            continue
        try:
            render_episode(episode_path, settings)
        except Exception as exc:  # noqa: BLE001 —— 单集失败不阻塞其余集，缓存保证续跑
            failed.append(episode["id"])
            print(f"  !! {episode['id']} 失败: {exc}", file=sys.stderr)

    print("\n==== 生成结果 ====")
    for out_file in sorted(OUTPUT_DIR.glob("EP*.mp3")):
        print(f"  {out_file.name}: {probe_duration(out_file):.1f}s")
    if failed:
        print(f"失败集（重跑本脚本将从缓存续跑）: {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
