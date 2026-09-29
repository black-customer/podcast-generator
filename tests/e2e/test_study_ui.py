"""暖纸桌面学习主线：五句默写、提示恢复、三类录音与复习。"""
import os
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest
import requests
from playwright.sync_api import sync_playwright

from server import library, study, study_progress

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8765")
ANSWER = [
    ("我通常下班后去散步。", "I usually go for a walk after work."),
    ("这能让我放松下来。", "It helps me unwind."),
    ("比起刷手机，我更喜欢散步。", "I prefer walking to scrolling through my phone."),
    ("有时我会在路上听一集播客。", "Sometimes I listen to a podcast along the way."),
    ("等我到家时，我感觉放松多了。", "By the time I get home, I feel much more relaxed."),
]


@pytest.fixture()
def sample():
    topic = requests.post(
        f"{BASE_URL}/api/topics", json={"name": f"学习验收-{uuid.uuid4().hex[:8]}"}, timeout=10
    ).json()
    tid = topic["id"]
    question = "What do you usually do after work?"
    body = {
        "question": question,
        "original_answer": (
            "我下班常去散步。It help me relaxed. "
            "比起刷手机我更喜欢走路。有时路上听播客，到家感觉轻松。"
        ),
        "natural_english": " ".join(en for _, en in ANSWER),
        "podcast_text": f"A: {question}\nB: " + " ".join(en for _, en in ANSWER),
    }
    try:
        created = requests.post(f"{BASE_URL}/api/topics/{tid}/items", json=body, timeout=10).json()
        iid = created["id"]
        audio = library.item_path(tid, iid) / "audio_podcast.mp3"
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "anullsrc",
                        "-t", "8", "-codec:a", "libmp3lame", "-y", str(audio)],
                       check=True, capture_output=True)
        rows = [{"zh": zh, "en": en, "explanation": "按自然英语组织本句。",
                 "usage": "练习完整回答中的表达。"} for zh, en in ANSWER]
        rows[1]["original_error"] = {
            "quote": "It help me relaxed.", "issue": "三单形式与动词形态有误。",
            "correction": "It helps me relax.",
        }
        study.save_material(tid, iid, {
            "complete_chinese": "我下班后去散步、听播客，感觉放松。", "sentences": rows,
        })
        yield tid, iid
    finally:
        requests.delete(f"{BASE_URL}/api/topics/{tid}", timeout=10)
        private = study_progress.PRIVATE_DIR / tid
        if private.resolve().is_relative_to(study_progress.PRIVATE_DIR.resolve()):
            shutil.rmtree(private, ignore_errors=True)


def _record_and_save(page):
    page.locator("[data-rec='start']").click()
    page.wait_for_timeout(350)
    page.locator("[data-rec='stop']").click()
    page.locator("[data-rec='save']").wait_for(state="visible")
    page.locator("[data-rec='save']").click()
    page.locator("[data-act='advance']").wait_for(state="visible")
    page.locator("[data-act='advance']").click()


def _fill_sentence(page, en):
    words = [word.strip(".,?!") for word in en.split()]
    boxes = page.locator(".study-word")
    boxes.first.wait_for(state="visible")
    assert boxes.count() == len(words)
    for i, word in enumerate(words):
        boxes.nth(i).fill(word)
    page.locator("[data-act='check']").click()
    page.locator(".study-answer").wait_for(state="visible")


