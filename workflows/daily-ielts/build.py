"""把已完成的单题问答导出为四张练习卡、音频和竖屏视频；不调用付费 API。"""
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
        "question": question["text"], "answer": answer, "part": question["part"],
        "topic": topic["name_en"], "season": " / ".join(seasons) or "考季未核实",
        "question_id": question["id"], "alignment": alignment,
    }


def esc(text: str) -> str:
    return html.escape(str(text), quote=True)


STYLE = """
*{box-sizing:border-box}body{margin:0;background:#E6EFF4;color:#142F46;
font-family:'Microsoft YaHei','Segoe UI',sans-serif}
.card{width:1080px;height:1440px;padding:68px 88px 170px;position:relative;overflow:hidden}
.mast{display:flex;justify-content:space-between;align-items:center;font-size:28px;
padding-bottom:30px;border-bottom:2px solid #A9BCC9;letter-spacing:1px}
.steps{display:flex;gap:12px}
.steps span{width:13px;height:13px;border-radius:50%;background:#A9BCC9}
.steps .on{background:#195DC6}
.eyebrow{margin:42px 0 18px;font-size:29px;color:#195DC6;font-weight:700}
h1{font-size:76px;line-height:1.28;letter-spacing:-2px;margin:0 0 32px;font-weight:900}
.topic{font-size:27px;margin:22px 0 16px;color:#405E72}
.question{font-family:Georgia,serif;font-size:37px;line-height:1.35;margin:0 0 34px}
.zh{font-size:46px;line-height:1.6;margin:0 0 8px}
.prompt{background:#D8F074;display:inline-block;padding:12px 23px;font-size:29px;
font-weight:700;margin:24px 0 0;border-radius:8px}
.audio-panel{background:#195DC6;color:#FFFFFF;border-radius:24px;padding:48px;margin:48px 0}
.audio-panel h2{font-size:43px;margin:0 0 28px}
.audio-panel p{font-size:31px;line-height:1.6;margin:0}
.wave{display:flex;height:150px;align-items:center;gap:13px;margin:22px 0 28px}
.wave i{display:block;width:11px;background:#D8F074;border-radius:9px}
.english{font-family:Georgia,serif;font-size:47px;line-height:1.44;margin:0 0 25px}
mark{background:#D8F074;color:inherit;box-decoration-break:clone;padding:0 3px}
.notes h1{font-size:60px;margin-bottom:24px}
.note{padding:18px 0;border-top:2px solid #A9BCC9}.phrase{font-family:Georgia,serif;
font-size:43px;line-height:1.3;margin:0 0 6px}.meaning{font-size:30px;margin:0 0 12px}
.example{font-family:Georgia,serif;font-size:29px;line-height:1.4;margin:0;color:#405E72}
.transfer{margin-top:32px;background:#D8F074;padding:23px 28px;border-radius:12px;
font-size:30px;line-height:1.55}.transfer strong{display:block;font-size:32px}
.footer{position:absolute;bottom:60px;left:88px;right:88px;font-size:23px;line-height:1.65;
color:#405E72;border-top:2px solid #A9BCC9;padding-top:17px}
.footer b{color:#142F46;font-size:27px}.reading h1{font-size:64px;margin-bottom:35px}
"""


