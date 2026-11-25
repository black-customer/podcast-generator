/* 桌面三步口语练习与闪电复习。 */

let session = null;
let activeCapture = null;
let playback = null;
let playbackRevision = 0;
const stagedBlind = new Map();
const voiceNames = { golden_self: "我的母语分身", af_bella: "Bella", am_liam: "Liam",
  af_heart: "Heart", am_michael: "Michael", am_puck: "Puck", am_fenrir: "Fenrir" };

const enabled = () => !MobileRuntime.native && !PackState.active;
const itemPath = (tid, iid) => `/api/topics/${encodeURIComponent(tid)}/items/${encodeURIComponent(iid)}`;
const button = (action, label, style = "") =>
  `<button type="button" class="study-button ${style}" data-arcade="${action}">${label}</button>`;
const chunk = text => text ? `<mark class="arcade-chunk">${esc(text)}</mark>` : "";
const hotkey = key => `<kbd>${key}</kbd>`;
const recordKey = key => `arcade:${key}`;
const active = ctx => session === ctx && !viewStale(ctx.token);
const isReview = ctx => ctx.kind !== "train";
const voiceLabel = data => voiceNames[data.voice] || "示范回答";

function stageNav(step) {
  return `<ol class="arcade-steps" aria-label="练习步骤">${["听懂与抓重点", "逐句开口", "脱稿回答"].map(
    (label, index) => `<li ${step === index + 1 ? 'aria-current="step"' : ""}${step > index + 1 ?
      ' class="done"' : ""}><span>${index + 1}</span>${label}</li>`).join("")}</ol>`;
}

async function home(token) {
  const ctx = { token, kind: "home", step: 2, index: 0, revealed: false, cachedAudio: new Map() };
  session = ctx;
  $app.innerHTML = `<main class="arcade-home" aria-labelledby="arcade-home-title">
    <header class="arcade-home-head"><div><h1 id="arcade-home-title">今日练习</h1>
      <p id="arcade-home-progress" role="status">正在找可练的句子…</p></div>
      <nav aria-label="今日练习入口"><a class="study-button" href="#/radio">教学电台</a>
      <button class="study-button" id="arcade-open-draw" type="button">范围随机抽题</button></nav></header>
    <div id="arcade-home-card"></div>
    <section class="arcade-frame arcade-draw" id="arcade-draw" hidden aria-labelledby="arcade-draw-title">
      <h2 id="arcade-draw-title">抽一道新题</h2>
      <form><div class="arcade-draw-filters">
        <label>Part<select name="part"><option value="all">全部 Part</option>
          <option value="1">Part 1</option><option value="2">Part 2</option><option value="3">Part 3</option></select></label>
        <label>考季<select name="set"><option value="">全部考季</option></select></label>
        <label>话题<select name="topic"><option value="">全部话题</option></select></label>
        <label>作答状态<select name="answer_status"><option value="">优先未回答</option>
          <option value="unanswered">仅未回答</option><option value="answered">仅已回答</option>
          <option value="all">全部</option></select></label>
      </div><div class="arcade-controls"><button class="study-button primary" type="submit">随机抽题</button>
      <a class="study-button" href="#/practice">浏览题库</a></div>
      <p class="arcade-muted" role="status"></p></form>
    </section>
    <p class="arcade-status" id="arcade-status" role="status"></p>
    <div id="arcade-home-setup"></div>
    <details class="arcade-board"><summary>我的口语病历榜</summary><div id="arcade-home-board"></div></details>
    <footer class="arcade-home-footer"><a href="#/review">复习记录</a><a href="#/legacy-today">历史训练与复验</a></footer>
  </main>`;
  bindDraw(ctx);
  api("GET", "/api/settings").then(settings => {
    if (active(ctx) && !settings.llm_configured)
      document.getElementById("arcade-home-setup").innerHTML = apiSetupBanner();
  }).catch(() => {});
  api("GET", "/api/arcade/error-board").then(board => {
    if (!active(ctx)) return;
    const diagnoses = board.top.slice(0, 3);
    document.getElementById("arcade-home-board").innerHTML = `${diagnoses.length ?
      `<ol>${diagnoses.map(row => `<li><strong>${esc(row.label)}</strong><span>${esc(row.count)} 次</span></li>`).join("")}</ol>` :
      '<p class="arcade-muted">还没有可归类的原话问题。</p>'}
      <button class="study-button" id="arcade-copy-prompt" type="button">复制今日 AI 陪练指令</button>
      ${board.today_chunks.length ? `<div class="arcade-chunks">${board.today_chunks.map(chunk).join("")}</div>` : ""}`;
    document.getElementById("arcade-copy-prompt").onclick = () => copyText(board.prompt);
  }).catch(() => {
    if (active(ctx)) document.getElementById("arcade-home-board").textContent = "病历榜读取失败，请刷新重试。";
  });
  try {
    const {cards, due_count: count} = await api("GET", "/api/arcade/blitz?include_pending=true");
    if (!active(ctx)) return;
    ctx.cards = cards;
    ctx.due = count;
    renderHomeCard(ctx);
  } catch (error) {
    if (!active(ctx)) return;
    document.getElementById("arcade-home-progress").textContent = "暂时无法读取练习材料";
    ctx.showDraw();
    note(error.message);
  }
}

