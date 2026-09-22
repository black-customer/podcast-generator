"""Bruce 定制学习包音频生成器。

设计依据（写在这里是为了下次不用再解释为什么这么排）：
- 注意到差异（Schmidt noticing）：每道题先念他的原话错误，再紧接母语者版本。
- 检索练习：每个示范后必有一个强制输出窗口，窗口里他必须张嘴，静音不算完成。
- 交错与间隔：语块在 Track 02 首现、Track 04 被动用、Track 05 睡前重播，
  而不是在一个 track 里连着念十遍（集中练习留存最差）。
- 自我参照：所有例句都用他自己的经历，不用假想例子。

用法：
    .venv/Scripts/python scripts/build_bruce_audio.py            # 全部
    .venv/Scripts/python scripts/build_bruce_audio.py --only 01  # 单条
    .venv/Scripts/python scripts/build_bruce_audio.py --dry-run  # 只排期不花钱
"""
# ruff: noqa: E501  # 语料与 HTML 模板是数据，折行会让内容不可核对

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import bruce_kit_content as C  # noqa: E402

from server.audio import _concat_line, _run, make_silence, probe_duration  # noqa: E402
from server.config import TMP_DIR, load_settings  # noqa: E402
from server.tts import fish_tts_dialogue  # noqa: E402

for _stream in (sys.stdout, sys.stderr):  # Windows 控制台默认 GBK，中文与符号日志会崩
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

KIT_DIR = Path(__file__).resolve().parent / "learning_kit_bruce"
AUDIO_DIR = KIT_DIR / "audio"
CACHE_DIR = KIT_DIR / ".cache"

SPEED_SLOW = 0.82

STATS: dict[str, int] = {"api_calls": 0, "cache_hits": 0}


def for_tts(text: str) -> str:
    """去掉 TTS 会读崩的排版符号，保留自然标点。"""
    return (
        text.replace("「", "“")
        .replace("」", "”")
        .replace("｜", "，")
        .replace("→", " to ")
        .replace("\n", " ")
        .strip()
    )


def make_cue(freq: int, seconds: float, gain: float = 0.3) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    out = CACHE_DIR / f"cue-{freq}-{seconds:.2f}-{gain:.2f}.mp3"
    if not out.exists():
        tmp = CACHE_DIR / f"{out.stem}.{uuid.uuid4().hex[:6]}.tmp.mp3"
        _run([
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", f"sine=frequency={freq}:duration={seconds}",
            "-af", f"afade=t=in:ss=0:d=0.02,afade=t=out:st={seconds - 0.08}:d=0.08,volume={gain}",
            "-ar", "44100", "-ac", "1", "-b:a", "128k", str(tmp),
        ])
        tmp.replace(out)
    return out


