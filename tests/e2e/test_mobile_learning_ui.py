"""手机 UI 用隔离的原生桥模拟器驱动，所有数据及生成结果均为合成内容。"""
import os
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
BASE = os.environ.get("BASE_URL", "http://127.0.0.1:8765")
MOCK = r"""
window.NativeDigest={sha256:text=>{
 let n=2166136261;for(const c of text)n=Math.imul(n^c.charCodeAt(0),16777619);
 return (n>>>0).toString(16).padStart(8,'0').repeat(8);}};
window.__mobileState=JSON.parse(sessionStorage.getItem('synthetic-native-state') || 'null')
 || MobileCore.createState();
window.__mobileNow=sessionStorage.getItem('synthetic-native-clock')
 || '2026-10-03T10:00:00+08:00';
const bank={questions:[{id:'q1',text:'What food do you like?',text_zh:'喜欢什么食物？',
 part:1,topic_id:'food'}],topics:[{id:'food',name_en:'Food',name_zh:'饮食'}],sets:[]};
const listeners={};
const native={
 addListener:async(name,cb)=>{listeners[name]=cb;return{remove(){}};},
 media:async()=>{},
 request:async({method,url,body={}})=>{
  const s=window.__mobileState;
  if(url==='/api/mobile/snapshot')return{value:JSON.parse(JSON.stringify(s))};
  if(url==='/api/mobile/shared')return{value:{text:''}};
  if(url==='/api/mobile/import-draft')return{value:{ok:true}};
  if(url==='/api/mobile/storage')return{value:{media_files:0,media_bytes:0}};
  if(url==='/api/voices')return{value:[
   {provider:'stepfun',voice_id:'lively-girl',name:'Synthetic partner',gender:'female'},
   {provider:'stepfun',voice_id:'vibrant-youth',name:'Synthetic learner',gender:'male'}]};
  if(url==='/api/settings'){
   if(method==='PUT')for(const [k,v]of Object.entries(body))
    if(k!=='stepfun_api_key')s.settings[k]=v;
   return{value:{...s.settings,stepfun_api_key_configured:true,stepfun_api_key_set:true,tts_provider:'stepfun'}};
  }
  if(url==='/api/mobile/migrate'){
   window.__migrationCalls=(window.__migrationCalls || 0)+1;return{value:{ok:true}};
  }
  const m=url.match(/^\/api\/conversations\/([^/]+)\/generate$/);
  if(m){const c=s.conversations[m[1]];
   MobileCore.applyResult(s,c.id,{dialogue:[
    {speaker:'A',en:'What would you like to say?',zh:'你想说什么？'},
    {speaker:'B',en:'Mushrooms have some dietary fiber.',zh:'蘑菇含有一些膳食纤维。'}],
    notes:[{kind:'explicit_gap',target:'dietary fiber',prompt_zh:'描述蘑菇含有的一种成分。',
     reference_en:'Mushrooms have some dietary fiber.',explanation:'fiber 是不可数名词。',
     sources:[{message_id:c.messages[0].id,quote:'dietary fiber'}]}]},
    window.__mobileNow);
   c.audio='/synthetic.m4a';c.status='ready';s.jobs[c.id]={id:c.id,state:'done',kind:'conversation'};return{value:s.jobs[c.id]};
  }
  return{value:MobileCore.route(s,method,url,body,window.__mobileNow,bank)};
 }
};
window.Capacitor={isNativePlatform:()=>true,Plugins:{Learning:native},convertFileSrc:p=>p,registerPlugin:()=>native};
const originalRequest=native.request;
native.request=async args=>{const result=await originalRequest(args);
 sessionStorage.setItem('synthetic-native-state',JSON.stringify(window.__mobileState));
 return result;};
"""


@pytest.fixture()
def phone():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 390, "height": 844},
                                      service_workers="block")
        context.add_init_script(
            (ROOT / "web/mobile-core.js").read_text(encoding="utf-8") + "\n" +
            (ROOT / "web/mobile-api-core.js").read_text(encoding="utf-8") + "\n" + MOCK
        )
        page = context.new_page()
        yield page
        context.close()
        browser.close()


def capture(phone, name):
    folder = ROOT / "data/.tmp/mobile-learning-screenshots"
    folder.mkdir(parents=True, exist_ok=True)
    phone.evaluate("document.getElementById('app').scrollTop=0")
    phone.screenshot(path=str(folder / name))


