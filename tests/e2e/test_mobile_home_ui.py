"""首页轻练、主题和内容入口：隔离原生桥与合成音频。"""
import io
import wave
from pathlib import Path

from playwright.sync_api import expect

from tests.e2e import test_mobile_learning_ui as mobile_fixture

BASE = mobile_fixture.BASE
phone = mobile_fixture.phone


def seed(page):
    page.goto(BASE + "/#/today")
    page.evaluate("""() => {
      const items={};
      for(const [id,en,zh] of [['a','I grew up by the river.','我在河边长大。'],
                              ['b','I walk with my family.','我和家人一起散步。']]) {
        const texts={question:'Tell me about yourself.',original_answer:zh,
          natural_english:en,podcast_text:'B: '+en,podcast_script:'B: '+en};
        items[id]={id,title:'合成练习',texts,audio:{podcast:'/home-synthetic.wav'},
          material:MobileCore.validateStudyMaterial({complete_chinese:zh,sentences:[
            {en,zh,explanation:'合成解释',usage:'合成用法'}]},texts),
          timelines:{podcast:{lines:[{role:'b',text:en,start:1,end:3}]}}};
      }
      window.__mobileState.topics.t={id:'t',name:'合成来源',items};
      route();
    }""")
    payload = io.BytesIO()
    with wave.open(payload, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b"\x00\x00" * 8000 * 6)
    page.route("**/home-synthetic.wav", lambda r: r.fulfill(
        status=200, content_type="audio/wav", body=payload.getvalue()
    ))
    expect(page.locator("#home-zh")).to_have_text("我在河边长大。")


def test_home_reveal_audio_next_and_theme_do_not_change_learning(phone):
    seed(phone)
    before = phone.evaluate("JSON.stringify(window.__mobileState)")
    expect(phone.locator("#app")).not_to_contain_text("I grew up by the river.")
    expect(phone.locator("#home-toggle-answer")).to_have_attribute("aria-expanded", "false")
    expect(phone.locator("#home-position")).to_have_text("1 / 2")
    phone.locator("#home-toggle-answer").click()
    expect(phone.locator("#home-toggle-answer")).to_have_attribute("aria-expanded", "true")
    expect(phone.locator("#home-answer")).to_contain_text("I grew up by the river.")
    assert phone.locator("#home-answer-audio").evaluate("a=>a.paused")
    phone.locator("#home-listen").click()
    phone.wait_for_function("!document.getElementById('home-answer-audio').paused")
    phone.locator("#mobile-theme-toggle").click()
    expect(phone.locator("body")).to_have_attribute("data-mobile-theme", "dark")
    expect(phone.locator("#home-answer")).to_be_visible()
    assert not phone.locator("#home-answer-audio").evaluate("a=>a.paused")
    phone.locator("#home-next").click()
    expect(phone.locator("#home-zh")).to_have_text("我和家人一起散步。")
    expect(phone.locator("#home-position")).to_have_text("2 / 2")
    expect(phone.locator("#home-toggle-answer")).to_have_attribute("aria-expanded", "false")
    expect(phone.locator("#home-answer")).to_be_hidden()
    assert phone.locator("#home-answer-audio").evaluate("a=>a.paused")
    assert phone.evaluate("JSON.stringify(window.__mobileState)") == before
    phone.reload()
    expect(phone.locator("body")).to_have_attribute("data-mobile-theme", "dark")
    expect(phone.locator("#home-answer")).to_be_hidden()


def test_home_empty_navigation_and_settings_details(phone):
    phone.goto(BASE + "/#/today")
    expect(phone.locator("#app")).to_contain_text("准备一份练习内容")
    for text in ("练习", "题库", "内容", "我的"):
        expect(phone.locator(".nav-menu").get_by_text(text, exact=True)).to_be_visible()
    phone.goto(BASE + "/#/my")
    expect(phone.locator("#mobile-key")).to_have_count(0)
    phone.get_by_role("link", name="生成服务").click()
    expect(phone.locator("#mobile-key")).to_be_visible()
    phone.goto(BASE + "/#/materials")
    phone.get_by_role("button", name="添加内容").click()
    expect(phone.get_by_role("link", name="导入英语聊天")).to_be_visible()
    expect(phone.get_by_role("link", name="导入语料包")).to_be_visible()


def test_home_audio_failure_and_late_play_keep_current_answer(phone):
    seed(phone)
    phone.unroute("**/home-synthetic.wav")
    phone.route("**/home-synthetic.wav", lambda r: r.fulfill(status=404))
    phone.locator("#home-listen").click()
    expect(phone.locator("#home-audio-notice")).to_contain_text("文字答案")
    expect(phone.locator("#home-en")).to_have_text("I grew up by the river.")
    phone.evaluate("""() => {
      document.getElementById('home-answer-audio').play=()=>new Promise(resolve=>{
        window.__releaseHomePlay=resolve;
      });
    }""")
    phone.locator("#home-listen").click()
    phone.locator("#home-next").click()
    phone.evaluate("window.__releaseHomePlay()")
    expect(phone.locator("#home-zh")).to_have_text("我和家人一起散步。")
    expect(phone.locator("#home-answer")).to_be_hidden()
    expect(phone.locator("#home-audio-notice")).to_be_empty()


def test_home_source_text_is_escaped(phone):
    seed(phone)
    phone.evaluate("""() => {
      const injected='<img id="unsafe-home" src=x onerror="window.__homeUnsafe=true">';
      window.__mobileState.topics.t.items.a.material.sentences[0].zh=injected;
      route();
    }""")
    expect(phone.locator("#home-zh")).to_contain_text("<img")
    expect(phone.locator("#unsafe-home")).to_have_count(0)
    assert phone.evaluate("window.__homeUnsafe===undefined")