function bindDraw(ctx) {
  const panel = document.getElementById("arcade-draw");
  const toggle = document.getElementById("arcade-open-draw");
  const form = panel.querySelector("form"), fields = form.elements;
  const status = form.querySelector("[role=status]"), submit = form.querySelector("[type=submit]");
  let loaded = false, revision = 0;
  toggle.setAttribute("aria-controls", panel.id);
  toggle.setAttribute("aria-expanded", "false");
  const filters = async () => {
    const current = ++revision;
    submit.disabled = true;
    status.textContent = "正在读取范围…";
    try {
      const result = await api("GET", `/api/bank/questions?part=${fields.part.value}&page_size=1`);
      if (!active(ctx) || current !== revision) return;
      for (const [name, label, options] of [["set", "全部考季", result.sets], ["topic", "全部话题", result.topics]]) {
        const selected = fields[name].value;
        fields[name].replaceChildren(new Option(label, ""), ...options.map(row => new Option(row.name_zh, row.id)));
        if (options.some(row => row.id === selected)) fields[name].value = selected;
      }
      loaded = result.available;
      status.textContent = loaded ? "" : "公开题库尚未就绪。";
    } catch (error) {
      if (active(ctx) && current === revision) status.textContent = error.message;
    } finally {
      if (active(ctx) && current === revision) submit.disabled = false;
    }
  };
  ctx.showDraw = () => {
    panel.hidden = false;
    toggle.setAttribute("aria-expanded", "true");
    if (!loaded) filters();
  };
  toggle.onclick = () => {
    if (panel.hidden) { ctx.showDraw(); fields.part.focus(); }
    else { panel.hidden = true; toggle.setAttribute("aria-expanded", "false"); }
  };
  fields.part.onchange = filters;
  form.onsubmit = async event => {
    event.preventDefault();
    const scope = new URLSearchParams([...new FormData(form)].filter(([, value]) => value));
    const query = new URLSearchParams(scope);
    query.set("random", "1");
    if (scope.has("set")) query.set("set_filter", scope.get("set"));
    query.delete("set");
    try {
      const last = sessionStorage.getItem("arcade-last-question");
      if (last) query.set("exclude_id", last);
    } catch (_) {}
    submit.disabled = true;
    try {
      const result = await api("GET", `/api/bank/questions?${query}`);
      if (!active(ctx)) return;
      const question = result.items?.[0];
      if (!question) { status.textContent = "此范围内没有另一道题，请调整筛选。"; return; }
      try { sessionStorage.setItem("arcade-last-question", question.id); } catch (_) {}
      scope.set("sel", question.id);
      scope.set("page", result.selected_page || 1);
      if (question.answered) scope.set("write", "1");
      location.hash = `#/bank?${scope}`;
    } catch (error) {
      if (active(ctx)) status.textContent = error.message;
    } finally {
      submit.disabled = false;
    }
  };
}

function renderHomeCard(ctx) {
  const card = document.getElementById("arcade-home-card");
  const progress = document.getElementById("arcade-home-progress");
  if (!ctx.cards.length) {
    progress.textContent = "今天没有到期待练的句子";
    ctx.showDraw();
    return;
  }
  progress.textContent = ctx.due
    ? `今日到期 ${ctx.due} 句 · 本轮已练 ${ctx.index} 句`
    : `新材料 ${ctx.cards.length} 句 · 本轮已练 ${ctx.index} 句`;
  card.innerHTML = sentence(ctx);
  bindPracticeActions(card, ctx);
  if (ctx.index >= ctx.cards.length) ctx.showDraw();
}

async function open(tid, iid, token) {
  const url = `${itemPath(tid, iid)}/arcade`;
  const ctx = { tid, iid, token, url, step: 1, index: 0, revealed: false, kind: "train",
    cachedAudio: new Map(), retry: null };
  session = ctx;
  document.body.classList.add("training-focus");
  ExperienceUI.loading("单题练习");
  try {
    ctx.data = await api("GET", url);
    if (!active(ctx)) return;
    render(ctx);
    if (ctx.data.audio_url && ctx.data.status === "ready") play(ctx, ctx.data.audio_url, 0);
    if (ctx.data.status === "preparing") pollMaterial(ctx);
  } catch (error) {
    if (active(ctx)) ExperienceUI.readError("暂时无法读取本题", error);
  }
}

async function blitz(token) {
  const ctx = { token, kind: "blitz", step: 2, index: 0, revealed: false, cachedAudio: new Map() };
  session = ctx;
  document.body.classList.add("training-focus");
  ExperienceUI.loading("闪电刷句");
  try {
    ctx.cards = (await api("GET", "/api/arcade/blitz")).cards;
    if (active(ctx)) render(ctx);
  } catch (error) {
    if (active(ctx)) ExperienceUI.readError("暂时无法读取复习句子", error);
  }
}

function pollMaterial(ctx) {
  clearTimeout(ctx.poll);
  ctx.poll = setTimeout(async () => {
    if (!active(ctx)) return;
    try {
      ctx.data = await api("GET", ctx.url);
      if (!active(ctx)) return;
      if (ctx.data.status === "preparing") pollMaterial(ctx);
      render(ctx);
    } catch (error) {
      if (active(ctx)) note(error.message);
    }
  }, 1200);
}