def test_import_then_oral_review_without_answer_leak(phone):
    phone.goto(BASE + "/#/chat-import")
    phone.locator("#chat-import-input").fill(
        "User: How do I say dietary fiber?\nAssistant: Dietary fiber."
    )
    phone.locator("#chat-read").click()
    expect(phone.locator("#chat-generate")).to_be_visible()
    expect(phone.get_by_text("2 条文本发言", exact=False)).to_be_visible()
    phone.locator("#chat-generate").click()
    expect(phone.locator("#chat-listen")).to_be_visible()
    capture(phone, "chat-material-390.png")
    phone.evaluate("""() => {
      window.__mobileNow='2026-10-04T10:00:00+08:00';
      sessionStorage.setItem('synthetic-native-clock',window.__mobileNow);
    }""")
    phone.goto(BASE + "/#/today")
    phone.locator("#mobile-review-start").click()
    expect(phone.locator(".oral-page")).to_be_visible()
    capture(phone, "oral-prompt-390.png")
    assert "Mushrooms have some dietary fiber." not in phone.locator("#app").inner_text()
    phone.locator('[data-oral="no-record"]').click()
    expect(phone.locator("#app")).to_contain_text("Mushrooms have some dietary fiber.")
    capture(phone, "oral-compare-390.png")
    phone.locator('[data-oral="independent"]').click()
    expect(phone.locator("#app")).to_contain_text("本轮口答完成")
    expect(phone.locator("#app")).to_contain_text("2026-10-07")


def test_mobile_settings_does_not_persist_key_and_layout(phone):
    phone.goto(BASE + "/#/my")
    phone.locator("#mobile-key").fill("synthetic-test-secret")
    phone.locator("#mobile-save-settings").click()
    expect(phone.locator("#mobile-settings-status")).to_have_text("配置已保存。")
    expect(phone.locator("#mobile-key")).to_have_value("")
    assert "synthetic-test-secret" not in phone.evaluate("JSON.stringify(localStorage)")
    assert "synthetic-test-secret" not in phone.evaluate("JSON.stringify(window.__mobileState)")
    for width in (360, 390, 430):
        phone.set_viewport_size({"width": width, "height": 844})
        assert phone.evaluate("document.documentElement.scrollWidth <= innerWidth")
        capture(phone, f"settings-{width}.png")


def test_mobile_navigation_owns_one_destination_and_warns_unknown_request(phone):
    for route, owner in (("today", "today"), ("materials", "materials"),
                         ("my", "my"), ("bank", "bank"), ("chat-import", "today")):
        phone.goto(BASE + "/#/" + route)
        expect(phone.locator('.nav-menu [aria-current="page"]')).to_have_count(1)
        expect(phone.locator('.nav-menu [aria-current="page"]')).to_have_attribute(
            "href", "#/" + owner
        )
        expect(phone.locator(".nav-menu .active")).to_have_count(1)
        for destination in ("今日", "材料", "题库", "我的"):
            expect(phone.locator(".nav-menu").get_by_text(destination, exact=True)).to_be_visible()
    phone.goto(BASE + "/#/my")
    phone.evaluate("document.body.classList.add('player-route')")
    expect(phone.locator(".sidebar")).to_be_visible()
    assert phone.locator("#mobile-save-settings").bounding_box()["height"] >= 48
    select = phone.locator("#mobile-voice-a").bounding_box()
    preview = phone.locator('[data-preview-role="a"]').bounding_box()
    assert preview["y"] - select["y"] - select["height"] >= 8
    phone.evaluate("""() => {
      window.__mobileState.jobs.pending={id:'pending',kind:'conversation',state:'interrupted',
       inflight:'text',errors:[{message:'服务返回 HTTP 429，请稍后手动继续'}]};
      route();
    }""")
    expect(phone.locator("#app")).to_contain_text("可能再次计费")
    expect(phone.locator("#app")).to_contain_text("HTTP 429")


def test_mobile_bank_can_submit_and_keeps_original_answer(phone):
    phone.goto(BASE + "/#/bank?sel=q1")
    expect(phone.locator("#bank-answer-input")).to_be_visible()
    phone.locator("#bank-answer-input").fill("I like mushrooms and rice.")
    phone.locator("#bank-answer-submit").click()
    expect(phone.locator("#app")).to_contain_text("API")
    texts = phone.evaluate(
        "Object.values(window.__mobileState.topics['mobile-ielts'].items).map(i=>i.texts)"
    )
    assert texts[0]["original_answer"] == "I like mushrooms and rice."


