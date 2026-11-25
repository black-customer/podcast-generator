/* 桌面三步口语练习与闪电复习。 */

let session = null;
let activeCapture = null;
let playback = null;
let playbackRevision = 0;
const stagedBlind = new Map();
const voiceNames = { golden_self: "我的母语分身", af_bella: "Bella", am_liam: "Liam",
  am_michael: "Michael", am_puck: "Puck" };

const enabled = () => !MobileRuntime.native && !PackState.active;
const itemPath = (tid, iid) => `/api/topics/${encodeURIComponent(tid)}/items/${encodeURIComponent(iid)}`;
const button = (action, label, style = "") =>
  `<button type="button" class="study-button ${style}" data-arcade="${action}">${label}</button>`;
const chunk = text => text ? `<mark class="arcade-chunk">${esc(text)}</mark>` : "";
const hotkey = key => `<kbd>${key}</kbd>`;
const recordKey = key => `arcade:${key}`;
const active = ctx => session === ctx && !viewStale(ctx.token);
const voiceLabel = data => voiceNames[data.voice] || "示范回答";

function stageNav(step) {
  return `<ol class="arcade-steps" aria-label="练习步骤">${["听懂与抓重点", "逐句开口", "脱稿回答"].map(
    (label, index) => `<li ${step === index + 1 ? 'aria-current="step"' : ""}${step > index + 1 ?
      ' class="done"' : ""}><span>${index + 1}</span>${label}</li>`).join("")}</ol>`;
}