def card_html(lesson: dict, source: dict, stage: int) -> str:
    titles = ["先开口", "再听音", "看英文", "学会用"]
    topic = f"IELTS Speaking · Part {source['part']} · {source['topic']}"
    question = f'<p class="question">{esc(source["question"])}</p>'
    if stage == 0:
        paragraphs = "".join(f'<p class="zh">{esc(s["zh"])}</p>' for s in lesson["sentences"])
        body = (
            f'<h1>{esc(lesson["headline"]).replace(chr(10), "<br>")}</h1>'
            f'<p class="topic">{esc(topic)}</p>{question}'
            f'{paragraphs}<p class="prompt">暂停一下，把这段话说成英语。</p>'
        )
    elif stage == 1:
        heights = [32, 56, 90, 120, 65, 140, 105, 46, 82, 124, 60, 36, 100, 146,
                   88, 40, 116, 68, 32, 86, 130, 48, 102, 66, 34, 80]
        wave = "".join(f'<i style="height:{h}px"></i>' for h in heights)
        body = (
            '<h1>先听一遍。<br>暂时不看答案。</h1>'
            f'<p class="topic">{esc(topic)}</p>{question}'
            '<div class="audio-panel"><h2>听声音，抓住意思。</h2>'
            f'<div class="wave" aria-hidden="true">{wave}</div>'
            '<p>这一次只有声音。<br>听完后，试着复述你听到的回答。</p></div>'
            '<p class="prompt">下一页揭示英文。</p>'
        )
    elif stage == 2:
        paragraphs = []
        for sentence in lesson["sentences"]:
            text = esc(sentence["en"])
            for chunk in lesson["chunks"]:
                text = text.replace(esc(chunk["en"]), f'<mark>{esc(chunk["en"])}</mark>')
            paragraphs.append(f'<p class="english">{text}</p>')
        body = (
            '<h1>再听一遍，<br>对照你的表达。</h1>'
            f'<p class="topic">{esc(topic)}</p>' + "".join(paragraphs)
            + '<p class="prompt">留意停顿和语气，再跟着说一遍。</p>'
        )
    else:
        notes = "".join(
            f'<div class="note"><p class="phrase">{esc(c["en"])}</p>'
            f'<p class="meaning">{esc(c["zh"])}</p>'
            f'<p class="example">{esc(c["example"])}</p></div>'
            for c in lesson["chunks"]
        )
        body = (
            f'<h1>带走这 {len(lesson["chunks"])} 个表达，<br>换个场景说。</h1>{notes}'
            '<div class="transfer"><strong>轮到你了 · 暂停开口</strong>'
            f'{esc(lesson["transfer_zh"])}</div>'
        )
    dots = "".join(f'<span class="{"on" if i == stage else ""}"></span>' for i in range(4))
    footer = (
        f'<b>英语说说说 · 每天练一道题</b><br>'
        f'本地题库标签：{esc(source["season"])} · {esc(lesson["answer_origin"])}<br>'
        '考季未作当季独立核验；示范供练习，回答请换成自己的经历。'
    )
    return (
        f'<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>{titles[stage]}</title>'
        f'<style>{STYLE}</style><body><article class="card '
        f'{"reading" if stage == 2 else "notes" if stage == 3 else ""}">'
        f'<header class="mast"><b>英语说说说</b><div class="steps">{dots}</div></header>'
        f'<p class="eyebrow">0{stage + 1} / 04 · {titles[stage]}</p>'
        f'<main>{body}</main><footer class="footer">{footer}</footer></article></body></html>'
    )


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
        f"标题：{lesson['headline'].replace(chr(10), '')}｜每天练一道雅思口语\n\n"
        "先看中文开口，再盲听，最后对照英文。\n"
        "不要只收藏：挑一个表达，换成你自己的经历说一遍。\n\n"
        f"本期题目：{source['question']}\n"
        f"话题：{source['topic']}｜Part {source['part']}\n"
        f"题库标签：{source['season']}（本地记录，未作当季独立核验）\n"
        f"回答来源：{lesson['answer_origin']}。{origins[lesson['answer_origin']]}\n"
        "语音为 AI 合成，示范供练习，不作分数保证。\n\n"
        "#雅思口语 #英语口语 #英语听力 #每天练英语\n\n"
        f"置顶评论建议：{lesson['transfer_zh']}\n\n"
        "发布：上传 publish.mp4，封面选 01.png；检查平台 AI 标识选项。\n"
        "图文备选：按 01–04.png 顺序上传，并自行确认平台能否完整保留示范音频。\n"
        "本地未上传或发布到任何平台。\n"
    )