function reference(ctx) {
  const d = ctx.data;
  if (d.status !== "ready") return `<section class="arcade-frame"><h2>准备本题的逐句材料</h2>
    <p>${esc(d.reason)}</p><div class="arcade-controls">${d.audio_url ? button("demo", "播放完整问答") : ""}
    ${d.audio_url && d.status !== "preparing" ? button("prepare", "准备逐句材料", "primary") : ""}
    <a class="study-button" href="#/legacy-train/${esc(encodeURIComponent(ctx.tid))}/${esc(encodeURIComponent(ctx.iid))}">打开历史训练</a></div></section>`;
  const lines = d.alignment.lines;
  const words = d.alignment.words;
  return `<div class="arcade-reference">
    <section class="arcade-frame arcade-script"><header><h2>听完整问答</h2>${button("demo", "播放问答")}</header>
    ${d.dry_run ? '<p class="arcade-muted">当前音频是试运行占位。</p>' : ""}
    ${lines.map(line => {
      const within = words.filter(word => word.start >= line.start - 0.03 && word.start < line.end);
      return `<div class="arcade-line"><span>${line.speaker === "A" ? "考官" : esc(voiceLabel(d))}</span>
        <p>${timedText(line, within)}</p></div>`;
    }).join("") || d.sentences.map(row => `<p>${esc(row.en)}</p>`).join("")}</section>
    <section class="arcade-frame arcade-notes"><h2>带走这些表达</h2>
      <div class="arcade-chunks">${[...new Set(d.sentences.map(row => row.key_chunk).filter(Boolean))].slice(0, 3).map(chunk).join("")
        || '<p class="arcade-muted">这份材料尚未标注语块。</p>'}</div>
      ${d.sentences.some(row => row.gap_kind === "explicit_gap") ?
        `<h3>这次想说的词块</h3><div class="arcade-chunks">${d.sentences.filter(row =>
          row.gap_kind === "explicit_gap").map(row => chunk(row.key_chunk)).join("")}</div>` : ""}
    </section></div>
    <div class="arcade-controls arcade-proceed">${button("next", `${d.sentences.some(row => row.original_error)
      ? "先重说原话中的问题句" : "开始逐句开口"} ${hotkey("Space")}`, "primary")}
      ${RadioUI.itemLink(ctx.tid, ctx.iid)}</div>`;
}

function repair(ctx) {
  const row = ctx.repairs[ctx.repairIndex], error = row.original_error;
  return `<section class="arcade-frame arcade-repair">
    <h2>把这句话重说一遍</h2>
    <p class="arcade-intent">${esc(row.zh)}</p>
    <dl><div><dt>你的原话</dt><dd lang="en">${esc(error.quote)}</dd></div>
      <div><dt>可以改的地方</dt><dd>${esc(error.issue)}</dd></div></dl>
    <details id="arcade-repair-answer"><summary>开口后看改法</summary><p lang="en">${esc(error.correction)}</p></details>
    <div class="arcade-controls">${button("next", ctx.repairIndex + 1 < ctx.repairs.length
      ? "下一句修复" : "继续逐句开口", "primary")}</div></section>`;
}

function timedText(line, words) {
  const text = line.text.replace(/\[[^\]]*\]\s*/g, "");
  if (!words.length) return `<button class="arcade-word" type="button"
    data-start="${esc(line.start)}">${esc(text)}</button>`;
  let cursor = 0;
  const normalized = text.toLowerCase().replaceAll("’", "'");
  const html = words.map(word => {
    const index = normalized.indexOf(word.text.toLowerCase().replaceAll("’", "'"), cursor);
    if (index < 0) return "";
    const end = index + word.text.length;
    const part = esc(text.slice(cursor, index)) + `<button class="arcade-word" type="button"
      data-start="${esc(word.start)}" data-end="${esc(word.end)}">${esc(text.slice(index, end))}</button>`;
    cursor = end;
    return part;
  }).join("");
  return html + esc(text.slice(cursor));
}

function sentence(ctx) {
  const review = isReview(ctx);
  const rows = review ? ctx.cards : ctx.data.sentences;
  const row = rows[ctx.index];
  if (!row) return `<section class="arcade-frame arcade-recall"><h2>${rows.length ? "本轮刷句完成" : "今天没有到期句子"}</h2>
    <p>${rows.length ? `你已练完 ${esc(rows.length)} 句。` : "练过的新句子会按复习日期出现在这里。"}</p>
    <a class="study-button primary" href="#/practice">去题库选题</a></section>`;
  return `<section class="arcade-frame arcade-recall" data-revealed="${ctx.revealed}">
    <div class="arcade-recall-meta"><span>第 ${esc(ctx.index + 1)} / ${esc(rows.length)} 句</span>
      <span>${review ? "3 秒反应时间" : "3.5 秒反应时间"}</span></div>
    <div class="arcade-reaction" aria-hidden="true" style="--reaction-time:${review ? 3000 : 3500}ms"><span></span></div>
    <p class="arcade-intent">${esc(row.zh)}</p>
    <div class="arcade-reveal" ${ctx.revealed ? "" : "hidden"}><p class="arcade-plain-answer" lang="en">${highlight(row.en, row.key_chunk)}</p>
      <div class="arcade-pronunciation" hidden></div>
      <div class="arcade-voice-control">
        ${row.prosody ? '<label><input type="checkbox" data-prosody> 发音标</label>' : ""}
        <label>收听声音 <select data-answer-voice><option value="demo">母语示范</option>
          <option value="golden_self" ${chosenVoice(ctx, row) === "golden_self" ? "selected" : ""}>我的母语分身</option></select></label>
      </div>
    </div>
    <div class="arcade-controls">
      ${button("reveal", `揭晓并听示范 ${hotkey("Space")}`, "primary")}
      ${review ? "" : button("record", `录音对比 ${hotkey("R")}`)}
    </div>
    <div class="arcade-controls arcade-grade" ${ctx.revealed ? "" : "hidden"}>
      ${button("good", `${hotkey("1")} 顺畅`)}${button("again", `${hotkey("2")} 卡壳`)}
    </div><p class="arcade-feedback" role="status"></p>
  </section>`;
}

