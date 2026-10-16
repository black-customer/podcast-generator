"""体验回归：同一步的帮助与保存不替换正在操作的输入和录音。"""

import re

from playwright.sync_api import expect

from tests.e2e.test_training_ui import BASE, begin, phone, seed_phone  # noqa: F401


def test_help_keeps_input_selection_details_and_scroll(phone):  # noqa: F811
    page = phone
    seed_phone(page)
    begin(page)
    page.get_by_role("button", name="默写巩固").click()
    field = page.locator("#training-dictation")
    field.fill("I enjoy cooking on weekends.")
    page.wait_for_timeout(650)
    page.evaluate("""() => {
      window.originalInput=document.querySelector('#training-dictation');
      originalInput.focus();originalInput.setSelectionRange(3,8);
      window.originalRoot=document.querySelector('#training-root');
      document.querySelector('.main-content').scrollTop=160;
      window.originalScroll=document.querySelector('.main-content').scrollTop;
    }""")
    page.locator('[data-train="reveal"]').evaluate("b=>b.click()")
    expect(page.locator(".training-reference")).to_be_visible()
    assert page.evaluate("originalInput===document.querySelector('#training-dictation')")
    assert page.evaluate("originalRoot===document.querySelector('#training-root')")
    assert page.evaluate("document.activeElement===originalInput")
    assert page.evaluate("originalInput.selectionStart===3 && originalInput.selectionEnd===8")
    assert page.evaluate(
        "Math.abs(document.querySelector('.main-content').scrollTop-originalScroll)<2"
    )
    expect(field).to_have_value("I enjoy cooking on weekends.")
    page.locator('[data-train="hide"]').evaluate("b=>b.click()")
    expect(field).to_have_value("I enjoy cooking on weekends.")
    assert page.evaluate("originalInput===document.querySelector('#training-dictation')")


def test_focus_layout_restores_browsing_navigation(phone):  # noqa: F811
    page = phone
    seed_phone(page)
    begin(page)
    expect(page.locator("body")).to_have_class(re.compile(".*training-focus.*"))
    expect(page.locator(".sidebar")).to_be_hidden()
    page.evaluate("document.documentElement.style.setProperty('--mobile-vh','480px')")
    expect(page.locator(".app-shell")).to_have_css("height", "480px")
    page.get_by_role("link", name="返回练习", exact=True).click()
    expect(page.locator(".sidebar")).to_be_visible()
    expect(page.get_by_role("heading", name="继续训练", exact=True)).to_be_visible()


def test_optional_context_is_progressively_disclosed(phone):  # noqa: F811
    page = phone
    seed_phone(page)
    page.get_by_role("button", name="不录音，直接继续").click()
    expect(page.locator("#training-answer")).to_be_visible()
    expect(page.locator("#training-intent")).to_be_hidden()
    page.get_by_text("补充意思或外部反馈", exact=True).click()
    page.locator("#training-intent").fill("这是还没说出来的意思")
    page.get_by_role("button", name="确认文字，查看学习材料").click()
    saved = page.evaluate("__mobileState.topics.t.items.i.progress.training.inputs.intent")
    assert saved == "这是还没说出来的意思"


def test_bank_return_restores_selected_question_and_position(phone):  # noqa: F811
    page = phone
    page.goto(BASE + "/#/bank")
    page.locator(".bank-row").first.click()
    expect(page.locator("#baseline-root")).to_be_visible()
    selected = page.evaluate("location.hash")
    page.evaluate("document.querySelector('.main-content').scrollTop=120")
    position = page.evaluate("document.querySelector('.main-content').scrollTop")
    page.evaluate("location.hash='#/today'")
    expect(page.get_by_role("heading", name="今日练习", exact=True)).to_be_visible()
    page.locator('.nav-item[href="#/bank"],.nav-item[href="#/practice"]').first.click()
    expect(page.locator("#baseline-root")).to_be_visible()
    assert page.evaluate("location.hash") == selected
    assert page.evaluate("document.querySelector('.main-content').scrollTop") == position


def test_primary_oral_action_precedes_help_and_fits_phone(phone):  # noqa: F811
    page = phone
    seed_phone(page)
    begin(page)
    action = page.locator('[data-train="sentence-independent"]')
    help_button = page.locator('[data-train="reveal"]')
    assert action.bounding_box()['y'] < help_button.bounding_box()['y']
    assert action.bounding_box()['y'] + action.bounding_box()['height'] < 600
    expect(page.locator('#training-alternate')).to_be_hidden()
    help_button.click()
    expect(page.locator('#training-alternate')).to_be_visible()
    expect(action).to_be_disabled()


def test_focus_selection_count_survives_help_and_empty_selection(phone):  # noqa: F811
    page = phone
    seed_phone(page)
    page.locator('[data-train="start-without"]').click()
    page.locator('[data-train="inputs"]').click()
    counter = page.locator('#training-selection-count')
    expect(counter).to_have_text('已选 2 处表达')
    for checkbox in page.locator('[name="training-focus"]').all():
        checkbox.uncheck()
    expect(counter).to_have_text('未选句子，将直接练整题')
    expect(page.locator('[data-train="understand"]')).to_be_enabled()
    page.locator('[name="training-focus"]').last.check()
    expect(counter).to_have_text('已选 1 处表达')
    page.locator('[data-train="understand"]').click()
    expect(page.locator('.training-prompt')).to_have_text('做饭让我放松。')


def test_phone_bank_search_keeps_readable_width(phone):  # noqa: F811
    page = phone
    page.goto(BASE + '/#/bank')
    search = page.locator('#bank-q')
    expect(search).to_be_visible()
    assert search.bounding_box()['width'] >= 200
    search.fill('food')
    page.locator('.bank-search button').click()
    expect(page.locator('.bank-row')).to_have_count(1)


def test_home_empty_state_offers_real_paths_without_fake_progress(phone):  # noqa: F811
    page = phone
    page.goto(BASE + '/#/today')
    expect(page.locator('.home-workspace')).to_be_visible()
    expect(page.get_by_role('link', name='去题库选题')).to_have_attribute('href', '#/bank')
    expect(page.locator('.home-method li')).to_have_count(3)
    expect(page.locator('.home-history')).to_have_count(0)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


def test_new_page_starts_at_top_after_scrolling_home(phone):  # noqa: F811
    page = phone
    page.goto(BASE + '/#/today')
    expect(page.locator('.home-workspace')).to_be_visible()
    page.evaluate("document.querySelector('.main-content').scrollTop=200")
    page.evaluate("location.hash='#/bank'")
    expect(page.locator('.bank-row')).to_be_visible()
    assert page.locator('.hero-title').bounding_box()['y'] >= 24


def test_desktop_player_controls_fit_without_clipping():
    from playwright.sync_api import sync_playwright

    from tests.e2e.test_q05_ui import mock

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': 1280, 'height': 900})
        mock(page)
        page.goto(BASE + '/#/play/t1/i1')
        expect(page.locator('#remake-item')).to_be_visible()
        for selector in ('#remake-item', '.player-progress', '.player-transport'):
            box = page.locator(selector).bounding_box()
            assert box['x'] >= 0 and box['x'] + box['width'] <= 1280
        browser.close()
