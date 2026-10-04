/* L04：今日练习与困难句口答。复用服务端私有进度和原生录音能力。 */
"use strict";

const OralReviewUI = (() => {
  const state = { session: null, blob: null, blobUrl: "", recorder: null, stream: null,
    chunks: [], recordStart: 0, duration: 0, hintTimer: null, playback: null,
    currentHash: "", pendingSubmissionId: null, pendingSubmissionRating: null,
    pendingActions: {}, historyRevision: 0 };

  const sidPath = suffix => `/api/study/review-sessions/${encodeURIComponent(state.session.id)}${suffix}`;
  const newId = () => crypto.randomUUID();
  const ratingNames = { independent: "独立说出", needs_hint: "需要提示", unable: "暂时说不出" };

  function clearMedia() {
    clearTimeout(state.hintTimer);
    if (state.recorder?.state === "recording") {
      state.recorder.onstop = null;
      state.recorder.stop();
    }
    state.stream?.getTracks().forEach(track => track.stop());
    state.stream = null;
    state.playback?.pause();
    state.playback = null;
  }

  function discardBlob() {
    if (state.blobUrl) URL.revokeObjectURL(state.blobUrl);
    state.blobUrl = "";
    state.blob = null;
  }

  function leave(nextHash) {
    if (state.session && nextHash === state.currentHash) return false;
    if ((state.blob || state.recorder?.state === "recording")
        && !confirm("当前录音还没有保存。离开后会丢失这段录音，是否离开？")) {
      if (location.hash !== state.currentHash) location.hash = state.currentHash;
      return false;
    }
    clearMedia();
    discardBlob();
    state.session = null;
    state.pendingSubmissionId = null;
    state.pendingSubmissionRating = null;
    state.pendingActions = {};
    return true;
  }

  window.addEventListener("beforeunload", event => {
    if (state.blob || state.recorder?.state === "recording") {
      event.preventDefault(); event.returnValue = "";
    }
  });

  function safeDesktop() {
    if (typeof MobileRuntime !== "undefined" && MobileRuntime.native) return true;
    if ((typeof PackState !== "undefined" && PackState.active)
      || matchMedia("(max-width: 860px)").matches) {
      $app.innerHTML = `<section class="study-page"><h1>今日口答练习在电脑端使用</h1>
        <p class="study-muted">手机仍可导入、浏览和收听语料。</p>
        <a class="study-button" href="#/practice">返回开始练习</a></section>`;
      return false;
    }
    return true;
  }

  async function today(token) {
    state.currentHash = "#/today";
    if (!safeDesktop()) return;
    ExperienceUI.loading("今日练习");
    try {
      const data = await api("GET", "/api/study/today");
      if (viewStale(token)) return;
      const pending = data.continue_learning || [];
      $app.innerHTML = `<div class="today-page">
        <header class="today-head"><div><h1>今天练什么</h1>
          <p>先接着上次的题，再口答到期的困难句。</p></div>
          <a href="#/study-history" class="study-button">学习记录</a></header>
        <section class="today-section ${pending.length ? "" : "is-empty"}"><h2>继续学习</h2>
          ${pending.length ? `<a class="today-continue" href="#/learn/${encodeURIComponent(pending[0].topic_id)}/${encodeURIComponent(pending[0].item_id)}">
            <span>${pending[0].last_activity_at ? `上次练习 ${esc(pending[0].last_activity_at.replace("T", " "))}` : "历史未完成学习"}</span>
            <strong>${esc(pending[0].question)}</strong><b class="today-main-action">继续本题 →</b></a>`
            : `<p class="today-empty">暂无未完成的学习。选一道新题，把你的想法练成英文。</p>`}</section>
        <section class="today-section"><div class="today-section-head"><h2>到期的困难句</h2>
          <span>${data.due_count} 句待口答</span></div>
          ${data.active_session_id ? `<a class="study-button primary" href="#/oral-review/${encodeURIComponent(data.active_session_id)}">继续本轮口答</a>` :
            data.due_count ? `<button type="button" class="study-button ${pending.length ? "" : "primary"}" id="today-start">开始本轮 · ${Math.min(data.due_count, 10)} 句</button>` :
            `<p class="today-empty">${data.has_learning_records
              ? "今天没有到期的困难句。学过的句子会在之后的日期再次出现。"
              : "尚无学习记录。先选一道题，完成学习后再安排困难句口答。"}</p>`}
          ${data.due_preview.length ? `<div class="today-due-list">${data.due_preview.map(row =>
            `<div><strong>${esc(row.zh)}</strong><span>${esc(row.source)}</span></div>`).join("")}</div>` : ""}
          ${data.due_count > 10 ? `<p class="study-muted">本轮完成后还可继续练余下 ${data.due_count - 10} 句。</p>` : ""}
          ${data.needs_material_count ? `<p class="today-note">${data.needs_material_count} 句的日程需要复核材料。</p>
            <div class="today-due-list">${(data.needs_material || []).map(row => `<div>
              <span>${esc(row.source)}</span>${row.source_exists
                ? row.material_ready
                  ? `<a class="study-button" href="#/review/${encodeURIComponent(row.topic_id)}/${encodeURIComponent(row.item_id)}/${row.sentence_index}">复核新版并重新加入</a>`
                  : `<a class="study-button" href="#/learn/${encodeURIComponent(row.topic_id)}/${encodeURIComponent(row.item_id)}">补齐材料</a>`
                : `<span>条目已删除，历史仍保留</span>`}</div>`).join("")}</div>` : ""}
        </section>
        <section class="today-section"><h2>开始新题</h2><p class="study-muted">从一道雅思题出发，说出你自己的想法。</p>
          <a class="study-button ${!pending.length && !data.due_count && !data.active_session_id ? "primary" : ""}" href="#/practice">打开题库</a></section>
      </div>`;
      document.getElementById("today-start")?.addEventListener("click", async event => {
        const button = event.currentTarget;
        button.disabled = true;
        button.textContent = "正在准备本轮…";
        try {
          const session = await api("POST", "/api/study/review-sessions", {});
          if (viewStale(token)) return;
          location.hash = `#/oral-review/${encodeURIComponent(session.id)}`;
        } catch (err) {
          if (viewStale(token)) return;
          toast(`无法开始本轮练习：${err.message}`); button.disabled = false;
          button.textContent = `开始本轮 · ${Math.min(data.due_count, 10)} 句`;
        }
      });
    } catch (err) {
      if (!viewStale(token)) $app.innerHTML = `<div class="study-page"><h1>今日练习加载失败</h1>
        <p>${esc(err.message)}</p><button type="button" class="study-button" id="today-retry">重试</button></div>`;
      document.getElementById("today-retry")?.addEventListener("click", () => today(token));
    }
  }

  async function sessionView(sessionId, token) {
    state.currentHash = `#/oral-review/${encodeURIComponent(sessionId)}`;
    if (!safeDesktop()) return;
    ExperienceUI.loading("困难句口答");
    try {
      const session = await api("GET", `/api/study/review-sessions/${encodeURIComponent(sessionId)}`);
      if (viewStale(token)) return;
      state.session = session;
      renderSession();
    } catch (err) {
      if (!viewStale(token)) $app.innerHTML = `<div class="study-page"><h1>无法打开这轮练习</h1>
        <p>${esc(err.message)}</p><a href="#/today">返回今日练习</a></div>`;
    }
  }

  function renderSession() {
    clearMedia();
    const session = state.session;
    $app.scrollTop = 0;
    if (session.state === "completed") {
      $app.innerHTML = `<div class="study-page oral-page"><a href="#/today" class="study-breadcrumb">今日练习</a>
        <h1>本轮口答完成</h1><p class="study-muted">只列本轮实际练过的句子；跳过的句子仍保留原到期日期。</p>
        <div class="study-review-list">${session.results.map(row => `<div class="study-review-result">
          <strong>${esc(row.zh)}</strong><p>${row.outcome === "skipped" ? "本轮跳过" :
            `${ratingNames[row.outcome]} · ${row.recorded ? "已保存录音" : "未录音／本人自评"} · 下次 ${esc(row.next_due_date)}`}</p>
          </div>`).join("")}</div>
        <div class="study-actions"><a class="study-button primary" href="#/today">返回今日练习</a>
          <a class="study-button" href="#/study-history">查看学习记录</a></div></div>`;
      return;
    }
    const card = session.current_card;
    const unavailable = card.availability !== "ready";
    $app.innerHTML = `<div class="study-page oral-page">
      <div class="study-breadcrumb"><a href="#/today">今日练习</a><span>/</span>困难句口答</div>
      <div class="study-counter">第 ${session.current_index + 1} / ${session.card_ids.length} 句</div>
      <div class="study-question-block"><span>来源题目</span><h1>${esc(card.question)}</h1></div>
      <section class="study-task"><p class="study-counter">先看中文，自己说英文</p>
        <h2 class="study-chinese">${esc(card.zh)}</h2>
        ${unavailable ? `<p class="study-feedback">${card.availability === "paused"
          ? "这句日程已暂停，可先跳过本句，或到句子详情恢复日程。"
          : "材料已变化或条目已删除。这句暂时无法口答，请跳过后补齐材料。"}</p>` :
          session.phase === "prompt" ? promptMarkup(session) : compareMarkup(session)}
        <div class="study-actions auxiliary-actions"><button type="button" data-oral="skip">本轮跳过</button>
          <a class="study-button" href="#/today">返回今日练习</a></div>
        <p id="oral-error" class="study-feedback" role="alert"></p>
      </section></div>`;
    $app.querySelectorAll("[data-oral]").forEach(button => button.onclick = onAction);
    bindAudioCompetition();
    ExperienceUI.recordingControls(document.getElementById("oral-recorder"), "ready");
  }

  function promptMarkup(session) {
    return `<div class="oral-prompt">
      <div class="study-recorder" id="oral-recorder"><p id="oral-rec-status" class="study-rec-status" role="status">录下你现在的回答；也可以直接口答并自评。</p>
        <div class="study-actions"><button type="button" data-oral="record-start">开始录音</button>
          <button type="button" data-oral="record-stop" disabled>停止</button>
          <button type="button" data-oral="record-save" disabled class="primary">保存录音并查看示范</button></div>
        <audio id="oral-preview" controls hidden></audio>
        <a id="oral-download" download="oral-review.webm" hidden>下载当前录音</a></div>
      <div class="study-actions auxiliary-actions"><button type="button" data-oral="no-record">我已口答，不录音</button>
        <button type="button" data-oral="hint">短暂看示范</button>
        <button type="button" data-oral="reveal">先查看示范</button></div>
      <div id="oral-hint" class="study-hint" hidden></div>
      ${session.hint_used ? `<p class="study-muted">本句已使用提示，自评会如实记录。</p>` : ""}
    </div>`;
  }

  function compareMarkup(session) {
    const card = session.current_card;
    const canIndependent = session.responded && !session.hint_used;
    return `<div class="study-explanation oral-compare">
      <div class="study-counter">现在核对示范并由你自评</div>
      <p class="study-answer">${esc(card.en)}</p>
      <div class="study-explain-grid"><div><h3>这句话怎么组织</h3><p>${esc(card.explanation)}</p></div>
        <div><h3>表达选择</h3><p>${esc(card.usage)}</p></div></div>
      <div class="study-actions"><button type="button" data-oral="play-reference">听示范</button>
        ${session.recording_id ? `<audio controls preload="none" src="${recordingUrl(card, session.recording_id)}" aria-label="回听本次口答"></audio>` :
          `<span class="study-muted">未录音／本人自评</span>`}</div>
      ${session.recording_id ? `<button type="button" class="study-button" data-oral="no-record">改为无录音自评（保留录音文件）</button>` : ""}
      <p class="study-muted">意思完整、英文自然即可选“独立说出”；合理的其他表达也成立。</p>
      <div class="study-actions oral-ratings"><button type="button" data-oral="independent" ${canIndependent ? "" : "disabled"}>独立说出</button>
        <button type="button" data-oral="needs_hint" ${session.responded ? "" : "disabled"}>需要提示</button>
        <button type="button" data-oral="unable">暂时说不出</button></div>
      ${!canIndependent ? `<p class="study-muted">本次看过提示或尚未口答，不能标为独立说出。</p>` : ""}
    </div>`;
  }

  function recordingUrl(card, id) {
    if (typeof MobileRuntime !== "undefined" && MobileRuntime.native) return esc(MobileRuntime.fileUrl(id));
    return `/api/topics/${encodeURIComponent(card.topic_id)}/items/${encodeURIComponent(card.item_id)}/study/recordings/${encodeURIComponent(id)}`;
  }

  async function actionRequest(action) {
    const key = `${state.session.id}:${state.session.current_index}:${action}`;
    const actionId = state.pendingActions[key] || newId();
    state.pendingActions[key] = actionId;
    const response = await api("POST", sidPath("/actions"), { action, action_id: actionId });
    delete state.pendingActions[key];
    return response;
  }

  async function onAction(event) {
    const button = event.currentTarget;
    const action = button.dataset.oral;
    const sessionId = state.session?.id;
    const viewHash = state.currentHash;
    const isCurrent = () => state.session?.id === sessionId && state.currentHash === viewHash;
    if (button.disabled) return;
    button.disabled = true;
    try {
      if (state.recorder?.state === "recording" && action !== "record-stop") {
        throw new Error("请先停止当前录音");
      }
      if (action === "record-start") { button.disabled = await recordStart(); return; }
      if (action === "record-stop") { state.recorder?.stop(); return; }
      if (action === "record-save") { await saveRecording(); return; }
      if (action === "play-reference") { await playReference(); button.disabled = false; return; }
      if (["independent", "needs_hint", "unable"].includes(action)) {
        if (state.pendingSubmissionRating && state.pendingSubmissionRating !== action) {
          throw new Error("上次提交结果尚未确认，请重试刚才的自评结果或刷新恢复");
        }
        const submissionId = state.pendingSubmissionId || newId();
        state.pendingSubmissionId = submissionId;
        state.pendingSubmissionRating = action;
        await api("POST", `/api/study/review-sessions/${encodeURIComponent(sessionId)}/attempts`,
          { rating: action, submission_id: submissionId });
        if (!isCurrent()) return;
        state.pendingSubmissionId = null;
        state.pendingSubmissionRating = null;
        const restored = await api("GET", `/api/study/review-sessions/${encodeURIComponent(sessionId)}`);
        if (!isCurrent()) return;
        state.session = restored;
        renderSession();
        return;
      }
      if (action === "no-record" && state.blob
          && !confirm("当前录音尚未保存，改为无录音自评会丢失它。继续？")) {
        button.disabled = false; return;
      }
      if (["skip", "reveal"].includes(action) && state.blob
          && !confirm("当前录音尚未保存，继续会丢失它。是否继续？")) {
        button.disabled = false; return;
      }
      const response = await actionRequest({ "no-record": "answered_without_recording",
        reveal: "show_answer", skip: "skip", hint: "hint" }[action]);
      if (!isCurrent()) return;
      if (["no-record", "skip", "reveal"].includes(action)) discardBlob();
      if (action === "hint") {
        state.session = response;
        const box = document.getElementById("oral-hint");
        box.textContent = response.hint_text;
        box.hidden = false;
        const seconds = Number(localStorage.getItem("study-hint-seconds") || 5);
        clearTimeout(state.hintTimer);
        state.hintTimer = setTimeout(() => {
          if (matchMedia("(prefers-reduced-motion: reduce)").matches) box.hidden = true;
          else { box.classList.add("fading"); setTimeout(() => {
            box.hidden = true; box.classList.remove("fading");
          }, 250); }
        }, [3, 5, 8].includes(seconds) ? seconds * 1000 : 5000);
        button.disabled = false;
        return;
      }
      state.session = response;
      renderSession();
    } catch (err) {
      if (!isCurrent()) return;
      const output = document.getElementById("oral-error");
      if (output) output.textContent = action === "record-save"
        ? `录音保存失败：${err.message}。录音仍在本页，可重试保存或下载当前录音。`
        : `操作失败：${err.message}。可以重试。`;
      button.disabled = false;
    }
  }

  async function recordStart() {
    const sessionId = state.session.id;
    const status = document.getElementById("oral-rec-status");
    try {
      if (state.blob && !confirm("当前录音尚未保存。重新录制会丢失它，继续？")) {
        document.querySelector("[data-oral='record-start']").disabled = false;
        return false;
      }
      discardBlob();
      if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) throw new Error("当前浏览器没有录音能力");
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (state.session?.id !== sessionId) {
        stream.getTracks().forEach(track => track.stop());
        return false;
      }
      state.stream = stream;
      const mime = ["audio/webm", "audio/ogg", "audio/mp4"].find(type => MediaRecorder.isTypeSupported(type));
      state.recorder = mime ? new MediaRecorder(state.stream, { mimeType: mime }) : new MediaRecorder(state.stream);
      state.chunks = [];
      state.recorder.ondataavailable = event => { if (event.data.size) state.chunks.push(event.data); };
      state.recorder.onstop = () => {
        state.duration = (performance.now() - state.recordStart) / 1000;
        state.blob = new Blob(state.chunks, { type: state.recorder.mimeType || mime || "audio/webm" });
        if (state.chunks[0]?.nativePath) state.blob.nativePath = state.chunks[0].nativePath;
        if (state.blobUrl) URL.revokeObjectURL(state.blobUrl);
        state.blobUrl = URL.createObjectURL(state.blob);
        const preview = document.getElementById("oral-preview");
        if (preview) { preview.src = state.blobUrl; preview.hidden = false; }
        const download = document.getElementById("oral-download");
        if (download) { download.href = state.blobUrl; download.download = `oral-review.${ExperienceUI.recordingExtension(state.blob.type)}`; download.hidden = false; }
        document.querySelector("[data-oral='record-save']").disabled = false;
        document.querySelector("[data-oral='record-start']").disabled = false;
        document.querySelector("[data-oral='record-stop']").disabled = true;
        ExperienceUI.recordingControls(document.getElementById("oral-recorder"), "stopped");
        status.textContent = "录音已停止。可回听、保存，或下载后离开。";
        state.stream?.getTracks().forEach(track => track.stop());
        state.stream = null;
      };
      state.recordStart = performance.now();
      state.recorder.start();
      document.querySelector("[data-oral='record-stop']").disabled = false;
      status.textContent = "正在录音…";
      ExperienceUI.recordingControls(document.getElementById("oral-recorder"), "recording");
      return true;
    } catch (err) {
      state.stream?.getTracks().forEach(track => track.stop());
      state.stream = null;
      if (state.session?.id !== sessionId) return false;
      status.textContent = `无法使用麦克风：${err.message}。仍可口答并选择“不录音”。`;
      document.querySelector("[data-oral='record-start']").disabled = false;
      return false;
    }
  }

  async function saveRecording() {
    if (!state.blob) throw new Error("请先录音并停止");
    const sessionId = state.session.id;
    const response = await fetch(sidPath(`/recording?duration_sec=${state.duration.toFixed(2)}`), {
      method: "POST", body: state.blob, headers: { "Content-Type": state.blob.type },
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.detail || `HTTP ${response.status}`);
    }
    const restored = (await response.json()).session;
    if (state.session?.id !== sessionId) return;
    state.session = restored;
    discardBlob();
    renderSession();
  }

  async function playReference() {
    const sessionId = state.session.id;
    const card = state.session.current_card;
    const span = await api("GET", `/api/topics/${encodeURIComponent(card.topic_id)}/items/${encodeURIComponent(card.item_id)}/study/audio/${card.sentence_index}?card_id=${encodeURIComponent(card.id)}`);
    if (state.session?.id !== sessionId) return;
    if (MobileRuntime.native && !span.url) throw new Error("示范音频尚未完成，文字学习仍可继续。");
    state.playback?.pause();
    $audio.pause();
    $app.querySelectorAll("audio").forEach(audio => audio.pause());
    const path = `/api/topics/${encodeURIComponent(card.topic_id)}/items/${encodeURIComponent(card.item_id)}/audio/podcast`;
    const audio = new Audio(MobileRuntime.native && span.url ? MobileRuntime.fileUrl(span.url) : mediaUrl(path) || path);
    state.playback = audio;
    audio.onloadedmetadata = () => { audio.currentTime = span.start || 0; audio.play().catch(() => {}); };
    if (span.end != null) audio.ontimeupdate = () => { if (audio.currentTime >= span.end) audio.pause(); };
    toast(span.reason);
  }

  function bindAudioCompetition() {
    $app.querySelectorAll("audio").forEach(el => el.addEventListener("play", () => {
      $audio.pause();
      state.playback?.pause();
      $app.querySelectorAll("audio").forEach(other => { if (other !== el) other.pause(); });
    }));
  }

  async function history(token, dayFilter = "", sourceFilter = "") {
    const revision = ++state.historyRevision;
    state.currentHash = "#/study-history";
    if (!safeDesktop()) return;
    const previousResults = $app.querySelector(".history-results");
    if (previousResults) {
      previousResults.inert = true;
      previousResults.setAttribute("aria-busy", "true");
      previousResults.insertAdjacentHTML("afterbegin", '<p class="filter-loading" role="status">正在读取记录…</p>');
    } else ExperienceUI.loading("学习记录");
    try {
      const query = new URLSearchParams();
      if (dayFilter) query.set("day", dayFilter);
      if (sourceFilter) {
        const [topicId, itemId] = sourceFilter.split("/");
        query.set("topic_id", topicId); query.set("item_id", itemId);
      }
      const data = await api("GET", `/api/study/history${query.size ? `?${query}` : ""}`);
      if (viewStale(token) || revision !== state.historyRevision) return;
      const historyHtml = `<div class="study-page oral-history"><div class="study-breadcrumb"><a href="#/today">今日练习</a><span>/</span>学习记录</div>
        <h1>口答学习记录</h1><p class="study-muted">这里记录实际口答、自评与录音，不生成分数。</p>
        <div class="study-review-filter"><label>日期 <input type="date" id="oral-history-date" value="${esc(dayFilter)}"></label>
          <label>题目 <select id="oral-history-source"><option value="">全部题目</option>
            ${(data.sources || []).map(row => `<option value="${esc(`${row.topic_id}/${row.item_id}`)}" ${sourceFilter === `${row.topic_id}/${row.item_id}` ? "selected" : ""}>${esc(row.question)}</option>`).join("")}
          </select></label></div>
        <div class="history-results"><p class="study-muted">已通过默写 ${data.dictation_passed_total} 句；${data.dictation_undated_count} 句为无日期的历史记录。</p>
        ${data.undated_legacy_count ? `<p class="today-note">${data.undated_legacy_count} 条旧困难句没有历史练习日期，已作为首次复习候选。</p>` : ""}
        ${data.days.length ? data.days.map(day => `<section class="today-section"><h2>${esc(day.date)}</h2>
          <dl class="history-facts"><div><dt>默写通过</dt><dd>${day.dictation_passed_count} 句</dd></div>
            <div><dt>实际口答</dt><dd>${day.attempt_count} 次 · ${day.distinct_sentence_count} 句</dd></div>
            <div><dt>本人自评</dt><dd>独立 ${day.ratings.independent}／提示 ${day.ratings.needs_hint}／暂未说出 ${day.ratings.unable}</dd></div></dl>
          ${day.attempts.map(row => `<div class="study-recording-row"><div><strong>${esc(row.zh)}</strong>
            <small class="history-source">${esc(row.question)}</small><small>${ratingNames[row.rating]} · ${row.recorded
              ? row.recording_available === false ? "当时已录音，文件现不可用" : "已保存录音"
              : "未录音／本人自评"}</small><small>当次安排下次 ${esc(row.next_due_date)}</small></div>
            ${row.recorded && row.recording_available !== false ? `<audio controls preload="none" src="${recordingUrl(row, row.recording_id)}"></audio>` : ""}</div>`).join("")}
        </section>`).join("") : `<p class="today-empty">尚无口答记录。完成一次困难句口答后，这里会显示真实经过。</p>`}
      </div></div>`;
      if (previousResults?.isConnected) {
        const next = document.createElement("div"); next.innerHTML = historyHtml;
        previousResults.replaceWith(next.querySelector(".history-results"));
      } else $app.innerHTML = historyHtml;
      const filter = () => history(token, document.getElementById("oral-history-date").value,
        document.getElementById("oral-history-source").value);
      document.getElementById("oral-history-date").onchange = filter;
      document.getElementById("oral-history-source").onchange = filter;
      bindAudioCompetition();
    } catch (err) {
      if (!viewStale(token) && revision === state.historyRevision) {
        ExperienceUI.readError("学习记录读取失败", err, () => history(token, dayFilter, sourceFilter),
          previousResults?.isConnected ? previousResults : $app);
      }
    }
  }

  return { today, sessionView, history, leave };
})();