def test_mobile_leaving_generation_stops_redirect_and_material_source_filter(phone):
    phone.goto(BASE + "/#/bank?sel=q1")
    phone.locator("#bank-answer-input").fill("I like rice.")
    phone.locator("#bank-answer-submit").click()
    expect(phone.locator("#api-stage-row")).to_be_visible()
    phone.goto(BASE + "/#/my")
    expect(phone.locator("#mobile-save-settings")).to_be_visible()
    phone.evaluate("Object.values(window.__mobileState.jobs).forEach(j=>j.state='done')")
    phone.wait_for_timeout(1300)
    assert phone.url.endswith("#/my")
    phone.evaluate("""() => {
      MobileCore.importConversation(window.__mobileState,
       {provider:'doubao',title:'Synthetic Doubao',messages:[
        {role:'user',text:'How do I say whole grain?'},
        {role:'assistant',text:'Whole grain.'}]},window.__mobileNow);
      MobileCore.importConversation(window.__mobileState,
       {provider:'chatgpt',title:'Synthetic ChatGPT',messages:[
        {role:'user',text:'What is dietary fiber?'},
        {role:'assistant',text:'Dietary fiber.'}]},window.__mobileNow);
      location.hash='#/materials';
    }""")
    phone.locator("#mobile-source").select_option("doubao")
    expect(phone.locator("#mobile-material-results")).to_contain_text("Synthetic Doubao")
    expect(phone.locator("#mobile-material-results")).not_to_contain_text("Synthetic ChatGPT")
    phone.locator("#mobile-search").fill("no match")
    expect(phone.locator("#mobile-material-results")).to_contain_text("没有匹配材料")


def test_completed_legacy_migration_is_not_replayed_on_boot(phone):
    phone.goto(BASE + "/#/today")
    expect(phone.locator(".mobile-page")).to_be_visible()
    count = phone.evaluate("""async() => {
      window.__mobileState.migration.legacy_pack=true;await MobileRuntime.snapshot();
      PackState.active=true;PackState.manifest={pack_version:1,topics:[]};
      await MobileRuntime.migratePack();return window.__migrationCalls || 0;
    }""")
    assert count == 0
    count = phone.evaluate("""async() => {
      PackState.active=true;PackState.manifest={pack_version:2,topics:[]};
      await MobileRuntime.migratePack(true);return window.__migrationCalls || 0;
    }""")
    assert count == 1


def test_full_mobile_ielts_learning_keeps_all_sentences_and_resume(phone):
    phone.goto(BASE + "/#/materials")
    expect(phone.locator(".mobile-page")).to_be_visible()
    phone.evaluate("""() => {
      const texts={question:'What food do you like?',original_answer:'Rice and chicken.',
       natural_english:'Brown rice is a whole grain. Chicken is high in protein.',
       podcast_text:'A: What food do you like?\\nB: Brown rice is a whole grain. '+
        'Chicken is high in protein.',
       podcast_script:'A: What food do you like?\\nB: Brown rice is a whole grain. '+
        'Chicken is high in protein.'};
      const material=MobileCore.validateStudyMaterial({
       complete_chinese:'糙米是全谷物，鸡肉蛋白质高。',
       sentences:[{en:'Brown rice is a whole grain.',zh:'糙米是一种全谷物。',
        explanation:'分类表达',usage:'a whole grain'},
        {en:'Chicken is high in protein.',zh:'鸡肉蛋白质含量高。',
         explanation:'含量表达',usage:'high in protein'}]},texts);
      window.__mobileState.topics.t={id:'t',name:'Synthetic IELTS',items:{i:{id:'i',
       title:texts.question,texts,material,audio:{podcast:'/synthetic.m4a'},
       audioFingerprints:{podcast:'synthetic-bytes'},meta:{created_at:'2026-10-03T00:00:00Z'}}}};
      location.hash='#/learn/t/i';
    }""")
    phone.locator("#study-begin").click()
    phone.locator('[data-act="skip-record"]').click()
    expect(phone.locator(".study-chinese")).to_have_text("糙米是一种全谷物。")
    capture(phone, "ielts-dictation-390.png")
    phone.locator('[data-act="hint"]').click()
    phone.locator(".study-word").first.fill("Brown")
    phone.wait_for_function(
        "window.__mobileState.topics.t.items.i.progress.draft[0]==='Brown'"
    )
    phone.reload()
    expect(phone.locator(".study-word").first).to_have_value("Brown")
    for sentence in ("Brown rice is a whole grain", "Chicken is high in protein"):
        for index, word in enumerate(sentence.split()):
            phone.locator(".study-word").nth(index).fill(word)
        phone.locator('[data-act="check"]').click()
        expect(phone.locator('[data-act="next"]')).to_be_visible()
        phone.locator('[data-act="next"]').click()
    expect(phone.locator("#app")).to_contain_text("看完整中文，连贯说一遍")
    phone.locator('[data-act="skip-record"]').click()
    expect(phone.locator("#app")).to_contain_text("只看原题，脱稿回答")
    phone.locator('[data-act="skip-record"]').click()
    expect(phone.locator("#app")).to_contain_text("回听你的三次回答")
    progress = phone.evaluate("window.__mobileState.topics.t.items.i.progress")
    assert progress["stage"] == "summary"
    assert progress["facts"]["0"]["passed"]
    assert progress["facts"]["1"]["passed"]
    assert phone.evaluate("Object.keys(window.__mobileState.cards).length") == 1