def build(lesson_path: Path, item: Path, output: Path, speed: float = 0.82) -> Path:
    from playwright.sync_api import sync_playwright

    output = output.resolve()
    if OUTPUT_ROOT.resolve() not in output.parents or output.exists():
        raise ValueError("输出必须是 daily-ielts/output 内尚不存在的新目录")
    if not 0.7 <= speed <= 1.1:
        raise ValueError("速度必须在 0.7–1.1 之间")
    lesson = read_json(lesson_path)
    source = validate_source(lesson, item, read_json(ROOT / "data/question_bank_public.json"))
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".build-", dir=OUTPUT_ROOT) as staging:
        dest = Path(staging)
        measurements = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": 1080, "height": 1440}, device_scale_factor=1)
            for stage in range(4):
                doc = card_html(lesson, source, stage)
                if stage == 1 and esc(source["answer"]) in doc:
                    raise ValueError("盲听卡泄露了完整答案")
                page.set_content(doc)
                page.evaluate("document.fonts.ready")
                metrics = page.evaluate("""() => {
                    const main = document.querySelector('main').getBoundingClientRect();
                    const footer = document.querySelector('footer').getBoundingClientRect();
                    const outside = [...document.querySelectorAll('main *')].some(el => {
                        const r = el.getBoundingClientRect();
                        return r.left < 88 || r.right > 992 || el.scrollWidth > el.clientWidth + 2;
                    });
                    return {mainBottom: main.bottom, footerTop: footer.top, outside};
                }""")
                if metrics["mainBottom"] > metrics["footerTop"] - 18 or metrics["outside"]:
                    raise ValueError(f"第 {stage + 1} 张卡片发生内容溢出：{metrics}")
                measurements.append(metrics)
                (dest / f"0{stage + 1}.html").write_text(doc, encoding="utf-8")
                page.screenshot(path=str(dest / f"0{stage + 1}.png"))
            browser.close()
        audio = dest / "answer.mp3"
        run([
            "ffmpeg", "-v", "error", "-i", str(item / "audio_podcast.mp3"),
            "-af", f"atempo={speed},loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", "44100",
            "-ac", "1", "-b:a", "128k", str(audio),
        ])
        audio_info = probe(audio)
        duration = float(audio_info["format"]["duration"])
        volume = run(["ffmpeg", "-hide_banner", "-i", str(audio),
                      "-af", "volumedetect", "-f", "null", "-"])
        mean_match = re.search(r"mean_volume: (-?[\d.]+) dB", volume)
        if not mean_match or float(mean_match[1]) < -45:
            raise ValueError("导出音频近似静音，不能交付")
        stages = [12.0, duration + 1.0, duration + 1.0, 12.0]
        total = sum(stages)
        question_end = max(
            (s["end"] for s in source["alignment"].get("segments", [])
             if s.get("speaker", "").lower() == "a"), default=0,
        ) / speed
        if question_end <= 0:
            raise ValueError("缺少提问者真实时间轴，不能截取提问音频")
        run([
            "ffmpeg", "-v", "error", "-i", str(audio), "-af",
            f"atrim=end={question_end},apad", "-t", str(stages[0]),
            "-ar", "44100", "-ac", "1", str(dest / "prompt.wav"),
        ])
        run([
            "ffmpeg", "-v", "error", "-i", str(audio), "-af", "apad",
            "-t", str(stages[1]), "-ar", "44100", "-ac", "1", str(dest / "listen.wav"),
        ])
        run([
            "ffmpeg", "-v", "error", "-f", "lavfi", "-i",
            "anullsrc=r=44100:cl=mono", "-t", str(stages[3]), str(dest / "practice.wav"),
        ])

        def concat_file(paths: list[Path], name: str, durations: list[float] | None = None):
            lines = ["ffconcat version 1.0"]
            for i, path in enumerate(paths):
                quoted = path.as_posix().replace("'", "'\\''")
                lines.append(f"file '{quoted}'")
                if durations is not None:
                    lines.append(f"duration {durations[i]:.6f}")
            if durations is not None:
                lines.append(lines[-2])
            result = dest / name
            result.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return result

        audio_list = concat_file(
            [dest / name for name in ("prompt.wav", "listen.wav", "listen.wav", "practice.wav")],
            "audio.ffconcat",
        )
        run([
            "ffmpeg", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(audio_list),
            "-ar", "44100", "-ac", "1", str(dest / "soundtrack.wav"),
        ])
        visual_list = concat_file([dest / f"0{i}.png" for i in range(1, 5)],
                                  "cards.ffconcat", stages)
        video = dest / "publish.mp4"
        run([
            "ffmpeg", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(visual_list),
            "-i", str(dest / "soundtrack.wav"), "-vf",
            "pad=1080:1920:0:160:color=0xE6EFF4,setsar=1", "-map", "0:v", "-map", "1:a",
            "-t", str(total), "-r", "24", "-threads", "2", "-c:v", "libx264",
            "-preset", "veryfast", "-crf", "23",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
            str(video),
        ])
        video_info = probe(video)
        video_stream = next(s for s in video_info["streams"] if "width" in s)
        if (video_stream["width"], video_stream["height"]) != (1080, 1920):
            raise ValueError("视频不是要求的 1080×1920")
        if abs(float(video_info["format"]["duration"]) - total) > 0.25:
            raise ValueError("视频时长与四步计划不一致")
        for path in dest.iterdir():
            if path.suffix in {".wav", ".ffconcat"}:
                path.unlink()
        (dest / "publish.txt").write_text(publish_text(lesson, source), encoding="utf-8")
        (dest / "lesson.json").write_text(json.dumps(lesson, ensure_ascii=False, indent=2),
                                       encoding="utf-8")
        provenance = {k: v for k, v in source.items() if k != "alignment"}
        provenance["bank_file"] = "data/question_bank_public.json"
        provenance["verification_scope"] = "本地题干、话题与考季标签匹配；非当季官方真题认证"
        (dest / "source.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2),
                                       encoding="utf-8")
        (dest / "verification.json").write_text(json.dumps({
            "ready": True, "cards": measurements, "audio": audio_info, "video": video_info,
            "source_audio_sha256": hashlib.sha256(
                (item / "audio_podcast.mp3").read_bytes()
            ).hexdigest(),
            "stage_seconds": stages, "speed": speed, "mean_volume_db": float(mean_match[1]),
            "listening_gate": "源QA通过且非静音；自然度、切换节奏与手机显示仍需人工试听预览",
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        gallery = "".join(
            f'<a href="0{i}.png"><img src="0{i}.png" alt="练习第 {i} 步"></a>'
            for i in range(1, 5)
        )
        index = (
            '<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>每日雅思口语 · 本期</title><style>'
            'body{background:#E6EFF4;color:#142F46;font-family:Microsoft YaHei,sans-serif;'
            'max-width:1500px;margin:30px auto;padding:20px}a{color:#195DC6}'
            '.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:18px}'
            '.grid img{width:100%;border-radius:12px}video{max-height:660px;max-width:100%}'
            'a:focus-visible{outline:3px solid #195DC6}audio{max-width:100%}</style>'
            f'<h1>{esc(lesson["headline"]).replace(chr(10), "")}</h1>'
            '<p>四步练习：先说 → 盲听 → 揭示 → 迁移</p>'
            '<p><a href="publish.mp4" download>下载视频</a> · '
            '<a href="answer.mp3" download>下载问答音频</a> · '
            '<a href="publish.txt">发布文案</a></p>'
            '<audio controls src="answer.mp3"></audio>'
            f'<div class="grid">{gallery}</div>'
            '<h2>发布视频预览</h2><video controls preload="metadata" src="publish.mp4"></video>'
            '<p>题库考季标签尚未作当季独立核验；语音为 AI 合成。</p></html>'
        )
        (dest / "index.html").write_text(index, encoding="utf-8")
        output.parent.mkdir(parents=True, exist_ok=True)
        dest.rename(output)
    zip_path = output.with_suffix(".zip")
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_STORED) as bundle:
        for path in output.iterdir():
            if path.suffix != ".html" or path.name == "index.html":
                bundle.write(path, path.name)
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lesson", type=Path, required=True)
    parser.add_argument("--item-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--speed", type=float, default=0.82)
    args = parser.parse_args()
    print(build(args.lesson, args.item_dir, args.out, args.speed))