def test_history_includes_saved_full_answer_recordings(phone):
    seed(phone)
    phone.evaluate("""() => {
      window.__mobileState.topics.t.items.a.progress={stage:'summary',recordings:[
        {id:'rec',stage:'chinese',path:'/home-synthetic.wav',created_at:'2026-10-06T10:00:00+08:00',duration_sec:6}]};
      location.hash='#/mobile-history';
    }""")
    expect(phone.locator('#app')).to_contain_text('完整回答录音')
    expect(phone.locator('#app')).to_contain_text('看中文说')
    expect(phone.get_by_label('回听看中文说录音')).to_be_visible()


def test_home_reading_surface_handles_long_sentences_and_large_text(phone):
    seed(phone)
    out = Path(__file__).resolve().parents[2] / 'data/.tmp/home-refinement'
    out.mkdir(parents=True, exist_ok=True)
    for theme in ('light', 'dark'):
        if phone.locator('body').get_attribute('data-mobile-theme') != theme:
            phone.locator('#mobile-theme-toggle').click()
        for width in (360, 390, 430):
            phone.set_viewport_size({'width': width, 'height': 844})
            assert phone.evaluate('document.documentElement.scrollWidth <= innerWidth')
            phone.screenshot(path=str(out / f'{theme}-{width}-home.png'))
            phone.locator('#home-toggle-answer').click()
            phone.wait_for_function("document.getElementById('home-answer-audio').readyState >= 1")
            phone.screenshot(path=str(out / f'{theme}-{width}-answer.png'))
            phone.locator('#home-toggle-answer').click()
    phone.evaluate("""() => {
      const item=window.__mobileState.topics.t.items.a;
      const zh='我在河边的一座小城长大，那里的人大多彼此熟悉。';
      const en='I grew up in a small town by the river, where most people knew each other.';
      Object.assign(item.texts,{original_answer:zh,natural_english:en,
        podcast_text:'B: '+en,podcast_script:'B: '+en});
      item.material=MobileCore.validateStudyMaterial({complete_chinese:zh,sentences:[
        {en,zh,explanation:'合成解释',usage:'合成用法'}]},item.texts);
      item.timelines.podcast.lines[0].text=en;
      route();
    }""")
    expect(phone.locator('#home-zh')).to_contain_text('我在河边的一座小城长大')
    phone.set_viewport_size({'width': 360, 'height': 680})
    phone.add_style_tag(content='body.mobile-learning{font-size:22px}')
    for theme in ('light', 'dark'):
        if phone.locator('body').get_attribute('data-mobile-theme') != theme:
            phone.locator('#mobile-theme-toggle').click()
        assert phone.evaluate('document.documentElement.scrollWidth <= innerWidth')
        phone.screenshot(path=str(out / f'{theme}-long-large-text.png'))
        for selector in ('#home-toggle-answer', '#home-listen', '#home-next'):
            button = phone.locator(selector)
            button.scroll_into_view_if_needed()
            assert button.evaluate("""b => {
              const r=b.getBoundingClientRect();
              return b.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2));
            }"""), selector


def test_mobile_theme_layout_and_capture(phone):
    seed(phone)
    out = Path(__file__).resolve().parents[2] / 'data/.tmp/u01-screenshots'
    out.mkdir(parents=True, exist_ok=True)
    for theme in ('light', 'dark'):
        phone.goto(BASE + '/#/today')
        expect(phone.locator('#home-zh')).to_be_visible()
        if phone.locator('body').get_attribute('data-mobile-theme') != theme:
            phone.locator('#mobile-theme-toggle').click()
        for width in (360, 390, 430):
            phone.set_viewport_size({'width': width, 'height': 844})
            assert phone.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert phone.locator('#home-toggle-answer').bounding_box()['height'] >= 48
            phone.screenshot(path=str(out / f'{theme}-{width}-home.png'))
            phone.locator('#home-toggle-answer').click()
            phone.wait_for_function("document.getElementById('home-answer-audio').readyState >= 1")
            phone.screenshot(path=str(out / f'{theme}-{width}-answer.png'))
            phone.locator('#home-toggle-answer').click()
        phone.set_viewport_size({'width': 390, 'height': 844})
        for route in ('my', 'my/services', 'my/voices', 'my/tasks', 'my/files',
                      'my/storage', 'my/preferences', 'materials', 'chat-import', 'bank'):
            phone.goto(BASE + '/#/' + route)
            expect(phone.locator('#app h1').first).to_be_visible()
            assert phone.evaluate('document.documentElement.scrollWidth <= innerWidth'), route
            assert 'IELTS Pod' not in phone.locator('#app').inner_text()
            assert '英语说说说' not in phone.locator('#app').inner_text()
            if route == 'bank':
                last = phone.locator('.bank-tabs .bank-tab').last.bounding_box()
                assert last['x'] + last['width'] <= 390, '三个 Part 入口应同时可见'
            phone.screenshot(path=str(out / f'{theme}-390-{route.replace("/", "-")}.png'))
        phone.goto(BASE + '/#/learn/t/a')
        if theme == 'light':
            phone.locator('#study-begin').click()
            phone.locator('[data-act="skip-record"]').click()
        expect(phone.locator('.study-chinese')).to_be_visible()
        expect(phone.locator('.sidebar')).to_be_hidden()
        phone.screenshot(path=str(out / f'{theme}-390-dictation.png'))
        phone.goto(BASE + '/#/today')
        zoom = phone.add_style_tag(content='body.mobile-learning{font-size:22px}')
        assert phone.evaluate('document.documentElement.scrollWidth <= innerWidth')
        phone.screenshot(path=str(out / f'{theme}-390-large-font.png'))
        zoom.evaluate('element=>element.remove()')