def test_five_sentences_recordings_and_review(sample):
    tid, iid = sample
    out = Path("data/.tmp/study-ui")
    out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--use-fake-device-for-media-stream",
                                                    "--use-fake-ui-for-media-stream"])
        context = browser.new_context(viewport={"width": 1536, "height": 1024},
                                      permissions=["microphone"])
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda err: errors.append(str(err)))
        try:
            page.goto(f"{BASE_URL}/#/learn/{tid}/{iid}")
            page.locator(".study-recorder").wait_for()
            _record_and_save(page)
            page.locator(".study-word").first.wait_for()
            page.screenshot(path=str(out / "B03.png"), full_page=True)
            _fill_sentence(page, ANSWER[0][1])
            page.locator("[data-act='next']").click()
            page.locator(".study-word").first.fill("It")
            page.locator(".study-word").nth(1).fill("help")
            page.locator(".study-word").nth(2).fill("me")
            page.locator(".study-word").nth(3).fill("unwind")
            page.locator("[data-act='check']").click()
            assert "拼写" in page.locator("#study-feedback").inner_text()
            page.locator(".study-word").nth(1).fill("helps")
            page.locator("[data-act='check']").click()
            page.locator(".study-answer").wait_for()
            assert "It help me relaxed." in page.locator(".study-explanation").inner_text()
            page.screenshot(path=str(out / "B06.png"), full_page=True)
            page.locator("[data-act='next']").click()
            page.locator(".study-word").first.fill("I")
            page.locator("[data-act='hint']").click()
            page.locator("#study-hint").wait_for(state="visible")
            page.wait_for_timeout(5200)
            assert page.locator(".study-word").first.input_value() == "I"
            page.reload()
            page.locator(".study-word").first.wait_for()
            assert page.locator(".study-word").first.input_value() == "I"
            for index in (2, 3, 4):
                _fill_sentence(page, ANSWER[index][1])
                page.locator("[data-act='next']").click()
            page.locator(".study-full-chinese").wait_for()
            page.screenshot(path=str(out / "B07.png"), full_page=True)
            _record_and_save(page)
            page.locator(".study-full-chinese").wait_for(state="detached")
            assert page.locator(".study-full-chinese").count() == 0
            _record_and_save(page)
            page.get_by_role("heading", name="回听你的三次回答").wait_for()
            page.locator(".study-recording-row").first.wait_for()
            assert page.locator(".study-recording-row").count() == 3
            page.screenshot(path=str(out / "B09.png"), full_page=True)
            page.goto(f"{BASE_URL}/#/review")
            page.locator(".study-review-list a").first.wait_for()
            assert page.locator(".study-review-list a").count() >= 2
            assert "It helps me unwind" not in page.locator(".study-review-list").inner_text()
            page.locator("#study-review-start").click()
            for index in (1, 2):
                _fill_sentence(page, ANSWER[index][1])
                page.locator("[data-act='next']").click()
            page.get_by_role("heading", name="本轮句子复习完成").wait_for()
            assert page.locator(".study-review-result").count() == 2
            page.screenshot(path=str(out / "B14.png"), full_page=True)
            assert not errors, errors
        finally:
            browser.close()


@pytest.fixture()
def sample_no_material():
    """有音频但缺逐句材料的条目：学习页应给出待补齐状态与恢复入口。"""
    topic = requests.post(
        f"{BASE_URL}/api/topics", json={"name": f"学习验收-{uuid.uuid4().hex[:8]}"}, timeout=10
    ).json()
    tid = topic["id"]
    question = "Do you prefer mornings or evenings?"
    body = {
        "question": question,
        "original_answer": "我更喜欢晚上，晚上安静。I am more relax at night.",
        "natural_english": "I prefer evenings. They are much quieter.",
        "podcast_text": f"A: {question}\nB: I prefer evenings. They are much quieter.",
    }
    try:
        created = requests.post(f"{BASE_URL}/api/topics/{tid}/items", json=body, timeout=10).json()
        iid = created["id"]
        audio = library.item_path(tid, iid) / "audio_podcast.mp3"
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "anullsrc",
                        "-t", "5", "-codec:a", "libmp3lame", "-y", str(audio)],
                       check=True, capture_output=True)
        yield tid, iid
    finally:
        requests.delete(f"{BASE_URL}/api/topics/{tid}", timeout=10)
        private = study_progress.PRIVATE_DIR / tid
        if private.resolve().is_relative_to(study_progress.PRIVATE_DIR.resolve()):
            shutil.rmtree(private, ignore_errors=True)


def test_material_missing_shows_recovery(sample_no_material):
    tid, iid = sample_no_material
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1536, "height": 1024})
        try:
            page.goto(f"{BASE_URL}/#/learn/{tid}/{iid}")
            page.locator(".study-missing").wait_for()
            assert "待补齐" in page.locator(".study-missing h1").inner_text()
            assert page.locator("[data-missing='prepare']").count() == 1
            assert "继续听音频" in page.locator(".study-missing").inner_text()
        finally:
            browser.close()


def test_permission_denied_and_unreliable_audio_fallback(sample):
    tid, iid = sample
    requests.patch(f"{BASE_URL}/api/topics/{tid}/items/{iid}/study/progress",
                   json={"stage": "dictation"}, timeout=10)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1536, "height": 1024})
        context.add_init_script("""Object.defineProperty(navigator.mediaDevices, 'getUserMedia', {
          value: async () => { throw new DOMException('Permission denied', 'NotAllowedError'); }
        });""")
        page = context.new_page()
        try:
            page.goto(f"{BASE_URL}/#/learn/{tid}/{iid}")
            page.locator("[data-act='play']").click()
            page.wait_for_function("document.querySelector('#study-feedback')?.textContent.includes('完整音频')")
            requests.patch(f"{BASE_URL}/api/topics/{tid}/items/{iid}/study/progress",
                           json={"stage": "before"}, timeout=10)
            page.reload()
            page.locator("[data-rec='start']").click()
            page.wait_for_function("document.querySelector('#study-rec-error')?.textContent.includes('无法使用麦克风')")
            assert "无法使用麦克风" in page.locator("#study-rec-error").inner_text()
        finally:
            browser.close()
