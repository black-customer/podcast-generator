"""单题导出三张备忘录长图和独立带字幕问答视频；不调用付费 API。"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = Path(__file__).resolve().parent / "output"
sys.path.insert(0, str(ROOT))

from server.alignment import audio_signature, text_fingerprint  # noqa: E402


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def norm(text: str) -> str:
    return " ".join(text.split())


def validate_source(lesson: dict, item: Path, bank: dict) -> dict:
    """校验真实题源、逐句英文和音频版本，防止旧声音配新字幕。"""
    question = next((q for q in bank["questions"] if q["id"] == lesson["question_id"]), None)
    if question is None:
        raise ValueError("题目 ID 不在公开题库中")
    if norm((item / "question.txt").read_text(encoding="utf-8")) != norm(question["text"]):
        raise ValueError("题干与题库记录不一致")
    transcript = (item / "podcast_text.txt").read_text(encoding="utf-8").strip()
    if "[" in transcript or not transcript.startswith("A:"):
        raise ValueError("需要无表演标签的完整 A/B 问答文稿")
    asked = " ".join(re.findall(r"^A:\s*(.+)$", transcript, flags=re.M))
    if norm(asked) != norm(question["text"]):
        raise ValueError("音频提问题干与题库不一致")
    answer = " ".join(re.findall(r"^B:\s*(.+)$", transcript, flags=re.M))
    if not answer or norm(" ".join(s["en"] for s in lesson["sentences"])) != norm(answer):
        raise ValueError("逐句英文必须与音频文稿中的 B 回答一致")
    if not all(s.get("zh", "").strip() for s in lesson["sentences"]):
        raise ValueError("每句英文必须有对应中文")
    chinese_lines = lesson.get("chinese_lines")
    if chinese_lines and re.sub(r"\s+", "", "".join(chinese_lines)) != re.sub(
        r"\s+", "", "".join(s["zh"] for s in lesson["sentences"])
    ):
        raise ValueError("中文回答分行必须完整保留逐句中文，不能增删内容")
    if lesson["answer_origin"] not in {"原创示范", "本人回答", "已有回答"}:
        raise ValueError("必须明确回答来源")
    if not 1 <= len(lesson["chunks"]) <= 3:
        raise ValueError("每期只保留一至三个重点表达")
    for chunk in lesson["chunks"]:
        if chunk["en"].lower() not in answer.lower():
            raise ValueError("重点表达必须出现在本期答案中")
        if not chunk.get("zh") or not chunk.get("example"):
            raise ValueError("重点表达必须有中文及迁移例句")
    meta = read_json(item / "meta.json")
    if meta.get("dry_run") is not False or meta.get("stale") or meta.get("error"):
        raise ValueError("拒绝占位、过期或生成失败的音频")
    if read_json(item / "qa_podcast.json").get("verdict") != "pass":
        raise ValueError("源音频尚未通过 QA")
    alignment = read_json(item / "alignment_podcast.json")
    audio = item / "audio_podcast.mp3"
    if alignment.get("audio_signature") != audio_signature(audio):
        raise ValueError("音频签名已变化，需要重新对齐")
    sources = [transcript]
    for name in ("podcast_script.txt", "fish_script.txt"):
        path = item / name
        if path.exists():
            script = path.read_text(encoding="utf-8").strip()
            if norm(re.sub(r"\[[^\]]*\]", "", script)) == norm(transcript):
                sources.append(script)
    if alignment.get("text_fingerprint") not in {text_fingerprint(s) for s in sources}:
        raise ValueError("对齐文本已过期，需要重新生成")
    if alignment.get("mode") not in {"sse", "measured"}:
        raise ValueError("需要真实测量的问答音频")
    topic = next(t for t in bank["topics"] if t["id"] == question["topic_id"])
    seasons = [
        f"{s['year']}年{s['start_month']}–{s['end_month']}月"
        for s in bank.get("sets", []) if question["id"] in s["question_ids"]
    ]
    return {
        "question": question["text"], "question_zh": question.get("text_zh", ""),
        "answer": answer, "part": question["part"], "topic_zh": topic.get("name_zh", ""),
        "topic": topic["name_en"], "season": " / ".join(seasons) or "考季未核实",
        "question_id": question["id"], "alignment": alignment,
    }


def esc(text: str) -> str:
    return html.escape(str(text), quote=True)


IMAGE_SIZE = (1260, 2800)
VIDEO_SIZE = (1080, 1920)
MATERIAL_FILES = ("01-chinese.png", "02-dialogue.mp4", "03-bilingual.png", "04-notes.png")

STYLE = """
*{box-sizing:border-box}html,body{margin:0;background:#FDFBF7;color:#25221E}
body{font-family:'Microsoft YaHei',sans-serif}
.sheet{width:1260px;height:2800px;padding:100px 94px 76px;display:flex;
flex-direction:column;overflow:hidden}
.season{font:46px/1.4 Georgia,'Microsoft YaHei',serif;margin:0 0 62px;color:#66615A}
.topic{font:70px/1.35 Georgia,serif;font-weight:700;margin:0}
.topic span{font:56px/1.4 'Microsoft YaHei',sans-serif;font-weight:500;margin-left:30px}
.sheet>header{padding-bottom:44px;border-bottom:2px solid #DAD4CB}
.question{margin:42px 0 34px}.role{font-size:43px;font-weight:700;margin:0 0 20px}
.q-en{font:56px/1.4 Georgia,serif;font-weight:700;margin:0 0 20px}
.q-zh{font-size:51px;line-height:1.6;margin:0}
.sheet>main{flex:1;min-height:0}.sheet>footer{font-size:29px;line-height:1.6;
margin-top:44px;color:#6C665F}
.chinese>main{display:flex;flex-direction:column}
.chinese-answer{display:flex;flex:1;flex-direction:column;justify-content:space-between}
.answer-line{font-size:76px;line-height:1.5;white-space:nowrap;margin:0}
.bilingual .q-en{font-size:49px}.bilingual .q-zh{font-size:46px}
.bilingual>main{display:flex;flex-direction:column;justify-content:space-between;gap:30px}
.pair{padding:0 0 18px}.pair-en{font:54px/1.38 Georgia,serif;margin:0 0 18px}
.pair-zh{font-size:51px;line-height:1.58;margin:0;color:#5B554D}
.notes>main{display:flex;flex-direction:column;justify-content:space-between;gap:38px}
.notes-label{font:60px/1.4 'KaiTi','Microsoft YaHei',serif;margin:40px 0 38px}
.note{padding-bottom:32px;border-bottom:2px solid #E6E0D8}
.note:last-child{border-bottom:0;padding-bottom:0}
.phrase{font:60px/1.4 Georgia,serif;font-weight:700;margin:0 0 26px}
mark{color:inherit;background:linear-gradient(transparent 70%,#F0D1D2 70%);padding:0}
.meaning{font:70px/1.45 'KaiTi','Microsoft YaHei',serif;color:#863B38;margin:0 0 24px}
.usage{font-size:45px;line-height:1.6;margin:0 0 30px}
.example-en{font:51px/1.5 Georgia,serif;margin:0 0 18px}
.example-zh{font-size:48px;line-height:1.55;color:#5B554D;margin:0}
.recording{width:1080px;height:1920px;padding:92px 78px 74px}
.recording .season{font-size:34px;margin-bottom:38px}
.recording .topic{font-size:53px}.recording .topic span{font-size:45px;margin-left:24px}
.recording .caption{display:flex;flex-direction:column;justify-content:center}
.recording .role{color:#863B38;font-size:38px;margin:0 0 38px}
.cue-en{font:54px/1.5 Georgia,serif;margin:0 0 42px}
.cue-zh{font-size:65px;line-height:1.6;margin:0}
.recording>footer{font-size:25px;margin-top:24px}
"""


def memo_header(lesson: dict, source: dict) -> str:
    topic_zh = lesson.get("topic_label_zh") or source["topic_zh"]
    return (
        '<header>'
        f'<p class="season">{esc(source["season"])} · Part {source["part"]}</p>'
        f'<h1 class="topic">{esc(source["topic"])}<span>{esc(topic_zh)}</span></h1>'
        '</header>'
    )


def material_html(lesson: dict, source: dict, kind: str, cue: dict | None = None) -> str:
    header = memo_header(lesson, source)
    question = (
        '<section class="question"><h2 class="role">考官：</h2>'
        f'<p class="q-en">{esc(source["question"])}</p>'
        f'<p class="q-zh">{esc(source["question_zh"])}</p></section>'
    )
    if kind == "chinese":
        lines = lesson.get("chinese_lines") or [s["zh"] for s in lesson["sentences"]]
        body = question + '<main><h2 class="role">考生：</h2><div class="chinese-answer">'
        body += "".join(f'<p class="answer-line">{esc(line)}</p>' for line in lines)
        body += "</div></main>"
    elif kind == "bilingual":
        pairs = "".join(
            '<section class="pair">'
            f'<p class="pair-en">{esc(s["en"])}</p>'
            f'<p class="pair-zh">{esc(s["zh"])}</p></section>'
            for s in lesson["sentences"]
        )
        body = question + f"<main>{pairs}</main>"
    elif kind == "notes":
        notes = "".join(
            '<section class="note">'
            f'<h2 class="phrase"><mark>{esc(c.get("display_en") or c["en"])}</mark></h2>'
            f'<p class="meaning">{esc(c["zh"])}</p>'
            + (f'<p class="usage">{esc(c["usage"])}</p>' if c.get("usage") else "")
            + f'<p class="example-en">{esc(c["example"])}</p>'
            + (f'<p class="example-zh">{esc(c["example_zh"])}</p>'
               if c.get("example_zh") else "")
            + "</section>" for c in lesson["chunks"]
        )
        body = f'<h2 class="notes-label">重点语块</h2><main>{notes}</main>'
    elif kind == "recording" and cue:
        role = "考官" if cue["speaker"] == "a" else "考生"
        body = (
            f'<main class="caption"><p class="role">{role}</p>'
            f'<p class="cue-en">{esc(cue["en"])}</p>'
            f'<p class="cue-zh">{esc(cue["zh"])}</p></main>'
        )
    else:
        raise ValueError("未知材料类型或缺少字幕")
    footer = f'{esc(lesson["answer_origin"])} · 本地题库整理标签'
    return (
        '<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
        f'<title>{esc(source["topic"])}</title><style>{STYLE}</style><body>'
        f'<article class="sheet {kind}">{header}{body}<footer>{footer}</footer>'
        '</article></body></html>'
    )


def spoken_text(text: str) -> str:
    return norm(re.sub(r"\[[^\]]*\]", "", text))


def tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+(?:'[a-z]+)?", text.lower().replace("’", "'"))


def caption_cues(lesson: dict, source: dict, speed: float) -> list[dict]:
    """字幕使用实测单句跨度或真实词时间戳；没有就拒绝按字数猜时间。"""
    texts = [
        {"speaker": "a", "en": source["question"], "zh": source["question_zh"]},
        *[{"speaker": "b", **s} for s in lesson["sentences"]],
    ]
    segments = source["alignment"].get("segments", [])
    word_entries = [
        {"token": token, "start": word["start"], "end": word["end"]}
        for word in source["alignment"].get("words", [])
        for token in tokens(word["text"])
    ]
    segment_cursor, word_cursor = 0, 0
    cues = []
    for text in texts:
        span = None
        for i in range(segment_cursor, len(segments)):
            candidate = segments[i]
            if (candidate.get("speaker", "").lower() == text["speaker"]
                    and spoken_text(candidate["text"]) == norm(text["en"])):
                span = candidate
                segment_cursor = i + 1
                break
        expected = tokens(text["en"])
        if span is None and word_entries:
            actual = [w["token"] for w in word_entries]
            for i in range(word_cursor, len(actual) - len(expected) + 1):
                if actual[i:i + len(expected)] == expected:
                    span = {"start": word_entries[i]["start"],
                            "end": word_entries[i + len(expected) - 1]["end"]}
                    word_cursor = i + len(expected)
                    break
        if span is None:
            raise ValueError("缺少逐句真实时间轴；请准备逐句音频对齐，不能估算字幕")
        cue = {**text, "start": float(span["start"]) / speed, "end": float(span["end"]) / speed}
        if cue["end"] <= cue["start"] or (cues and cue["start"] < cues[-1]["start"]):
            raise ValueError("字幕时间顺序异常")
        cues.append(cue)
    return cues


def srt_time(seconds: float) -> str:
    ms = round(seconds * 1000)
    hours, ms = divmod(ms, 3600000)
    minutes, ms = divmod(ms, 60000)
    secs, ms = divmod(ms, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{ms:03}"


def run(command: list[str]) -> str:
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(result.stderr[-2000:])
    return result.stdout or result.stderr


def probe(path: Path) -> dict:
    return json.loads(run([
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration:stream=codec_name,width,height,sample_rate", "-of", "json", str(path),
    ]))


def publish_text(lesson: dict, source: dict) -> str:
    origins = {
        "本人回答": "本期根据本人真实回答整理。",
        "原创示范": "本期是原创示范，示例经历并非本人经历。",
        "已有回答": "本期根据已有回答整理，观众请换成自己的经历练习。",
    }
    return (
        f'{source["question"]}\n{source["question_zh"]}\n\n'
        f'Part {source["part"]} · {source["topic"]} · {source["season"]}\n'
        f'{origins[lesson["answer_origin"]]}\n'
        "题源为本地整理记录，考季未作当季独立核验；语音为 AI 合成。\n\n"
        "四份材料：中文回答长图、带中英字幕的问答录音视频、逐句中英对照长图、语块笔记。\n"
        "图文和录音视频分别发布，不合并为四步练习视频。\n"
        "#雅思口语 #英语口语 #英语笔记\n"
    )


def render_shot(page, doc: str, path: Path, size: tuple[int, int]) -> dict:
    page.set_viewport_size({"width": size[0], "height": size[1]})
    page.set_content(doc)
    page.evaluate("document.fonts.ready")
    page.evaluate("window.scrollTo(0, 0)")
    metrics = page.evaluate("""() => {
        const sheet = document.querySelector('.sheet');
        const footer = sheet.querySelector('footer').getBoundingClientRect();
        const main = sheet.querySelector('main').getBoundingClientRect();
        const nodes = [...sheet.querySelectorAll('main *, .question *, header *')];
        const outside = nodes.some(el => {
            const r = el.getBoundingClientRect();
            return r.left < 0 || r.right > innerWidth ||
                el.scrollWidth > el.clientWidth + 3 ||
                (el.closest('main') && r.bottom > footer.top - 12);
        });
        return {width: innerWidth, height: innerHeight, outside,
                mainBottom: main.bottom, footerTop: footer.top};
    }""")
    if metrics["outside"] or metrics["mainBottom"] > metrics["footerTop"] - 12:
        raise ValueError(f"材料正文溢出或碰到页脚：{path.name} {metrics}")
    page.screenshot(path=str(path))
    return metrics


def preview_html(lesson: dict) -> str:
    return (
        '<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>四份口语材料</title><style>'
        'body{margin:40px auto;padding:0 20px;max-width:740px;background:#FDFBF7;'
        'color:#25221E;font-family:Microsoft YaHei,sans-serif}'
        'h1{font-size:28px;font-weight:600}h2{font-size:20px;margin:0 0 20px}'
        'section{margin:54px 0 68px}img,video{display:block;width:100%;height:auto}'
        'video{max-height:760px;margin:auto;object-fit:contain}'
        'a{color:#863B38;text-underline-offset:4px}a:focus-visible{outline:2px solid #863B38}'
        '::selection{background:#F0D1D2}p{font-size:15px;line-height:1.7}</style>'
        f'<h1>{esc(lesson["headline"])}</h1>'
        '<p><a href="01-chinese.png" download>中文长图</a> · '
        '<a href="02-dialogue.mp4" download>问答录音视频</a> · '
        '<a href="03-bilingual.png" download>中英对照</a> · '
        '<a href="04-notes.png" download>语块笔记</a></p>'
        '<section><h2>中文回答</h2><img src="01-chinese.png" alt="只含中文回答的备忘录"></section>'
        '<section><h2>问答录音</h2><video controls playsinline preload="metadata" '
        'poster="assets/recording-cover.png" src="02-dialogue.mp4"></video></section>'
        '<section><h2>逐句中英对照</h2><img src="03-bilingual.png" alt="每句中英文相邻"></section>'
        '<section><h2>语块笔记</h2><img src="04-notes.png" alt="重点语块、用法和例句"></section>'
        '</html>'
    )


def build(lesson_path: Path, item: Path, output: Path, speed: float = 1.0) -> Path:
    from playwright.sync_api import sync_playwright

    output = output.resolve()
    if (OUTPUT_ROOT.resolve() not in output.parents or output.exists()
            or output.with_suffix(".zip").exists()):
        raise ValueError("输出必须是 daily-ielts/output 内尚不存在的新目录和 ZIP")
    if not 0.7 <= speed <= 1.1:
        raise ValueError("速度必须在 0.7–1.1 之间")
    lesson = read_json(lesson_path)
    source = validate_source(lesson, item, read_json(ROOT / "data/question_bank_public.json"))
    if not source["question_zh"]:
        raise ValueError("题库缺少中文题目，先准备经核对的翻译")
    cues = caption_cues(lesson, source, speed)
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".build-", dir=OUTPUT_ROOT) as staging:
        dest = Path(staging)
        assets = dest / "assets"
        assets.mkdir()
        run([
            "ffmpeg", "-v", "error", "-i", str(item / "audio_podcast.mp3"),
            "-af", f"atempo={speed},loudnorm=I=-16:TP=-1.5:LRA=11",
            "-ar", "44100", "-ac", "1", "-b:a", "128k", str(assets / "answer.mp3"),
        ])
        audio_info = probe(assets / "answer.mp3")
        duration = float(audio_info["format"]["duration"])
        volume = run(["ffmpeg", "-hide_banner", "-i", str(assets / "answer.mp3"),
                      "-af", "volumedetect", "-f", "null", "-"])
        match = re.search(r"mean_volume: (-?[\d.]+) dB", volume)
        if not match or float(match[1]) < -45:
            raise ValueError("录音近似静音，不能交付")
        if cues[-1]["end"] > duration + 0.15:
            raise ValueError("字幕超出录音时长")
        measurements = {}
        frames = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page()
            for kind, name in (("chinese", MATERIAL_FILES[0]),
                               ("bilingual", MATERIAL_FILES[2]), ("notes", MATERIAL_FILES[3])):
                doc = material_html(lesson, source, kind)
                (assets / f"{kind}.html").write_text(doc, encoding="utf-8")
                measurements[kind] = render_shot(page, doc, dest / name, IMAGE_SIZE)
            for i, cue in enumerate(cues):
                doc = material_html(lesson, source, "recording", cue)
                frame = assets / f"caption-{i:02}.png"
                measurements[f"caption-{i}"] = render_shot(page, doc, frame, VIDEO_SIZE)
                frames.append(frame)
                if i == 0:
                    (assets / "recording-cover.png").write_bytes(frame.read_bytes())
            browser.close()
        lines = ["ffconcat version 1.0"]
        for i, frame in enumerate(frames):
            quoted = frame.as_posix().replace("'", "'\\''")
            start = 0 if i == 0 else cues[i]["start"]
            end = cues[i + 1]["start"] if i + 1 < len(cues) else duration
            lines += [f"file '{quoted}'", f"duration {end - start:.6f}"]
        lines.append(lines[-2])
        visual_list = assets / "frames.ffconcat"
        visual_list.write_text("\n".join(lines) + "\n", encoding="utf-8")
        video = dest / MATERIAL_FILES[1]
        run([
            "ffmpeg", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(visual_list),
            "-i", str(assets / "answer.mp3"), "-t", str(duration), "-r", "24",
            "-threads", "2", "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
            str(video),
        ])
        video_info = probe(video)
        video_stream = next(s for s in video_info["streams"] if "width" in s)
        if (video_stream["width"], video_stream["height"]) != VIDEO_SIZE:
            raise ValueError("录音视频尺寸异常")
        if abs(float(video_info["format"]["duration"]) - duration) > 0.15:
            raise ValueError("录音视频必须只播放原问答一次")
        subtitles = "\n\n".join(
            f'{i + 1}\n{srt_time(c["start"])} --> {srt_time(c["end"])}\n{c["en"]}\n{c["zh"]}'
            for i, c in enumerate(cues)
        )
        (assets / "subtitles.srt").write_text(subtitles + "\n", encoding="utf-8")
        (dest / "index.html").write_text(preview_html(lesson), encoding="utf-8")
        (dest / "publish.txt").write_text(publish_text(lesson, source), encoding="utf-8")
        provenance = {k: v for k, v in source.items() if k != "alignment"}
        provenance["verification_scope"] = "本地题库匹配；非当季官方真题认证"
        (dest / "source.json").write_text(
            json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (dest / "lesson.json").write_text(
            json.dumps(lesson, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        verification = {
            "ready": True, "material_contract": "four-materials-v2",
            "materials": list(MATERIAL_FILES), "image_size": list(IMAGE_SIZE),
            "cards": measurements, "audio": audio_info, "video": video_info,
            "source_audio_sha256": hashlib.sha256(
                (item / "audio_podcast.mp3").read_bytes()
            ).hexdigest(),
            "speed": speed, "mean_volume_db": float(match[1]), "caption_cues": cues,
            "dialogue_turns": ["a", "b"],
            "listening_gate": "QA、实测字幕与非静音检查通过；自然度由 Bruce 抽听",
        }
        (dest / "verification.json").write_text(
            json.dumps(verification, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        visual_list.unlink()
        output.parent.mkdir(parents=True, exist_ok=True)
        dest.rename(output)
    with zipfile.ZipFile(output.with_suffix(".zip"), "w", compression=zipfile.ZIP_STORED) as bundle:
        for name in MATERIAL_FILES:
            bundle.write(output / name, name)
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lesson", type=Path, required=True)
    parser.add_argument("--item-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--speed", type=float, default=1.0)
    args = parser.parse_args()
    print(build(args.lesson, args.item_dir, args.out, args.speed))