function pronunciation(row) {
  const data = row.prosody;
  const matches = [...row.en.matchAll(/[A-Za-z]+(?:['’][A-Za-z]+)*|\d+(?:\.\d+)?/g)];
  const pairs = new Map(data.linking_pairs.map(pair => [pair.from, pair.type]));
  const cues = {cv_link: ["‿", "辅元连读"], flap_t: ["‿", "闪音连读"],
    held_stop: ["×", "失爆衔接"], reduction: ["‿", "缩读"]};
  let cursor = 0;
  const parts = matches.map(([word], index) => {
    const start = matches[index].index;
    const gap = row.en.slice(cursor, start);
    cursor = start + word.length;
    const focus = data.focus_words.includes(index), nuclear = index === data.nuclear_word;
    const ipa = data.weak_words[index], pair = cues[pairs.get(index)];
    return `${esc(gap)}<span class="arcade-pron-word ${nuclear ? "nuclear" : ""}">
      ${focus ? `<strong>${esc(word)}</strong>` : esc(word)}
      ${ipa ? `<small>/${esc(ipa)}/</small>` : ""}
      ${data.flap_t_words.includes(index) ? '<sup title="闪音">ɾ</sup>' : ""}
      ${pair ? `<sup title="${pair[1]}">${pair[0]}</sup>` : ""}
      ${data.break_after.includes(index) ? '<sup title="意群停顿">/</sup>' : ""}</span>`;
  });
  return `<p lang="en">${parts.join("")}${esc(row.en.slice(cursor))}
    <span title="句末语调">${esc(data.intonation)}</span></p>
    <p class="arcade-muted">粗体为重读，下划线标句核。语流提示供跟读参考。</p>`;
}

function highlight(text, phrase) {
  const index = phrase ? text.toLowerCase().indexOf(phrase.toLowerCase()) : -1;
  if (index < 0) return esc(text);
  const end = index + phrase.length;
  return esc(text.slice(0, index)) + chunk(text.slice(index, end)) + esc(text.slice(end));
}

function challenge(ctx) {
  const phrases = [...new Set(ctx.data.sentences.map(row => row.key_chunk).filter(Boolean))];
  return `<section class="arcade-frame arcade-recall"><div class="arcade-recall-meta"><span>只看原题</span><span>最多 60 秒</span></div>
    <p class="arcade-intent" lang="en">${esc(ctx.data.question)}</p>
    ${phrases.length ? `<details><summary>需要时查看语块</summary><div class="arcade-chunks">${phrases.map(chunk).join("")}</div></details>` : ""}
    <div class="arcade-controls">${button("record", "开始脱稿录音", "primary")}${button("skip", "无录音完成")}</div>
    <p class="arcade-feedback" role="status"></p></section>`;
}

function comparison(ctx) {
  const d = ctx.data;
  const before = d.blind?.analysis;
  const after = d.final?.analysis;
  const beforeWpm = before?.wpm, afterWpm = after?.wpm;
  const pauses = before?.long_pauses != null && after?.long_pauses != null ?
    before.long_pauses - after.long_pauses : null;
  const chunks = [...new Set(d.sentences.map(row => row.key_chunk).filter(Boolean))];
  const displayWpm = beforeWpm != null && afterWpm != null ? `${beforeWpm} → ${afterWpm} WPM` :
    afterWpm != null ? `${afterWpm} WPM（脱稿）` : "暂无可比数据";
  const displayPauses = pauses == null ? (after?.long_pauses ?? "暂无可比数据") :
    `${before.long_pauses} → ${after.long_pauses} 次`;
  const pauseDelta = pauses == null ? "" : pauses > 0 ? `减少 ${pauses} 次` :
    pauses < 0 ? `增加 ${-pauses} 次` : "次数相同";
  return `<section class="arcade-frame arcade-summary"><h2>口语前后对比</h2>
    <div class="arcade-tracks">${[["blind", "盲答原声"], ["final", "练后脱稿"], ["demo", voiceLabel(d)]].map(
      ([type, name]) => `<div><strong>${esc(name)}</strong>${d[type]?.url || type === "demo" && d.audio_url
        ? button(type === "demo" ? "answer" : type, "收听") : '<span class="arcade-muted">本次无录音</span>'}</div>`).join("")}</div>
    <dl class="arcade-metrics"><div><dt>英语语速</dt><dd>${esc(displayWpm)}</dd></div>
    <div><dt>长停顿（超过 0.8 秒）</dt><dd>${esc(displayPauses)}</dd>
    ${pauseDelta ? `<span class="arcade-muted">${esc(pauseDelta)}</span>` : ""}</div></dl>
    ${chunks.length ? `<h3>语块命中</h3><div class="arcade-chunks">${chunks.map(phrase => {
      const hit = after?.matched_chunks?.includes(phrase);
      return `<span class="arcade-hit ${hit ? "matched" : ""}">${esc(phrase)}${hit ? ' <b aria-label="已识别">✓</b>' : ""}</span>`;
    }).join("")}</div>` : ""}
    ${d.final?.analysis_error ? `<p class="arcade-muted">录音已保存。${esc(d.final.analysis_error)}</p>` : ""}
    ${after && after.wpm == null ? '<p class="arcade-muted">未识别到可计算语速的完整英文。</p>' : ""}
    <div class="arcade-controls arcade-proceed">${d.blind && d.final && !d.dry_run && d.answer_spans.length &&
      d.alignment.mode !== "estimated" ? button("export", "导出三合一 MP3", "primary") : ""}
    <a class="study-button ${d.blind && d.final && !d.dry_run ? "" : "primary"}" href="#/practice">再来一题</a>
    ${RadioUI.itemLink(ctx.tid, ctx.iid)}
    <a class="study-button" href="#/today">返回首页</a></div>
  </section>`;
}

function render(ctx) {
  if (!active(ctx)) return;
  const review = isReview(ctx);
  let body;
  if (ctx.step === 1) body = ctx.repairIndex == null ? reference(ctx) : repair(ctx);
  else if (ctx.step === 2) body = sentence(ctx);
  else if (ctx.step === 3) body = challenge(ctx);
  else body = comparison(ctx);
  $app.innerHTML = `<main class="arcade-workspace" data-stage="${review ? "blitz" : esc(ctx.step)}">
    <header class="arcade-nav"><a href="#/today">← 今日练习</a>
      ${review ? "" : `<a href="#/play/${esc(encodeURIComponent(ctx.tid))}/${esc(encodeURIComponent(ctx.iid))}">自由收听</a>`}</header>
    ${review ? "" : stageNav(Math.min(ctx.step, 3))}
    ${ctx.step === 3 ? "" : `<h1 class="arcade-title" tabindex="-1">${esc(review ? "闪电刷句" : ctx.data.question)}</h1>`}
    ${body}<p class="arcade-status" id="arcade-status" role="status"></p>
    <button class="study-button" id="arcade-retry" hidden>重试保存录音</button>
  </main>`;
  bindPracticeActions($app.querySelector(".arcade-workspace"), ctx);
  if (!review && ctx.step >= 2 && ctx.step <= 3) restoreTake(ctx);
}

function bindPracticeActions(root, ctx) {
  root.onclick = event => {
    const word = event.target.closest("[data-start]");
    if (word) play(ctx, ctx.data.audio_url, Number(word.dataset.start));
    const control = event.target.closest("[data-arcade]");
    if (control) action(ctx, control.dataset.arcade);
  };
  const prosody = root.querySelector("[data-prosody]");
  if (prosody) {
    const output = root.querySelector(".arcade-pronunciation");
    const sync = () => {
      output.hidden = !ctx.prosodyOn;
      root.querySelector(".arcade-plain-answer").hidden = Boolean(ctx.prosodyOn);
      if (ctx.prosodyOn) output.innerHTML = pronunciation(currentRow(ctx));
    };
    prosody.checked = Boolean(ctx.prosodyOn);
    if (ctx.prosodyOn && ctx.revealed) sync();
    prosody.onchange = () => { ctx.prosodyOn = prosody.checked; sync(); };
  }
  const voice = root.querySelector("[data-answer-voice]");
  if (voice) voice.onchange = () => { ctx.voicePreference = voice.value; reveal(ctx); };
}

function note(text) {
  const node = document.getElementById("arcade-status");
  if (node) node.textContent = text;
}

function stopAudio() {
  playbackRevision += 1;
  if (playback) {
    playback();
    playback = null;
  }
}

function play(ctx, url, start = 0, end = null) {
  if (!url || !active(ctx)) return;
  stopAudio();
  $audio.pause();
  const source = ctx.audio || (ctx.audio = new Audio());
  if (source.getAttribute("src") !== url) source.src = url;
  source.currentTime = start;
  let frame = 0;
  const update = () => {
    if (end != null && source.currentTime >= end) { stopAudio(); return; }
    $app.querySelectorAll(".arcade-word[data-end]").forEach(word => word.classList.toggle("spoken",
      source.currentTime >= Number(word.dataset.start) && source.currentTime < Number(word.dataset.end)));
    if (!source.paused) frame = requestAnimationFrame(update);
  };
  playback = () => {
    cancelAnimationFrame(frame);
    source.pause();
    $app.querySelectorAll(".arcade-word.spoken").forEach(word => word.classList.remove("spoken"));
  };
  source.play().then(update).catch(error => {
    if (active(ctx) && error.name !== "AbortError" && error.name !== "NotAllowedError") {
      note("音频暂时无法播放，请点击播放重试。");
    }
  });
}

function audioBuffer(ctx, url) {
  if (!ctx.cachedAudio.has(url)) {
    ctx.cachedAudio.set(url, fetch(url).then(response => {
      if (!response.ok) throw new Error("示范音频读取失败");
      return response.arrayBuffer();
    }).then(bytes => ctx.audioContext.decodeAudioData(bytes)).catch(error => {
      ctx.cachedAudio.delete(url);
      throw error;
    }));
  }
  return ctx.cachedAudio.get(url);
}

async function playTogether(ctx, tracks) {
  if (!active(ctx)) return;
  stopAudio();
  const revision = playbackRevision;
  const audioContext = ctx.audioContext || (ctx.audioContext = new AudioContext());
  await audioContext.resume();
  const buffers = await Promise.all(tracks.map(track => track.blob ?
    track.blob.arrayBuffer().then(bytes => audioContext.decodeAudioData(bytes)) : audioBuffer(ctx, track.url)));
  if (!active(ctx) || revision !== playbackRevision) return;
  $audio.pause();
  let startAt = audioContext.currentTime + 0.03;
  const sources = [];
  tracks.forEach(({ start = 0, end }, index) => {
    const buffer = buffers[index];
    const source = audioContext.createBufferSource();
    const duration = Math.min(end ?? buffer.duration, buffer.duration) - start;
    if (duration <= 0) return;
    source.buffer = buffer;
    source.connect(audioContext.destination);
    source.start(startAt, start, duration);
    startAt += duration;
    sources.push(source);
  });
  playback = () => sources.forEach(source => { source.stop(); source.disconnect(); });
}

function currentRow(ctx) {
  return isReview(ctx) ? ctx.cards?.[ctx.index] : ctx.data?.sentences[ctx.index];
}

function chosenVoice(ctx, row) {
  return ctx.voicePreference || ((row.voice || ctx.data?.voice) === "golden_self" ? "golden_self" : "demo");
}

async function playAlternate(ctx, row, voice) {
  stopAudio();
  ctx.altController?.abort();
  const request = ctx.altController = new AbortController();
  const url = isReview(ctx) ? itemPath(row.topic_id, row.item_id) : itemPath(ctx.tid, ctx.iid);
  const index = isReview(ctx) ? row.sentence_index : ctx.index;
  const fingerprint = row.source_fingerprint || ctx.data?.source_fingerprint;
  const destination = `${url}/arcade/sentences/${index}/voice/${voice}?source_fingerprint=${encodeURIComponent(fingerprint)}`;
  const revision = playbackRevision;
  note(voice === "golden_self" ? "正在准备母语分身…" : "正在准备母语示范…");
  try {
    const blob = await localAudioBlob(destination, request.signal);
    if (!active(ctx) || playbackRevision !== revision) return;
    const media = URL.createObjectURL(blob);
    const previous = ctx.altUrl;
    ctx.altUrl = media;
    play(ctx, media);
    if (previous) URL.revokeObjectURL(previous);
    note("");
  } catch (error) {
    if (!request.signal.aborted && active(ctx) && playbackRevision === revision) note(error.message);
  }
}

function reveal(ctx, sound = true) {
  const row = currentRow(ctx);
  if (!row) return;
  if (!ctx.revealed) {
    ctx.revealed = true;
    $app.querySelector(".arcade-recall").dataset.revealed = "true";
    $app.querySelector(".arcade-reveal").hidden = false;
    $app.querySelector(".arcade-grade").hidden = false;
  }
  if (!sound) return;
  const selected = chosenVoice(ctx, row);
  const source = (row.voice || ctx.data?.voice) === "golden_self" ? "golden_self" : "demo";
  if (selected !== source) {
    playAlternate(ctx, row, selected === "demo" ? "am_puck" : "golden_self");
    return;
  }
  ctx.altController?.abort();
  const url = row.audio_url || ctx.data?.audio_url;
  note(!url ? "这句暂无可播放的示范音频。" :
    row.audio.scope !== "sentence" ? "本句无独立时间位置，播放完整问答。" : "");
  if (row.audio.scope === "sentence" && typeof AudioContext !== "undefined") {
    const index = ctx.index;
    playTogether(ctx, [{ url, ...row.audio }]).catch(() => {
      if (active(ctx) && ctx.index === index) play(ctx, url, row.audio.start, row.audio.end);
    });
  } else play(ctx, url, row.audio.start, row.audio.end);
}

async function grade(ctx, rating) {
  if (!ctx.revealed || ctx.busy || activeCapture) return;
  ctx.busy = true;
  const row = currentRow(ctx);
  const review = isReview(ctx);
  const url = review ? `${itemPath(row.topic_id, row.item_id)}/arcade` : ctx.url;
  const payload = { sentence_index: review ? row.sentence_index : ctx.index,
    source_fingerprint: review ? row.source_fingerprint : ctx.data.source_fingerprint,
    rating, submission_id: ctx.submissionId ||= crypto.randomUUID() };
  try {
    await api("POST", `${url}/grade`, payload);
    if (!active(ctx)) return;
    stopAudio();
    ctx.altController?.abort();
    ctx.index += 1;
    ctx.revealed = false;
    ctx.submissionId = null;
    if (!review && ctx.index >= ctx.data.sentences.length) ctx.step = 3;
    if (ctx.kind === "home") { note(""); renderHomeCard(ctx); }
    else render(ctx);
  } catch (error) {
    if (active(ctx)) note(error.message);
  } finally { ctx.busy = false; }
}

async function capture(limit, onUpdate, onTake) {
  if (activeCapture) { activeCapture.stop(); return; }
  if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
    throw new Error("浏览器无法录音，打开本机网页并允许使用麦克风。");
  }
  let stopped = false;
  let recorder;
  const own = { stop() {
    stopped = true;
    if (recorder?.state === "recording") recorder.stop();
  } };
  activeCapture = own;
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    if (stopped) { stream.getTracks().forEach(track => track.stop()); activeCapture = null; return; }
    recorder = new MediaRecorder(stream);
    const parts = [];
    const start = performance.now();
    recorder.ondataavailable = event => { if (event.data.size) parts.push(event.data); };
    const elapsed = () => (performance.now() - start) / 1000;
    recorder.onstop = async () => {
      clearInterval(timer);
      stream.getTracks().forEach(track => track.stop());
      if (activeCapture === own) activeCapture = null;
      const blob = new Blob(parts, { type: recorder.mimeType || "audio/webm" });
      await onTake(blob, Math.min(limit, Math.max(.1, elapsed())));
    };
    recorder.start();
    const timer = setInterval(() => {
      if (elapsed() >= limit) own.stop();
      else onUpdate(Math.floor(elapsed()));
    }, 150);
    onUpdate(0);
  } catch (error) {
    stream?.getTracks().forEach(track => track.stop());
    if (activeCapture === own) activeCapture = null;
    throw error;
  }
}

async function upload(url, blob) {
  const response = await fetch(url, { method: "POST", headers: { "Content-Type": blob.type }, body: blob });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "录音保存失败");
  return data;
}

function takeKey(ctx) {
  return recordKey(`${ctx.tid}/${ctx.iid}/${ctx.data.source_fingerprint}/${ctx.step}/${ctx.index}`);
}

async function restoreTake(ctx) {
  const key = takeKey(ctx);
  const take = await TrainingBaseline.recoverRecording(key).catch(() => null);
  if (take && active(ctx) && key === takeKey(ctx)) showRetry(ctx, take, "发现一段尚未上传的录音。");
}

function showRetry(ctx, take, message) {
  note(message);
  const retry = document.getElementById("arcade-retry");
  if (!retry) return;
  retry.hidden = false;
  retry.onclick = () => storeTake(ctx, take);
}

async function storeTake(ctx, take) {
  if (ctx.busy) return;
  ctx.busy = true;
  const retry = document.getElementById("arcade-retry");
  if (retry) retry.hidden = true;
  const query = new URLSearchParams({ stage: take.stage, duration_sec: take.duration,
    upload_key: take.uploadKey, source_fingerprint: ctx.data.source_fingerprint });
  if (take.stage === "chunk") query.set("sentence_index", take.index);
  try {
    if (active(ctx)) note("保存录音，正在本机分析…");
    const saved = await upload(`${ctx.url}/recordings?${query}`, take.data);
    await TrainingBaseline.keepRecording(null, take.savePath).catch(() => {});
    if (!active(ctx)) return;
    if (take.stage === "final") {
      ctx.data.final = saved;
      ctx.step = 4;
      render(ctx);
      return;
    }
    const feedback = $app.querySelector(".arcade-feedback");
    const hits = saved.analysis?.matched_chunks || [];
    if (feedback) feedback.textContent = saved.analysis_error ? "录音已保存，语块分析暂不可用。" :
      hits.length ? `✓ 识别到 ${hits.join("、")}` : "未识别到目标语块。";
    note("");
  } catch (error) {
    if (active(ctx)) showRetry(ctx, take, error.message);
  } finally { ctx.busy = false; }
}

async function record(ctx) {
  if (ctx.busy) return;
  if (activeCapture) { activeCapture.stop(); return; }
  stopAudio();
  const control = $app.querySelector('[data-arcade="record"]');
  const label = control.innerHTML;
  const take = { savePath: takeKey(ctx), stage: ctx.step === 2 ? "chunk" : "final",
    index: ctx.index, uploadKey: crypto.randomUUID() };
  const row = take.stage === "chunk" ? currentRow(ctx) : null;
  if (row && ctx.data.audio_url) {
    ctx.audioContext ||= new AudioContext();
    ctx.audioContext.resume().then(() => audioBuffer(ctx, ctx.data.audio_url)).catch(() => {});
  }
  try {
    await capture(row ? 30 : 60, sec => {
      control.textContent = `结束录音 · ${fmtDur(sec)}`;
      control.classList.add("arcade-recording");
    }, async (blob, duration) => {
      control.innerHTML = label;
      control.classList.remove("arcade-recording");
      if (!blob.size || duration < .25) { if (active(ctx)) note("录音太短，请再说一次。"); return; }
      Object.assign(take, { data: blob, duration });
      if (row && active(ctx)) {
        reveal(ctx, false);
        const demo = { url: ctx.data.audio_url, start: row.audio.start, end: row.audio.end };
        playTogether(ctx, [demo, { blob }]).catch(() => {
          if (active(ctx)) note("暂时无法连播，可以重新听示范。");
        });
      }
      await TrainingBaseline.keepRecording(take).catch(() => {});
      await storeTake(ctx, take);
    });
  } catch (error) { note(`无法录音。${error.message}`); }
}

async function prepare(ctx) {
  try {
    await api("POST", `${itemPath(ctx.tid, ctx.iid)}/study/prepare`);
    if (!active(ctx)) return;
    ctx.data.status = "preparing";
    ctx.data.reason = "正在准备逐句材料…";
    render(ctx);
    pollMaterial(ctx);
  } catch (error) { if (active(ctx)) note(error.message); }
}

async function download(ctx) {
  if (ctx.busy) return;
  ctx.busy = true;
  try {
    note("正在拼接三段音频…");
    const res = await fetch(`${ctx.url}/export-evolution`, { method: "POST" });
    if (!res.ok) throw new Error((await res.json()).detail || "导出失败");
    const url = URL.createObjectURL(await res.blob());
    const a = document.createElement("a");
    a.href = url;
    a.download = "口语前后对比.mp3";
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
    if (active(ctx)) note("三合一音频已导出。");
  } catch (error) { if (active(ctx)) note(error.message); }
  finally { ctx.busy = false; }
}

function action(ctx, name) {
  if (!active(ctx)) return;
  if (name === "demo") play(ctx, ctx.data.audio_url);
  if (name === "prepare") prepare(ctx);
  if (name === "next") {
    stopAudio();
    ctx.repairs ||= ctx.data.sentences.filter(row => row.original_error);
    const next = (ctx.repairIndex ?? -1) + 1;
    if (next < ctx.repairs.length) {
      ctx.repairIndex = next;
      render(ctx);
      $app.querySelector(".arcade-repair h2").setAttribute("tabindex", "-1");
      $app.querySelector(".arcade-repair h2").focus({preventScroll: true});
      return;
    }
    ctx.repairIndex = null;
    ctx.step = 2;
    render(ctx);
    if (ctx.data.audio_url && typeof AudioContext !== "undefined") {
      ctx.audioContext ||= new AudioContext();
      ctx.audioContext.resume().then(() => audioBuffer(ctx, ctx.data.audio_url)).catch(() => {});
    }
  }
  if (name === "reveal") reveal(ctx);
  if (name === "good" || name === "again") grade(ctx, name);
  if (name === "record") record(ctx);
  if (name === "skip" && !activeCapture && !ctx.busy) { ctx.step = 4; render(ctx); }
  if (name === "blind" || name === "final") play(ctx, ctx.data[name].url);
  if (name === "answer") {
    const spans = ctx.data.alignment.mode === "estimated" ? [] : ctx.data.answer_spans;
    if (spans.length <= 1) play(ctx, ctx.data.audio_url, spans[0]?.start, spans[0]?.end);
    else playTogether(ctx, spans.map(span => ({ url: ctx.data.audio_url, ...span }))).catch(() =>
      play(ctx, ctx.data.audio_url, spans[0].start, spans.at(-1).end));
  }
  if (name === "export") download(ctx);
}

function reset() {
  activeCapture?.stop();
  stopAudio();
  if (session) {
    clearTimeout(session.poll);
    session.audioContext?.close().catch(() => {});
    session.altController?.abort();
    if (session.altUrl) URL.revokeObjectURL(session.altUrl);
    session = null;
  }
}

document.addEventListener("keydown", event => {
  const ctx = session;
  if (!ctx || !active(ctx) || event.repeat || event.ctrlKey || event.metaKey || event.altKey ||
     event.target.closest("input,textarea,select,[contenteditable]")) return;
  let next;
  if (ctx.step === 1 && ctx.data?.status === "ready" && ["Space", "Enter"].includes(event.code)) {
    next = ctx.repairIndex == null || document.getElementById("arcade-repair-answer").open
      ? "next" : "repair-answer";
  }
  if (ctx.step === 2 && (ctx.data || ctx.cards) && currentRow(ctx)) {
    if (event.code === "Space") next = "reveal";
    if (event.code === "Digit1" || event.code === "Numpad1") next = "good";
    if (event.code === "Digit2" || event.code === "Numpad2") next = "again";
    if (event.code === "KeyR" && !isReview(ctx)) { next = "record"; ctx.held = true; }
  }
  if (!next || (["Space", "Enter"].includes(event.code) && event.target.closest("button,a,summary"))) return;
  event.preventDefault();
  event.stopImmediatePropagation();
  if (next === "repair-answer") document.getElementById("arcade-repair-answer").open = true;
  else action(ctx, next);
}, true);

document.addEventListener("keyup", event => {
  if (event.code === "KeyR" && session?.held) { session.held = false; activeCapture?.stop(); }
});

function bindBlind(qid) {
  const control = document.getElementById("arcade-blind");
  const status = document.getElementById("arcade-blind-status");
  const input = document.getElementById("bank-answer-input");
  if (!control || !input) return;
  const key = recordKey(`blind:${qid}`);
  const intentKey = recordKey(`intent:${qid}`);
  const intent = document.getElementById("arcade-intent-input");
  const intentControl = document.getElementById("arcade-intent");
  const intentStatus = document.getElementById("arcade-intent-status");
  const submit = document.getElementById("bank-answer-submit");
  try { intent.value = sessionStorage.getItem(intentKey) || ""; } catch (_) {}
  intent.addEventListener("input", () => {
    try { sessionStorage.setItem(intentKey, intent.value); } catch (_) {}
  });
  if (stagedBlind.has(qid)) status.textContent = "英文盲答原声已保留。可编辑文字或重录。";
  const run = async take => {
    control.disabled = true;
    intentControl.disabled = true;
    submit.disabled = true;
    status.textContent = "正在本机转写盲答…";
    try {
      const saved = await upload(`/api/arcade/transcribe-blind?language=en&duration_sec=${take.duration}`, take.data);
      if (!control.isConnected) return;
      stagedBlind.set(qid, saved.blind_token);
      await TrainingBaseline.keepRecording(null, key).catch(() => {});
      if (!saved.transcript) {
        status.textContent = "录音已保留。没有识别到文字，可以输入回答后提交。";
        return;
      }
      input.value = saved.transcript;
      input.dispatchEvent(new Event("input", { bubbles: true }));
      status.textContent = "原声已保留。可编辑文字、重录或补充中文意图。";
      control.textContent = "重录英文盲答";
    } catch (error) {
      if (!control.isConnected) return;
      status.textContent = `${error.message}。录音保留，可重试转写。`;
      control.textContent = "重试转写";
      control.onclick = () => run(take);
    } finally {
      control.disabled = false;
      intentControl.disabled = false;
      if (submit.textContent === "一键生成并直接开练" || submit.textContent === "提交作答") submit.disabled = false;
    }
  };
  control.onclick = async () => {
    if (activeCapture) { activeCapture.stop(); return; }
    intentControl.disabled = true;
    submit.disabled = true;
    try {
      await capture(180, sec => { control.textContent = `结束并转写 · ${fmtDur(sec)}`; submit.disabled = true; },
        async (blob, duration) => {
          control.textContent = "录制英文盲答";
          if (!blob.size || duration < .25) {
            status.textContent = "录音太短，请再说一次。";
            submit.disabled = intentControl.disabled = false;
            return;
          }
          const take = { data: blob, duration, savePath: key };
          await TrainingBaseline.keepRecording(take).catch(() => {});
          if (control.isConnected) await run(take);
        });
    } catch (error) {
      status.textContent = `无法录音。${error.message}`;
      submit.disabled = intentControl.disabled = false;
    }
  };
  intentControl.onclick = async () => {
    if (activeCapture) { activeCapture.stop(); return; }
    const label = intentControl.textContent;
    control.disabled = submit.disabled = true;
    const restore = () => {
      control.disabled = submit.disabled = intentControl.disabled = false;
      intentControl.textContent = label;
    };
    try {
      await capture(180, sec => { intentControl.textContent = `结束并转写 · ${fmtDur(sec)}`; },
        async (blob, duration) => {
          if (!intent.isConnected) return;
          if (!blob.size || duration < .25) {
            intentStatus.textContent = "录音太短，请再说一次。";
            restore();
            return;
          }
          intentControl.disabled = true;
          intentStatus.textContent = "正在本机转写中文…";
          try {
            const saved = await upload(`/api/arcade/transcribe-intent?duration_sec=${duration}`, blob);
            if (!intent.isConnected) return;
            if (saved.transcript) {
              intent.value = [intent.value.trim(), saved.transcript].filter(Boolean).join("\n");
              intent.dispatchEvent(new Event("input", {bubbles: true}));
            }
            intentStatus.textContent = saved.transcript ? "仅保留转写文字，可继续编辑。"
              : "没有识别到中文，可以重录或输入。";
          } catch (error) {
            intentStatus.textContent = error.message;
          } finally { restore(); }
        });
    } catch (error) {
      intentStatus.textContent = `无法录音。${error.message}`;
      restore();
    }
  };
  const start = control.onclick;
  TrainingBaseline.recoverRecording(key).then(take => {
    if (!take || !control.isConnected || control.onclick !== start || activeCapture) return;
    control.textContent = "转写上次盲答";
    control.onclick = () => run(take);
  }).catch(() => {});
}

window.ArcadeUI = { enabled, home, open, blitz, reset, bindBlind, voiceNames,
  blindToken: qid => stagedBlind.get(qid),
  clearBlind(qid, submittedIntent) {
    stagedBlind.delete(qid);
    try {
      const key = recordKey(`intent:${qid}`);
      if (submittedIntent === undefined || sessionStorage.getItem(key) === submittedIntent)
        sessionStorage.removeItem(key);
    } catch (_) {}
  } };