def synth(lines: list[tuple[str, str]], settings: dict, speed: float | None = None) -> Path:
    """一次多说话人合成，结果按内容哈希缓存，重跑不重复花配额。"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        {"lines": [[s, t] for s, t in lines], "speed": speed, "model": settings.get("model")},
        ensure_ascii=False,
    )
    key = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
    out = CACHE_DIR / f"seg-{key}.mp3"
    if out.exists() and out.stat().st_size > 2000:
        STATS["cache_hits"] += 1
        return out
    run_settings = dict(settings) if speed is None else {**settings, "speed": speed}
    audio = fish_tts_dialogue([(sp, for_tts(tx)) for sp, tx in lines], run_settings)
    if len(audio) < 1500:
        raise RuntimeError(f"合成结果过短（{len(audio)} bytes），判定失败：{lines[0][1][:40]}")
    tmp = CACHE_DIR / f"{out.stem}.{uuid.uuid4().hex[:6]}.tmp.mp3"
    tmp.write_bytes(audio)
    tmp.replace(out)
    STATS["api_calls"] += 1
    return out


class Timeline:
    """攒条目 + 记录每个命名片段的起止时间，供视频和卡片索引使用。"""

    def __init__(self) -> None:
        self.entries: list[dict] = []
        self.cues: list[dict] = []
        self.markers: list[dict] = []
        self._t = 0.0

    def clip(self, path: Path, label: str = "", gap_before: float = 0.0) -> Timeline:
        if gap_before > 0:
            self.entries.append({"path": make_silence(gap_before), "gap_before": 0})
            self._t += gap_before
        dur = probe_duration(path)
        self.entries.append({"path": path, "gap_before": 0})
        if label:
            self.markers.append({"label": label, "start": round(self._t, 2), "duration": round(dur, 2)})
        self._t += dur
        return self

    def window(self, seconds: float, label: str = "") -> Timeline:
        """提示音 + 静音 + 提示音：强制输出窗口。"""
        start = self._t
        self.entries.append({"path": make_cue(660, 0.22), "gap_before": 0})
        self._t += 0.22
        self.entries.append({"path": make_silence(seconds), "gap_before": 0})
        self._t += seconds
        self.entries.append({"path": make_cue(880, 0.22), "gap_before": 0})
        self._t += 0.22
        self.cues.append({"start": round(start, 2), "end": round(self._t, 2), "kind": "window"})
        if label:
            self.markers.append({"label": label, "start": round(start, 2), "duration": round(seconds + 0.44, 2)})
        return self

    def echo(self, seconds: float) -> Timeline:
        """影子跟读的留白，不要提示音。"""
        self.entries.append({"path": make_silence(seconds), "gap_before": 0})
        self._t += seconds
        return self

    def render(self, out_path: Path) -> dict:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        list_file = TMP_DIR / f"kit-concat-{uuid.uuid4().hex[:8]}.txt"
        TMP_DIR.mkdir(parents=True, exist_ok=True)
        list_file.write_text(
            "\n".join(_concat_line(e["path"]) for e in self.entries) + "\n", encoding="utf-8"
        )
        try:
            _run([
                "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
                "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
                "-ar", "44100", "-ac", "1", "-b:a", "128k", str(out_path),
            ])
        finally:
            list_file.unlink(missing_ok=True)
        return {
            "file": out_path.name,
            "duration": round(probe_duration(out_path), 2),
            "markers": self.markers,
            "windows": self.cues,
        }


# ------------------------------------------------------------------ Track 01
def build_repair_lab(settings: dict, tl: Timeline) -> None:
    tl.clip(synth([
        ("a", "Bruce，这是你的英语口语体检报告。一点一万词的录音里，you know 出现两百一十九次，"
              "平均五十二个词一次；however、on the other hand、in my opinion，零次；stuff 和 things 这种含糊词，五十四次。"),
        ("b", "But here is the good news."),
        ("a", "好消息是：同一道题你录第二遍的时候，能说出 they were my deliberate choice, not imposed by the school 这种句子。"
              "这说明语法和词都在你脑子里，缺的只是那条通往嘴巴的路。所以接下来这十分钟，我不教你新知识，我只把你会的东西逼出来。"),
        ("a", "规则只有一条：听到第二声提示音响之前，你必须出声。静音不算完成。"),
    ], settings), label="xray-intro")
    tl.window(2.0)

    prev_core = ""
    for i, f in enumerate(C.FOSSILS, 1):
        lines: list[tuple[str, str]] = []
        if prev_core:
            lines.append(("b", prev_core))
            lines.append(("a", f"这一句现在归你了。第{i}号化石，{f['label_zh']}。你原来的说法是：{f['your_words']}。"))
        else:
            lines.append(("a", f"第{i}号化石，{f['label_zh']}。你原来的说法是：{f['your_words']}。"))
        lines.append(("b", f["fixed"]))
        lines.append(("a", for_tts(f["rule_zh"])))
        lines.append(("a", f"现在换你。十秒钟，把这句中文说成英语：{f['prompt_zh']}"))
        tl.clip(synth(lines, settings), label=f"fossil:{f['id']}")
        tl.window(C.WINDOW_FIRST, label=f"window:{f['id']}")
        prev_core = f["core"]

    tl.clip(synth([
        ("b", prev_core),
        ("a", "十个化石全部过完。现在压缩到考试节奏，五秒一题，我说中文你直接说英语。"
              "这一遍不许想语法，只想那个固定说法。"),
    ], settings), label="round2-intro")
    for f in C.FOSSILS[:6]:
        tl.clip(synth([("a", for_tts(f["prompt_zh"]))], settings), label=f"fast:{f['id']}")
        tl.window(C.WINDOW_FAST)
    tl.clip(synth([
        ("b", "There are too many options, and technology has changed the way we learn."),
        ("a", "第一遍的录音你已经有了。二十一天后重录同一批题，你会听到一个不一样的自己。"),
    ], settings), label="outro")


# ------------------------------------------------------------------ Track 02
def build_chunk_gym(settings: dict, tl: Timeline) -> None:
    tl.clip(synth([
        ("a", "语块健身房。二十个语块，每一个都对应你稿子里一处真实的坑。"
              "记住目标不是认识它们，是能在五秒内把它们放进自己的句子里。"),
    ], settings), label="gym-intro")
    prev: dict | None = None
    for i, ch in enumerate(C.CHUNKS, 1):
        lines: list[tuple[str, str]] = []
        if prev:
            lines.append(("b", prev["example_b"]))
            lines.append(("a", f"注意这是它的第二个战场。语块{i}，{ch['chunk']}。"))
        else:
            lines.append(("a", f"语块一，{ch['chunk']}。"))
        lines.append(("b", ch["example_a"]))
        lines.append(("a", f"{ch['zh']}。你原来的说法是 {ch['wrong']}。{for_tts(ch['usage_zh'])}"))
        lines.append(("a", f"现在用 {ch['chunk']} 说一句你自己身上真实发生过的事，九秒。"))
        tl.clip(synth(lines, settings), label=f"chunk:{ch['id']}")
        tl.window(9.0, label=f"window:{ch['id']}")
        prev = ch

    tl.clip(synth([
        ("b", prev["example_b"]),
        ("a", "二十个语块过完。接下来反向检索：我只说中文，你说英语，四秒。"),
    ], settings), label="gym-recall-intro")
    for ch in C.CHUNKS:
        tl.clip(synth([("a", ch["zh"])], settings), label=f"recall:{ch['id']}")
        tl.window(4.0)
    tl.clip(synth([
        ("a", "今天就到这。明天睡前听第五轨，它会替你把这二十个再走一遍。"),
    ], settings), label="gym-outro")


# ------------------------------------------------------------------ Track 03
def build_shadow_stress(settings: dict, tl: Timeline) -> None:
    tl.clip(synth([
        ("a", "第三轨，句子节奏。英语是重音计时语言，中文是音节计时语言，这就是你听起来平的原因。"
              "规则：实词重读并拖长，虚词一带而过。每句之后留给你一段空白，跟读，不是复述意思，是模仿旋律。"),
        ("a", "另外这条轨里给你一个替换动作：想说 you know 的时候，闭嘴半秒。沉默听起来像思考，you know 听起来像慌张。"),
    ], settings), label="shadow-intro")

    for m in C.MODELS:
        tl.clip(synth([("a", f"{m['title_zh']}。先逐句跟读。")], settings), label=f"model-head:{m['id']}", gap_before=0.5)
        for j, s in enumerate(m["sentences"], 1):
            path = synth([("b", s)], settings)
            tl.clip(path, label=f"line:{m['id']}:{j}")
            tl.echo(max(1.6, probe_duration(path) * 1.35))
        tl.clip(synth([
            ("a", "现在按考试语速连起来说，跟着我。"),
            ("b", " ".join(m["sentences"])),
        ], settings), label=f"run:{m['id']}", gap_before=0.8)
        tl.echo(1.0)

    hardest = C.MODELS[-1]
    tl.clip(synth([("a", "最后一段最难的，慢速再走一遍，听清楚每个重音之间的停顿。")], settings),
            label="slow-intro", gap_before=0.6)
    for j, s in enumerate(hardest["sentences"], 1):
        path = synth([("b", s)], settings, speed=SPEED_SLOW)
        tl.clip(path, label=f"slow:{hardest['id']}:{j}")
        tl.echo(max(2.0, probe_duration(path) * 1.6))
    tl.clip(synth([
        ("a", "把这段和第一轨连起来听，你已经在用自己的话说八分句子了，只是速度还没上来。"),
    ], settings), label="shadow-outro", gap_before=0.6)


# ------------------------------------------------------------------ Track 04
def build_gauntlet(settings: dict, tl: Timeline) -> None:
    tl.clip(synth([
        ("a", "考官快问快答。这一轨没有提示，没有暂停键，练的是你在压力下敢不敢开口。"
              "Part 3 之前先记住四步骨架。第一步表态，别再来一百二十五个 I think。"),
        ("b", "The way I see it, it's not really about the technology itself."),
        ("a", "第二步给理由，一句就够。"),
        ("b", "And the main reason is that it dumped far too many choices on us."),
        ("a", "第三步落到你自己身上，这块你其实最擅长，你只是从来没标记过它。"),
        ("b", "Take my own case — I spent a week comparing language apps and studied none of them."),
        ("a", "第四步让步收口，这是你整份稿子里完全消失的一个动作。"),
        ("b", "That said, it does depend on the person."),
        ("a", "四步连起来，就是一篇七到八分的答案。现在开考。"),
    ], settings), label="gauntlet-intro")

    block: list[dict] = []
    for i, item in enumerate(C.GAUNTLET, 1):
        chunk = next((c for c in C.CHUNKS if c["chunk"].lower() in item["must_use"].lower()
                      or item["must_use"].lower() in c["chunk"].lower()), None)
        head = f"第{i}题。" if item["part"] == 1 else f"第{i}题，Part 3，用上 {item['must_use']}。"
        tl.clip(synth([("a", head + item["q"])], settings), label=f"q:{i}")
        tl.window(float(item["window"]))
        if chunk:
            block.append({"q": item["q"], "must_use": item["must_use"], "chunk": chunk})
        if len(block) == 4:
            lines: list[tuple[str, str]] = [("a", "刚才四题，挑两题给你参考说法。")]
            for b in block[:2]:
                lines.append(("a", b["q"]))
                lines.append(("b", b["chunk"]["example_a"]))
            tl.clip(synth(lines, settings), label=f"reveal:{i}", gap_before=0.5)
            block = []

    tl.clip(synth([
        ("a", "今天到这。这一轨每天只能跑一次，坚持两周，你会发现你先开口的那半秒不用再等自己了。"),
    ], settings), label="gauntlet-outro", gap_before=0.6)


# ------------------------------------------------------------------ Track 05
def build_sleep_review(settings: dict, tl: Timeline) -> None:
    tl.clip(synth([
        ("a", "最后一轨，睡前用。不用张嘴，不用专注，躺着就行。你今天要做的只是让这二十个语块"
              "在你入睡前的最后一遍经过耳朵。记忆是在睡着以后被巩固的，这一遍会替你完成。"),
    ], settings), label="sleep-intro")
    for i, ch in enumerate(C.CHUNKS, 1):
        tl.clip(synth([
            ("b", ch["chunk"]),
            ("a", ch["zh"]),
            ("b", ch["example_a"]),
        ], settings), label=f"sleep:{ch['id']}", gap_before=0.4)
        tl.echo(6.0 if i % 5 else 9.0)
        if i % 5 == 0:
            tl.echo(6.0)
    tl.clip(synth([
        ("a", "最后，你那十个化石的正确版本，各听一遍就好。"),
        ("b", " ".join(f["core"] for f in C.FOSSILS)),
        ("a", "睡吧。明天早上醒来的时候，先别拿手机，把昨天那句你说不好的话再说一遍。"),
    ], settings), label="sleep-outro", gap_before=1.0)


TRACKS = {
    "01": ("01_xray_repair_lab", build_repair_lab, "体检报告 + 十大化石纠错（强制输出）"),
    "02": ("02_chunk_gym", build_chunk_gym, "二十个语块健身房 + 反向检索"),
    "03": ("03_shadow_stress", build_shadow_stress, "影子跟读与句子重音"),
    "04": ("04_examiner_gauntlet", build_gauntlet, "考官快问快答 + 四步骨架"),
    "05": ("05_sleep_review", build_sleep_review, "睡前间隔复习（不张嘴）"),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", choices=list(TRACKS), help="只构建指定轨道")
    ap.add_argument("--dry-run", action="store_true", help="只打印排期，不调用 TTS")
    args = ap.parse_args()

    wanted = args.only or list(TRACKS)
    if args.dry_run:
        for k in wanted:
            name, _, desc = TRACKS[k]
            print(f"Track {k} → {name}.mp3   {desc}")
        print("\n[dry-run] 未调用任何 TTS 接口。")
        return 0

    settings = load_settings()
    mpath = KIT_DIR / "audio_manifest.json"
    manifest: dict = {"tracks": [], "generated_with": settings.get("model")}
    if mpath.exists():  # 只重建部分轨道时，保留其余轨道的时间轴索引
        manifest = json.loads(mpath.read_text(encoding="utf-8"))
    rebuilt: dict[str, dict] = {}
    for k in wanted:
        name, fn, desc = TRACKS[k]
        print(f"[{k}] 合成中：{desc}", flush=True)
        tl = Timeline()
        fn(settings, tl)
        out = AUDIO_DIR / f"{name}.mp3"
        info = tl.render(out)
        info.update({"track": k, "title_zh": desc})
        rebuilt[k] = info
        print(f"[{k}] ✓ {out.name}  {info['duration']:.0f}s  "
              f"片段 {len(info['markers'])} 个  输出窗口 {len(info['windows'])} 个", flush=True)

    merged = {t["track"]: t for t in manifest.get("tracks", [])}
    merged.update(rebuilt)
    manifest["tracks"] = [merged[k] for k in sorted(merged)]
    manifest["generated_with"] = settings.get("model")
    mpath.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    total = sum(t["duration"] for t in manifest["tracks"])
    print(f"\n完成。全部 {len(manifest['tracks'])} 轨共 {total / 60:.1f} 分钟 | "
          f"本次 API 调用 {STATS['api_calls']} 次 | 命中缓存 {STATS['cache_hits']} 次")
    print(f"目录：{AUDIO_DIR}")
    print(f"清单：{mpath}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