async function home(token) {
  ExperienceUI.loading("今日练习");
  const [due, board] = await Promise.allSettled([api("GET", "/api/arcade/blitz?summary=true"),
    api("GET", "/api/arcade/error-board")]);
  if (viewStale(token)) return;
  const count = due.value?.due_count;
  const diagnoses = board.value?.top.slice(0, 3) || [];
  $app.innerHTML = `<main class="arcade-home" aria-labelledby="arcade-home-title">
    <header class="arcade-home-head"><h1 id="arcade-home-title">今日练习</h1>
      <p>练一道新题，或把已经学过的句子再说一遍。</p></header>
    <div class="arcade-home-grid">
      <div class="arcade-home-actions">
        <section class="arcade-blitz-card" aria-labelledby="blitz-card-title">
          <div class="arcade-card-meta"><span>间隔复习</span><span>${count == null ? "读取失败" : `今日到期 ${esc(count)} 句`}</span></div>
          <h2 id="blitz-card-title">3 分钟闪电刷句</h2>
          <p>看中文，开口说，再听示范校准。</p>
          <a class="study-button primary" href="#/blitz">${count > 0 ? "开始刷句" : "查看复习"} <span aria-hidden="true">→</span></a>
        </section>
        <section class="arcade-new"><div><h2>练一道新题</h2><p>用自己的经历回答，练到能脱稿说出来。</p></div>
          <a class="study-button" href="#/practice">去题库选题 <span aria-hidden="true">→</span></a></section>
      </div>
      <section class="arcade-board" aria-labelledby="arcade-board-title">
        <h2 id="arcade-board-title">我的口语病历榜</h2>
        <p>按原话中有证据的语法与搭配问题统计。</p>
        ${diagnoses.length ? `<ol>${diagnoses.map(row => `<li><strong>${esc(row.label)}</strong>
          <span>${esc(row.count)} 次</span></li>`).join("")}</ol>` :
          `<p class="arcade-board-empty">${board.status === "rejected" ? "病历榜读取失败，刷新可重试。" : "还没有可归类的原话问题。"}</p>`}
        <button class="study-button" id="arcade-copy-prompt" type="button" ${board.value?.prompt ? "" : "disabled"}>复制今日 AI 陪练指令</button>
        ${board.value?.today_chunks.length ? `<div class="arcade-chunks">${board.value.today_chunks.map(chunk).join("")}</div>` : ""}
      </section>
    </div>
    <footer class="arcade-home-footer"><a href="#/topics">我的语料</a><a href="#/legacy-today">历史训练与复验</a></footer>
  </main>`;
  document.getElementById("arcade-copy-prompt").onclick = () => copyText(board.value.prompt);
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
  const errors = d.sentences.filter(row => row.original_error);
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
      ${errors.length ? `<h3>原话中可以改的地方</h3>${errors.map(({original_error: error}) =>
        `<div class="arcade-error"><p><mark>${esc(error.quote)}</mark></p><p>${esc(error.issue)}</p>
        <strong>${esc(error.correction)}</strong></div>`).join("")}` : ""}
    </section></div>
    <div class="arcade-controls arcade-proceed">${button("next", `开始逐句开口 ${hotkey("Space")}`, "primary")}</div>`;
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
  const review = ctx.kind === "blitz";
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
    <div class="arcade-reveal" ${ctx.revealed ? "" : "hidden"}><p>${highlight(row.en, row.key_chunk)}</p></div>
    <div class="arcade-controls">
      ${button("reveal", `揭晓并听示范 ${hotkey("Space")}`, "primary")}
      ${review ? "" : button("record", `录音对比 ${hotkey("R")}`)}
    </div>
    <div class="arcade-controls arcade-grade" ${ctx.revealed ? "" : "hidden"}>
      ${button("good", `${hotkey("1")} 顺畅`)}${button("again", `${hotkey("2")} 卡壳`)}
    </div><p class="arcade-feedback" role="status"></p>
    ${ctx.revealed && row.audio.scope !== "sentence" ? '<p class="arcade-muted">这句缺少实测时间位置，将播放完整问答。</p>' : ""}
  </section>`;
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
    ${phrases.length ? `<div class="arcade-chunks">${phrases.map(chunk).join("")}</div>` : ""}
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
    <a class="study-button" href="#/today">返回首页</a></div>
  </section>`;
}

function render(ctx) {
  if (!active(ctx)) return;
  const review = ctx.kind === "blitz";
  let body;
  if (ctx.step === 1) body = reference(ctx);
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
  const root = $app.querySelector(".arcade-workspace");
  root.onclick = event => {
    const word = event.target.closest("[data-start]");
    if (word) play(ctx, ctx.data.audio_url, Number(word.dataset.start));
    const control = event.target.closest("[data-arcade]");
    if (control) action(ctx, control.dataset.arcade);
  };
  if (!review && ctx.step >= 2 && ctx.step <= 3) restoreTake(ctx);
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
  return ctx.kind === "blitz" ? ctx.cards[ctx.index] : ctx.data.sentences[ctx.index];
}

function reveal(ctx, sound = true) {
  const row = currentRow(ctx);
  if (!row) return;
  if (!ctx.revealed) {
    ctx.revealed = true;
    $app.querySelector(".arcade-recall").dataset.revealed = "true";
    $app.querySelector(".arcade-reveal").hidden = false;
    $app.querySelector(".arcade-grade").hidden = false;
    if (sound && row.audio.scope !== "sentence") note("本句无独立时间位置，播放完整问答。");
  }
  if (!sound) return;
  const url = row.audio_url || ctx.data.audio_url;
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
  const review = ctx.kind === "blitz";
  const url = review ? `${itemPath(row.topic_id, row.item_id)}/arcade` : ctx.url;
  const payload = { sentence_index: review ? row.sentence_index : ctx.index,
    source_fingerprint: review ? row.source_fingerprint : ctx.data.source_fingerprint,
    rating, submission_id: ctx.submissionId ||= crypto.randomUUID() };
  try {
    await api("POST", `${url}/grade`, payload);
    if (!active(ctx)) return;
    stopAudio();
    ctx.index += 1;
    ctx.revealed = false;
    ctx.submissionId = null;
    if (!review && ctx.index >= ctx.data.sentences.length) ctx.step = 3;
    render(ctx);
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
    session = null;
  }
}

document.addEventListener("keydown", event => {
  const ctx = session;
  if (!ctx || !active(ctx) || event.repeat || event.ctrlKey || event.metaKey || event.altKey ||
     event.target.closest("input,textarea,select,[contenteditable]")) return;
  let next;
  if (ctx.step === 1 && ctx.data?.status === "ready" && ["Space", "Enter"].includes(event.code)) next = "next";
  if (ctx.step === 2 && (ctx.data || ctx.cards) && currentRow(ctx)) {
    if (event.code === "Space") next = "reveal";
    if (event.code === "Digit1" || event.code === "Numpad1") next = "good";
    if (event.code === "Digit2" || event.code === "Numpad2") next = "again";
    if (event.code === "KeyR" && ctx.kind !== "blitz") { next = "record"; ctx.held = true; }
  }
  if (!next || (["Space", "Enter"].includes(event.code) && event.target.closest("button,a"))) return;
  event.preventDefault();
  event.stopImmediatePropagation();
  action(ctx, next);
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
  const submit = document.getElementById("bank-answer-submit");
  const run = async take => {
    control.disabled = true;
    submit.disabled = true;
    status.textContent = "正在本机转写盲答…";
    try {
      const saved = await upload(`/api/arcade/transcribe-blind?duration_sec=${take.duration}`, take.data);
      if (!control.isConnected) return;
      stagedBlind.set(qid, saved.blind_token);
      await TrainingBaseline.keepRecording(null, key).catch(() => {});
      if (!saved.transcript) {
        status.textContent = "录音已保留。没有识别到文字，可以输入回答后提交。";
        return;
      }
      input.value = saved.transcript;
      input.dispatchEvent(new Event("input", { bubbles: true }));
      submit.disabled = false;
      submit.click();
    } catch (error) {
      if (!control.isConnected) return;
      status.textContent = `${error.message}。录音保留，可重试转写。`;
      control.textContent = "重试转写";
      control.onclick = () => run(take);
    } finally {
      control.disabled = false;
      if (submit.textContent === "一键生成并直接开练" || submit.textContent === "提交作答") submit.disabled = false;
    }
  };
  control.onclick = async () => {
    if (activeCapture) { activeCapture.stop(); return; }
    try {
      await capture(180, sec => { control.textContent = `结束并转写 · ${fmtDur(sec)}`; submit.disabled = true; },
        async (blob, duration) => {
          control.textContent = "直接开口盲答";
          if (!blob.size || duration < .25) { status.textContent = "录音太短，请再说一次。"; submit.disabled = false; return; }
          const take = { data: blob, duration, savePath: key };
          await TrainingBaseline.keepRecording(take).catch(() => {});
          if (control.isConnected) await run(take);
        });
    } catch (error) { status.textContent = `无法录音。${error.message}`; }
  };
  const start = control.onclick;
  TrainingBaseline.recoverRecording(key).then(take => {
    if (!take || !control.isConnected || control.onclick !== start || activeCapture) return;
    control.textContent = "转写上次盲答";
    control.onclick = () => run(take);
  }).catch(() => {});
}

window.ArcadeUI = { enabled, home, open, blitz, reset, bindBlind, voiceNames,
  blindToken: qid => stagedBlind.get(qid), clearBlind: qid => stagedBlind.delete(qid) };
