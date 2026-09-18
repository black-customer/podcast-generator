"""M02 对齐真相层测试：段级精确时间轴 + 指纹失效 + 派生兼容。"""
import sys
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from server import alignment

# ---------------------------------------------------------------- 段级跨度

def test_spans_from_measured_segments():
    """逐段实测时长 + 段间 gap → 累积跨度精确。"""
    spans = alignment.spans_from_measured_segments(
        seg_durations=[2.0, 3.0, 1.5],
        gaps=[0.0, 0.35, 0.35],
    )
    assert spans == [
        {"start": 0.0, "end": 2.0},
        {"start": 2.35, "end": 5.35},
        {"start": 5.7, "end": 7.2},
    ]


def test_spans_rounding():
    spans = alignment.spans_from_measured_segments([1.234, 2.345], [0.0, 0.1])
    assert all(abs(s["end"] - round(s["end"], 2)) < 1e-9 for s in spans)


def test_spans_empty():
    assert alignment.spans_from_measured_segments([], []) == []


def test_rescale_spans_to_final_duration():
    """mp3 拼接的帧填充误差近似线性累积：按总时长线性重标定。"""
    spans = [
        {"start": 0.0, "end": 2.0, "text": "a"},
        {"start": 2.35, "end": 5.35, "text": "b"},
    ]
    rescaled = alignment.rescale_spans(spans, total=10.7)
    assert rescaled[-1]["end"] == pytest.approx(10.7, abs=0.01)
    assert rescaled[0]["start"] == 0.0
    # 比例保持
    assert rescaled[0]["end"] == pytest.approx(4.0, abs=0.01)


def test_rescale_spans_noop_when_matching():
    spans = [{"start": 0.0, "end": 5.0}]
    assert alignment.rescale_spans(spans, total=5.0) == spans


# ---------------------------------------------------------------- 块内句子分配

def test_distribute_sentences_within_segment():
    """段内多句：按字符权重分配段时长，不跨段累积误差。"""
    sents = ["Hello there.", "How are you today?", "Fine!"]
    spans = alignment.distribute_sentences_within_segment(sents, 0.0, 6.0)
    assert len(spans) == 3
    assert spans[0]["start"] == 0.0
    assert spans[-1]["end"] == 6.0
    # 单调且无缝
    for a, b in zip(spans, spans[1:], strict=False):
        assert b["start"] == a["end"]
    # 长句占比更大
    assert spans[1]["duration"] > spans[0]["duration"]


def test_distribute_single_sentence():
    spans = alignment.distribute_sentences_within_segment(["One."], 1.0, 2.5)
    assert spans[0]["start"] == 1.0 and spans[0]["end"] == 2.5


# ---------------------------------------------------------------- 对话行聚合

def test_aggregate_dialogue_lines():
    """多段属于同一对话行时，行跨度 = 首段起点 → 末段终点。"""
    line_map = [0, 0, 1, 1, 2]  # 5 段 → 3 行
    spans = [
        {"start": 0.0, "end": 2.0},
        {"start": 2.35, "end": 5.35},
        {"start": 5.7, "end": 6.7},
        {"start": 7.05, "end": 9.05},
        {"start": 9.4, "end": 10.0},
    ]
    lines = alignment.aggregate_dialogue_lines(line_map, spans)
    assert len(lines) == 3
    assert lines[0] == {"start": 0.0, "end": 5.35}
    assert lines[1] == {"start": 5.7, "end": 9.05}
    assert lines[2] == {"start": 9.4, "end": 10.0}


# ---------------------------------------------------------------- 指纹与失效

def test_fingerprint_stability_and_difference():
    a = alignment.text_fingerprint("Hello.\nWorld.")
    b = alignment.text_fingerprint("Hello. World.")
    same = alignment.text_fingerprint("Hello.\nWorld.")
    assert a == same
    assert a != b


def test_alignment_file_roundtrip_and_validation(tmp_path):
    """alignment.json 写入后：指纹匹配 → 有效；文本/音频变化 → 失效。"""
    src_text = "A: Hi.\nB: Hello there."
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"x" * 100)
    doc = alignment.build_alignment_doc(
        mode="measured",
        source_text=src_text,
        audio_path=audio,
        segments=[{"text": "Hi.", "speaker": "A", "start": 0.0, "end": 1.0}],
    )
    f = tmp_path / "alignment_podcast.json"
    alignment.save_alignment(doc, f)
    loaded = alignment.load_alignment(f, expect_text=src_text, expect_audio=audio)
    assert loaded is not None
    assert loaded["mode"] == "measured"

    # 文本变化 → 失效
    assert alignment.load_alignment(f, expect_text="A: Changed.", expect_audio=audio) is None
    # 音频变化（大小不同）→ 失效
    audio2 = tmp_path / "a2.mp3"
    audio2.write_bytes(b"y" * 200)
    assert alignment.load_alignment(f, expect_text=src_text, expect_audio=audio2) is None


def test_load_alignment_corrupt(tmp_path):
    f = tmp_path / "alignment_x.json"
    f.write_text("{not json", encoding="utf-8")
    assert alignment.load_alignment(f) is None


# ---------------------------------------------------------------- 时间轴派生（前端兼容形状）

def test_derive_timeline_from_alignment_dialogue():
    doc = {
        "version": 1,
        "track": "podcast",
        "mode": "measured",
        "segments": [
            {"text": "Hi.", "speaker": "a", "start": 0.0, "end": 1.0},
            {"text": "Hello there.", "speaker": "b", "start": 1.35, "end": 2.85},
        ],
    }
    tl = alignment.derive_timeline(doc, speaker_a_name="Alex", speaker_b_name="Mia")
    assert tl[0]["speaker"] == "A" and tl[0]["name"] == "Alex"
    assert tl[1]["speaker"] == "B" and tl[1]["name"] == "Mia"
    assert tl[0]["start"] == 0.0 and tl[0]["end"] == 1.0
    assert tl[1]["duration"] == pytest.approx(1.5)


def test_derive_timeline_monologue():
    doc = {
        "version": 1,
        "track": "monologue",
        "mode": "measured",
        "segments": [
            {"text": "First sentence.", "start": 0.0, "end": 2.0},
            {"text": "Second one!", "start": 2.35, "end": 4.0},
        ],
    }
    tl = alignment.derive_timeline(doc, speaker_a_name="Alex")
    assert all(t["speaker"] == "A" for t in tl)
    assert tl[0]["text"] == "First sentence."
