/* 单题逐句学习与本机练习记录。依赖 app.js 的 api、esc、$app。 */
"use strict";

const StudyUI = (() => {
  const state = { topicId: "", itemId: "", item: null, material: null, progress: null,
    review: false, reviewIndex: 0, reviewDraft: [], reviewPassed: false, hintTimer: null,
    reviewSession: false, reviewWrongCount: 0, reviewHintUsed: false,
    recorder: null, stream: null, chunks: [], blob: null, blobUrl: "", recordStart: 0,
    duration: 0, playback: null, saveTimer: null, currentHash: "" };
  const stageNames = { before: "先回答", dictation: "逐句默写", chinese: "看中文说",
    recall: "脱稿说", summary: "完成" };

  function endpoint(suffix = "") {
    return `/api/topics/${encodeURIComponent(state.topicId)}/items/${encodeURIComponent(state.itemId)}/study${suffix}`;
  }
  function href() {
    return `#/learn/${encodeURIComponent(state.topicId)}/${encodeURIComponent(state.itemId)}`;
  }
  function clearHint() {
    clearTimeout(state.hintTimer);
    state.hintTimer = null;
  }
  function stopMedia() {
    if (state.recorder && state.recorder.state === "recording") {
      state.recorder.onstop = null;
      state.recorder.stop();
    }
    if (state.stream) state.stream.getTracks().forEach(t => t.stop());
    state.stream = null;
    if (state.playback) state.playback.pause();
    state.playback = null;
  }
  window.addEventListener("beforeunload", event => {
    if (state.blob || state.recorder?.state === "recording") {
      event.preventDefault(); event.returnValue = "";
    }
  });
  function leave(nextHash) {
    if (nextHash === state.currentHash) return !(state.blob || state.recorder?.state === "recording");
    if (nextHash && (state.blob || state.recorder?.state === "recording")
      && !confirm(MobileRuntime.native ? "当前录音尚未加入练习。退出后已录内容会保留，可到我的未保存录音恢复。是否退出？" : "当前录音还没有保存，离开会丢失这段录音。是否离开？")) {
      location.hash = state.currentHash;
      return false;
    }
    clearHint();
    if (state.saveTimer && !state.review && state.progress?.stage === "dictation") {
      clearTimeout(state.saveTimer);
      api("PATCH", endpoint("/progress"), { draft: state.progress.draft })
        .catch(() => toast("草稿保存失败：重新进入本题可从上次保存继续。"));
    }
    state.saveTimer = null;
    stopMedia();
    if (state.blobUrl) URL.revokeObjectURL(state.blobUrl);
    state.blobUrl = "";
    state.blob = null;
    state.currentHash = "";
    return true;
  }
  function steps(stage) {
    const names = ["先回答", "逐句默写", "看中文说", "脱稿说"];
    const at = ["before", "dictation", "chinese", "recall", "summary"].indexOf(stage);
    if (at > 3) { /* summary：四步全部完成，无 current */ }
    return `<div class="study-steps" aria-label="学习阶段">${names.map((name, i) =>
      `<span class="study-step ${i === at ? "current" : ""} ${i < at ? "complete" : ""}">
        <b>${i + 1}</b><span>${name}</span></span>`).join("")}</div>`;
  }
  function shell(content, stage = "before") {
    $app.innerHTML = `<div class="study-page">
      <div class="study-breadcrumb">${MobileRuntime.native ? '<a href="#/materials">退出学习</a>' : `<a href="#/topics">我的语料</a><span>/</span><a href="#/topic/${encodeURIComponent(state.topicId)}">${esc(state.topicId)}</a>`}<span>/</span>学习</div>
      ${state.review ? "" : steps(stage)}
      ${content}
      <div class="study-footer"><a href="#/topics">返回我的语料</a></div>
    </div>`;
    $app.scrollTop = 0;
    $app.querySelector(".study-footer a").addEventListener("click", async e => {
      if (!state.saveTimer || state.review) return;
      e.preventDefault();
      clearTimeout(state.saveTimer);
      state.saveTimer = null;
      try {
        await save({ draft: state.progress.draft });
        location.hash = "#/topics";
      } catch (err) { toast(`草稿保存失败：${err.message}`); }
    });
  }
  function facts(index) {
    return state.progress.facts[String(index)] || {};
  }
  async function save(update) {
    state.progress = await api("PATCH", endpoint("/progress"), update);
    return state.progress;
  }
  function wordsOf(en) {
    return [...en.matchAll(/[A-Za-z]+(?:['’][A-Za-z]+)?/g)].map(m => m[0]);
  }
  function normalized(word) {
    return word.trim().toLowerCase().replace(/’/g, "'");
  }
  function activeIndex() {
    return state.review ? state.reviewIndex : state.progress.sentence_index;
  }
  function currentSentence() {
    return state.material.sentences[activeIndex()];
  }
  function currentDraft() {
    return state.review ? state.reviewDraft : state.progress.draft;
  }
  function currentPassed() {
    return state.review ? state.reviewPassed : !!facts(activeIndex()).passed;
  }
  function wordBoxes(en) {
    let index = 0;
    return en.split(/([A-Za-z]+(?:['’][A-Za-z]+)?)/g).map(part => {
      if (!/^[A-Za-z]+(?:['’][A-Za-z]+)?$/.test(part)) {
        return part.trim() ? `<span class="study-punctuation">${esc(part.trim())}</span>` : "";
      }
      const n = index++;
      return `<input class="study-word" data-word="${n}" aria-label="第 ${n + 1} 个词"
        autocomplete="off" autocapitalize="off" spellcheck="false"
        value="${esc(currentDraft()[n] || "")}" style="--word-ch:${Math.max(5, Math.min(17, part.length + 2))}ch">`;
    }).join("");
  }
  function renderDictation() {
    const index = activeIndex();
    const total = state.material.sentences.length;
    const sentence = currentSentence();
    const passed = currentPassed();
    shell(`<div class="study-question-block"><span>问题</span>
        <h1>${esc(state.item.question || state.item.title)}</h1></div>
      <section class="study-task">
        <div class="study-counter">${state.review ? "句子复习" : `第 ${index + 1} / ${total} 句`}</div>
        <h2 class="study-chinese">${esc(sentence.zh)}</h2>
        ${passed ? `<div class="study-explanation">
          <h3 class="study-counter">本句已写出示范英文</h3>
          <p class="study-answer">${esc(sentence.en)}</p>
          <div class="study-explain-grid"><div><h3>这句话怎么组织</h3><p>${esc(sentence.explanation)}</p></div>
            <div><h3>表达选择</h3><p>${esc(sentence.usage)}</p></div>
            ${sentence.original_error ? `<div><h3>你的原始表达</h3><blockquote>${esc(sentence.original_error.quote)}</blockquote>
              <p>${esc(sentence.original_error.issue)} ${esc(sentence.original_error.correction)}</p></div>` : ""}</div>
          <div class="study-actions"><button type="button" data-act="play">播放本句</button>
            <button type="button" data-act="favorite">${facts(index).favorite ? "取消收藏" : "收藏这句"}</button>
            <button type="button" class="primary" data-act="next">${state.review ? "返回复习库" : index + 1 < total ? "下一句" : "看中文完整口答"}</button></div>
        </div>` : `<div class="study-word-line" role="group" aria-label="按词输入完整英文句子">${wordBoxes(sentence.en)}</div>
          <div class="study-actions study-actions-fixed"><button type="button" data-act="play">播放本句</button>
            <button type="button" data-act="hint">短暂看答案</button>
            <button type="button" class="primary" data-act="check">检查答案</button></div>
          <div id="study-hint" class="study-hint" hidden></div>
          <p id="study-feedback" class="study-feedback" role="status">空格进入下一词，也可以输入整句。</p>`}
      </section>`, "dictation");
    $app.querySelector(".study-task").onclick = onDictationClick;
    if (!passed) {
      const inputs = [...$app.querySelectorAll(".study-word")];
      inputs.forEach((input, i) => {
        input.onkeydown = e => {
          if (e.key === "Tab" && e.shiftKey) return;
          if (e.key === " " || e.key === "Tab") {
            if (e.key === " " || i + 1 < inputs.length) e.preventDefault();
            (inputs[i + 1] || input).focus();
          } else if (e.key === "Backspace" && !input.value && i > 0) {
            e.preventDefault(); inputs[i - 1].focus();
          } else if (e.key === "Enter") {
            e.preventDefault();
            ExperienceUI.busy($app.querySelector("[data-act='check']"), "正在检查…", checkAnswer).catch(err => {
              const fb = document.getElementById("study-feedback");
              if (fb) fb.textContent = `操作失败：${err.message}`;
            });
          }
        };
        input.onpaste = e => {
          const pasted = e.clipboardData.getData("text");
          const pieces = wordsOf(pasted);
          if (pieces.length <= 1) return;
          e.preventDefault();
          pieces.forEach((part, j) => { if (inputs[i + j]) inputs[i + j].value = part; });
          (inputs[Math.min(i + pieces.length, inputs.length - 1)]).focus();
          saveDraft();
        };
        input.oninput = () => {
          const pieces = wordsOf(input.value);
          if (pieces.length > 1) {
            pieces.forEach((part, j) => { if (inputs[i + j]) inputs[i + j].value = part; });
            (inputs[Math.min(i + pieces.length, inputs.length - 1)]).focus();
          }
          saveDraft();
        };
      });
    }
  }
  function saveDraft() {
    const draft = [...$app.querySelectorAll(".study-word")].map(el => el.value);
    if (state.review) { state.reviewDraft = draft; return; }
    state.progress.draft = draft;
    clearTimeout(state.saveTimer);
    state.saveTimer = setTimeout(() => save({ draft }).catch(() => {
      const feedback = document.getElementById("study-feedback");
      if (feedback) feedback.textContent = "草稿保存失败，请保持本页打开并重试。";
    }), 350);
  }
  function editDistance(a, b) {
    const row = Array.from({ length: b.length + 1 }, (_, i) => i);
    for (let i = 1; i <= a.length; i++) {
      let last = row[0]; row[0] = i;
      for (let j = 1; j <= b.length; j++) {
        const old = row[j];
        row[j] = Math.min(row[j] + 1, row[j - 1] + 1, last + (a[i - 1] === b[j - 1] ? 0 : 1));
        last = old;
      }
    }
    return row[b.length];
  }
  async function checkAnswer() {
    const expected = wordsOf(currentSentence().en);
    const inputs = [...$app.querySelectorAll(".study-word")];
    const got = inputs.map(el => normalized(el.value));
    const feedback = document.getElementById("study-feedback");
    inputs.forEach(el => el.classList.remove("empty", "different"));
    if (got.some(x => !x)) {
      inputs.forEach((el, i) => el.classList.toggle("empty", !got[i]));
      feedback.textContent = "还有词框未填完，请补齐后检查。";
      inputs.find((_, i) => !got[i])?.focus();
      return;
    }
    saveDraft();
    if (got.every((word, i) => word === normalized(expected[i]))) {
      clearTimeout(state.saveTimer);
      state.saveTimer = null;
      if (state.review) {
        state.reviewPassed = true;
        await save({ facts: { [activeIndex()]: {
          review_attempts: (facts(activeIndex()).review_attempts || 0) + 1 } } });
      } else {
        await save({ draft: got, facts: { [activeIndex()]: { passed: true } } });
      }
      renderDictation();
      return;
    }
    const different = got.map((word, i) => word !== normalized(expected[i]));
    if (state.review) state.reviewWrongCount++;
    inputs.forEach((el, i) => el.classList.toggle("different", different[i]));
    const typo = different.findIndex((isDiff, i) => isDiff && got[i].length > 2
      && editDistance(got[i], normalized(expected[i])) <= 2);
    feedback.textContent = typo >= 0
      ? `第 ${typo + 1} 个词可能有拼写问题；其余不同表达请对照示范检查。`
      : "与示范不同，请对照检查。其他自然说法不直接判作英语错误；写出本句示范后进入讲解。";
    if (typo >= 0) ExperienceUI.focus(inputs[typo]);
    await save({ facts: { [activeIndex()]: {
      wrong_attempts: (facts(activeIndex()).wrong_attempts || 0) + 1 } } });
  }
  async function onDictationClick(e) {
    const button = e.target.closest("[data-act]");
    const action = button?.dataset.act;
    if (!action) return;
    if (button.disabled) return;
    const oldLabel = button.textContent;
    button.disabled = true;
    if (["check", "next"].includes(action)) button.textContent = action === "check" ? "正在检查…" : "正在保存…";
    try {
      if (action === "check") await checkAnswer();
      if (action === "play") await playSentence();
      if (action === "hint") {
        clearHint();
        const box = document.getElementById("study-hint");
        box.textContent = currentSentence().en;
        box.hidden = false;
        await save({ facts: { [activeIndex()]: { hint_used: true } } });
        if (state.review) state.reviewHintUsed = true;
        const duration = Number(localStorage.getItem("study-hint-seconds") || 5);
        state.hintTimer = setTimeout(() => {
          if (matchMedia("(prefers-reduced-motion: reduce)").matches) box.hidden = true;
          else { box.classList.add("fading"); setTimeout(() => { box.hidden = true; box.classList.remove("fading"); }, 250); }
        }, [3, 5, 8].includes(duration) ? duration * 1000 : 5000);
      }
      if (action === "favorite") {
        await save({ facts: { [activeIndex()]: { favorite: !facts(activeIndex()).favorite } } });
        renderDictation();
      }
      if (action === "next") {
        if (state.review) {
          if (state.reviewSession) {
            const session = JSON.parse(sessionStorage.getItem("study-review-round") || "{}");
            const queue = session.queue || [];
            const current = queue.findIndex(row => row.topic_id === state.topicId
              && row.item_id === state.itemId && row.sentence_index === state.reviewIndex);
            session.results = [...(session.results || []), {
              zh: currentSentence().zh, source: state.item.title,
              wrong_attempts: state.reviewWrongCount, hint_used: state.reviewHintUsed,
            }];
            sessionStorage.setItem("study-review-round", JSON.stringify(session));
            const nextRow = queue[current + 1];
            location.hash = nextRow
              ? `#/review-practice/${encodeURIComponent(nextRow.topic_id)}/${encodeURIComponent(nextRow.item_id)}/${nextRow.sentence_index}`
              : "#/review-done";
          } else location.hash = "#/review";
          return;
        }
        const next = activeIndex() + 1;
        await save(next < state.material.sentences.length
          ? { stage: "dictation", sentence_index: next, draft: [] }
          : { stage: "chinese", draft: [] });
        render();
      }
    } catch (err) {
      const feedback = document.getElementById("study-feedback");
      if (feedback) feedback.textContent = `操作失败：${err.message}`;
      else toast(`操作失败：${err.message}`);
    } finally {
      if (button.isConnected) { button.disabled = false; button.textContent = oldLabel; }
    }
  }
  async function playSentence() {
    const span = await api("GET", endpoint(`/audio/${activeIndex()}`));
    const notice = document.getElementById("study-feedback");
    if (notice) notice.textContent = span.reason;
    if (state.playback) state.playback.pause();
    $audio.pause();
    const path = `/api/topics/${encodeURIComponent(state.topicId)}/items/${encodeURIComponent(state.itemId)}/audio/podcast`;
    const audio = new Audio(mediaUrl(path) || path);
    state.playback = audio;
    audio.onloadedmetadata = () => { audio.currentTime = span.start || 0; audio.play().catch(() => {}); };
    if (span.end != null) audio.ontimeupdate = () => {
      if (audio.currentTime >= span.end) audio.pause();
    };
    audio.onerror = () => { if (notice) notice.textContent = "本句音频不可用，可到精听播放器听完整回答。"; };
  }
  function recordingHistory(stage = null) {
    const recordings = state.progress.recordings.filter(r => !stage || r.stage === stage);
    if (!recordings.length) return `<p class="study-muted">还没有保存的录音。</p>`;
    return `<div class="study-recordings">${recordings.map((r, i) => `<div class="study-recording-row">
      <div><strong>${esc(stageNames[r.stage])} · 第 ${i + 1} 版</strong>
        <small>${esc(r.created_at.replace("T", " "))} · ${r.duration_sec < 10 ? `${r.duration_sec.toFixed(1)} 秒` : fmtDur(r.duration_sec)}</small></div>
      <audio controls preload="none" src="${typeof MobileRuntime !== 'undefined' && MobileRuntime.native ? esc(MobileRuntime.fileUrl(r.path)) : endpoint(`/recordings/${encodeURIComponent(r.id)}`)}"></audio>
      <button type="button" data-delete="${esc(r.id)}" aria-label="删除这段录音">删除</button></div>`).join("")}</div>`;
  }
  function recorderPanel(stage) {
    return `<div class="study-recorder" data-rec-stage="${stage}">
      <div class="study-rec-status" id="study-rec-status" role="status">准备就绪 · 录音只保存在本机</div>
      <div class="study-actions"><button type="button" data-rec="start">${state.progress.recordings.some(r => r.stage === stage) ? "重录一版" : "开始录音"}</button>
        <button type="button" data-rec="stop" disabled>停止</button>
        <button type="button" data-rec="save" disabled class="primary">保存这版录音</button></div>
      <audio id="study-rec-preview" controls hidden></audio>
      <a id="study-rec-download" download="my-answer.webm" hidden>下载当前录音</a>
      <div id="study-rec-error" class="study-feedback" role="alert"></div>
      <h3>本阶段已完成的录音</h3>${recordingHistory(stage)}
    </div>`;
  }
  function renderRecording(stage) {
    const before = stage === "before";
    const chinese = stage === "chinese";
    const title = before ? "先说出你现在的回答" : chinese ? "看完整中文，连贯说一遍" : "只看原题，脱稿回答";
    const instruction = before ? "先不看示范，按自己的想法回答。" : chinese
      ? "中文是你原话的完整意思；试着连贯说完整篇回答。" : "不看中文或英文参考，只用原题组织回答。";
    shell(`<div class="study-question-block"><span>问题</span><h1>${esc(state.item.question || state.item.title)}</h1></div>
      <section class="study-task"><div class="study-counter">${esc(stageNames[stage])}</div>
        <h2>${title}</h2><p class="study-muted">${instruction}</p>
        ${chinese ? `<div class="study-full-chinese">${esc(state.material.complete_chinese)}</div>` : ""}
        ${recorderPanel(stage)}
        ${state.progress.recordings.some(r => r.stage === stage) ?
          `<button type="button" class="study-next" data-act="advance">${stage === "before" ? "继续逐句默写" : chinese ? "继续脱稿说" : "查看本次总结"}</button>`
          : `<button type="button" class="study-skip" data-act="skip-record">麦克风不可用？不录音，直接${stage === "before" ? "开始逐句默写" : chinese ? "进入脱稿回答" : "查看本次总结"}</button>`}
      </section>`, stage);
    bindRecording();
    ExperienceUI.recordingControls($app.querySelector(".study-recorder"), "ready",
      state.progress.recordings.some(r => r.stage === stage));
    const advance = async event => {
      if ((state.blob || state.recorder?.state === "recording")
        && !confirm("当前录音还没有保存。继续会丢失这段录音，是否继续？")) return;
      try {
        await ExperienceUI.busy(event.currentTarget, "正在保存进度…", async () => {
          await save({ stage: stage === "before" ? "dictation" : chinese ? "recall" : "summary",
            sentence_index: stage === "before" ? 0 : state.progress.sentence_index });
          stopMedia();
          if (state.blobUrl) URL.revokeObjectURL(state.blobUrl);
          state.blobUrl = ""; state.blob = null;
          render();
        });
      } catch (err) {
        document.getElementById("study-rec-error").textContent =
          `进度保存失败：${err.message}。本页录音仍保留，可重试。`;
      }
    };
    $app.querySelector("[data-act='advance']")?.addEventListener("click", advance);
    $app.querySelector("[data-act='skip-record']")?.addEventListener("click", advance);
  }
  function renderIntro() {
    const count = state.material.sentences.length;
    shell(`<section class="study-intro">
      <h1>开始这道题的学习</h1>
      <p class="study-muted">先说出自己的回答，再把整篇回答逐句练成自然英文。</p>
      <div class="study-intro-count">${count} 句话 · 全句默写 · 3 次完整回答</div>
      <div class="study-question-block"><span>Question</span>
        <h2>${esc(state.item.question || state.item.title)}</h2></div>
      <div class="study-intro-grid">
        ${["先回答", "逐句默写与讲解", "看中文说", "脱稿说"].map((name, i) =>
          `<div><b>${i + 1}</b><h3>${name}</h3><p>${[
            "先用自己的想法完整回答这道题。", "每一句都写出播报中的示范英文，再看讲解。",
            "看完整中文意思，连贯说出整篇回答。", "只看原题，再独立回答一遍。",
          ][i]}</p></div>`).join("")}</div>
      <button type="button" class="study-next" id="study-begin">开始本题学习</button>
    </section>`, "before");
    document.getElementById("study-begin").onclick = async () => {
      try { await save({ before_started: true }); renderRecording("before"); }
      catch (err) { toast(`无法开始学习：${err.message}`); }
    };
  }
  function bindRecording() {
    const panel = $app.querySelector(".study-recorder");
    panel.querySelector("[data-rec='start']").onclick = async () => {
      const button = panel.querySelector("[data-rec='start']");
      if (button.disabled) return;
      button.disabled = true;
      const viewHash = state.currentHash;
      const status = document.getElementById("study-rec-status");
      try {
        if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) throw new Error("当前浏览器没有录音能力");
        stopMedia();
        state.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        if (state.currentHash !== viewHash || !panel.isConnected) {
          state.stream.getTracks().forEach(track => track.stop()); state.stream = null; return;
        }
        const mime = ["audio/webm", "audio/ogg", "audio/mp4"].find(MediaRecorder.isTypeSupported);
        state.recorder = mime ? new MediaRecorder(state.stream, { mimeType: mime }) : new MediaRecorder(state.stream);
        state.chunks = [];
        state.recorder.ondataavailable = e => { if (e.data.size) state.chunks.push(e.data); };
        state.recorder.onstop = () => {
          state.duration = (performance.now() - state.recordStart) / 1000;
          state.blob = new Blob(state.chunks, { type: state.recorder.mimeType || mime || "audio/webm" });
          if (state.chunks[0]?.nativePath) state.blob.nativePath = state.chunks[0].nativePath;
          if (state.blobUrl) URL.revokeObjectURL(state.blobUrl);
          state.blobUrl = URL.createObjectURL(state.blob);
          const preview = document.getElementById("study-rec-preview");
          preview.src = state.blobUrl; preview.hidden = false;
          const download = document.getElementById("study-rec-download");
          download.href = state.blobUrl; download.hidden = false;
          download.download = `my-answer.${ExperienceUI.recordingExtension(state.blob.type)}`;
          panel.querySelector("[data-rec='save']").disabled = false;
          panel.querySelector("[data-rec='start']").disabled = false;
          panel.querySelector("[data-rec='stop']").disabled = true;
          status.textContent = `已停止 · ${fmtDur(state.duration)} · 可回听、重录或保存`;
          ExperienceUI.recordingControls(panel, "stopped");
          state.stream?.getTracks().forEach(t => t.stop()); state.stream = null;
        };
        state.recordStart = performance.now(); state.recorder.start();
        panel.querySelector("[data-rec='start']").disabled = true;
        panel.querySelector("[data-rec='stop']").disabled = false;
        panel.querySelector("[data-rec='save']").disabled = true;
        status.textContent = "正在录制…";
        ExperienceUI.recordingControls(panel, "recording");
      } catch (err) {
        button.disabled = false;
        if (!panel.isConnected) return;
        document.getElementById("study-rec-error").textContent =
          `无法使用麦克风：${err.message}。请检查浏览器权限或设备；已有进度可以保存并退出。`;
      }
    };
    panel.querySelector("[data-rec='stop']").onclick = () => {
      if (state.recorder?.state === "recording") state.recorder.stop();
    };
    panel.querySelector("[data-rec='save']").onclick = async () => {
      if (!state.blob) return;
      const button = panel.querySelector("[data-rec='save']");
      button.disabled = true;
      const url = endpoint(`/recordings?stage=${panel.dataset.recStage}&duration_sec=${state.duration.toFixed(2)}`);
      try {
        const response = await fetch(url, { method: "POST", body: state.blob,
          headers: { "Content-Type": state.blob.type } });
        if (!response.ok) throw new Error((await response.json()).detail || `HTTP ${response.status}`);
        state.progress = await api("GET", endpoint("/progress"));
        state.blob = null;
        if (state.blobUrl) URL.revokeObjectURL(state.blobUrl);
        state.blobUrl = "";
        renderRecording(panel.dataset.recStage);
      } catch (err) {
        button.disabled = false;
        document.getElementById("study-rec-error").textContent =
          `保存失败：${err.message}。录音仍在本页，可重试保存或下载当前录音。`;
      }
    };
    panel.querySelectorAll("[data-delete]").forEach(button => button.onclick = async () => {
      const id = button.dataset.delete;
      if (!confirm("删除选中的这段录音？其他版本会保留。")) return;
      await api("DELETE", endpoint(`/recordings/${encodeURIComponent(id)}`));
      state.progress = await api("GET", endpoint("/progress"));
      renderRecording(panel.dataset.recStage);
    });
    panel.querySelectorAll("audio").forEach(el => el.addEventListener("play", () => {
      $audio.pause();
      panel.querySelectorAll("audio").forEach(other => { if (other !== el) other.pause(); });
    }));
  }
  function renderSummary() {
    const count = state.material.sentences.length;
    const difficult = Object.values(state.progress.facts).filter(f => f.hint_used || f.wrong_attempts).length;
    shell(`<section class="study-task"><div class="study-counter">本题学习完成</div>
      <h1>回听你的三次回答</h1><p class="study-muted">已练 ${count} 句，其中 ${difficult} 句用过提示或与示范不同。这里记录实际练习，不给自动分数。</p>
      ${["before", "chinese", "recall"].map(stage => `<h2>${esc(stageNames[stage])}</h2>${recordingHistory(stage)}`).join("")}
      <div class="study-actions"><a class="study-button primary" href="#/review">复习困难句</a>
        <a class="study-button" href="#/play/${encodeURIComponent(state.topicId)}/${encodeURIComponent(state.itemId)}">自由收听</a></div>
    </section>`, "summary");
    $app.querySelectorAll("[data-delete]").forEach(button => button.onclick = async () => {
      if (!confirm("删除选中的这段录音？其他版本会保留。")) return;
      await api("DELETE", endpoint(`/recordings/${encodeURIComponent(button.dataset.delete)}`));
      state.progress = await api("GET", endpoint("/progress")); renderSummary();
    });
    $app.querySelectorAll("audio").forEach(el => el.addEventListener("play", () => {
      $audio.pause();
      $app.querySelectorAll("audio").forEach(other => { if (other !== el) other.pause(); });
    }));
  }
  function render() {
    if (state.review) { renderDictation(); return; }
    if (state.progress.stage === "before" && !state.progress.before_started) renderIntro();
    else if (state.progress.stage === "dictation") renderDictation();
    else if (state.progress.stage === "summary") renderSummary();
    else renderRecording(state.progress.stage);
  }
  async function view(topicId, itemId, token) {
    leave();
    state.currentHash = location.hash;
    state.topicId = topicId; state.itemId = itemId; state.review = false;
    ExperienceUI.loading("本题学习");
    if (typeof PackState !== "undefined" && PackState.active && !MobileRuntime.native) {
      $app.innerHTML = `<div class="study-page"><h1>手机端学习布局尚未开放</h1>
        <p>离线语料仍可浏览、播放和精听。</p><a href="#/topics">返回我的语料</a></div>`;
      return;
    }
    try {
      const [item, doc, progress] = await Promise.all([
        api("GET", `/api/topics/${encodeURIComponent(topicId)}/items/${encodeURIComponent(itemId)}`),
        api("GET", endpoint()), api("GET", endpoint("/progress")),
      ]);
      if (viewStale(token)) return;
      state.item = item; state.progress = progress;
      if (doc.status !== "ready") { renderMissing(doc); return; }
      state.material = doc.material;
      render();
    } catch (err) {
      if (!viewStale(token)) $app.innerHTML = `<div class="study-page"><h1>学习页加载失败</h1>
        <p>${esc(err.message)}</p><a href="#/topics">返回我的语料</a></div>`;
    }
  }
  function renderMissing(doc) {
    const names = { preparing: "正在准备逐句材料", needs_input: "逐句材料待补齐",
      failed: "逐句材料准备失败", changed: "回答内容已变化" };
    // 旧语料的原话在 chinese/natural_english 里，后端已给回退视图
    const original = state.item.original_answer_effective || state.item.original_answer;
    shell(`<section class="study-task study-missing"><h1>${names[doc.status] || "逐句材料未就绪"}</h1>
      <p>${esc(doc.reason || "请准备本题逐句学习材料。")}</p>
      ${doc.status === "needs_input" && !original ? `<label for="study-original">补齐你的原始回答</label>
        <textarea id="study-original" rows="5" placeholder="粘贴当时的中文、英文或混合原话"></textarea>
        <button type="button" data-missing="original">保存原话</button>` : ""}
      <div class="study-actions"><a class="study-button" href="#/play/${encodeURIComponent(state.topicId)}/${encodeURIComponent(state.itemId)}">继续听音频</a>
        ${state.item.has_audio_podcast && original ? `<button type="button" class="primary" data-missing="prepare">准备／重试材料</button>
          <button type="button" data-missing="agent">复制 Agent 任务</button>` : ""}</div>
      <p class="study-muted">API 准备会使用你自己的 StepFun 文本额度；Agent 可按独立材料命令提交。</p>
    </section>`);
    $app.querySelectorAll("[data-missing]").forEach(button => button.onclick = async () => {
      try {
        if (button.dataset.missing === "original") {
          const value = document.getElementById("study-original").value.trim();
          if (!value) throw new Error("请填写原始回答");
          await api("PATCH", `/api/topics/${encodeURIComponent(state.topicId)}/items/${encodeURIComponent(state.itemId)}`, { original_answer: value });
          route();
        } else if (button.dataset.missing === "prepare") {
          await api("POST", endpoint("/prepare")); route();
        } else {
          const task = await api("GET", `/api/topics/${encodeURIComponent(state.topicId)}/items/${encodeURIComponent(state.itemId)}/agent-task`);
          await navigator.clipboard.writeText(task.agent_prompt);
          button.textContent = "已复制 Agent 任务";
        }
      } catch (err) { button.insertAdjacentHTML("afterend", `<p class="study-feedback">${esc(err.message)}</p>`); }
    });
    if (doc.status === "preparing") setTimeout(() => { if (location.hash === href()) route(); }, 2000);
  }
  async function review(token) {
    leave(); state.review = false;
    sessionStorage.removeItem("study-review-round");
    ExperienceUI.loading("句子库");
    if (typeof PackState !== "undefined" && PackState.active) {
      $app.innerHTML = `<div class="study-page"><h1>手机端句子复习尚未开放</h1><a href="#/topics">返回我的语料</a></div>`;
      return;
    }
    try {
      const rows = await api("GET", "/api/study/review");
      if (viewStale(token)) return;
      const topics = [...new Map(rows.map(r => [r.topic_id,
        { id: r.topic_id, name: r.topic_name || r.topic_id }])).values()];
      $app.innerHTML = `<div class="study-page"><h1>句子库</h1>
        <p class="study-muted">收录写错、用过提示或收藏的句子。打开句子详情，可做整句默写或口答复习。</p>
        ${rows.length ? `<button type="button" class="study-next" id="study-review-start">开始本轮复习 · ${rows.length} 句</button>
          <label class="study-review-filter">来源题目
          <select id="study-review-source"><option value="">全部来源</option>
          ${topics.map(t => `<option value="${esc(t.id)}">${esc(t.name)}</option>`).join("")}</select></label>
          <div class="study-review-list">${rows.map(row => `<a data-topic="${esc(row.topic_id)}" href="#/review/${encodeURIComponent(row.topic_id)}/${encodeURIComponent(row.item_id)}/${row.sentence_index}">
          <strong>${esc(row.zh)}</strong><span>${esc(row.source)}</span></a>`).join("")}</div>`
          : `<div class="study-task"><h2>暂无待复习句子</h2><a href="#/practice">去选一道题</a></div>`}</div>`;
      const source = document.getElementById("study-review-source");
      const start = document.getElementById("study-review-start");
      if (start) start.onclick = () => {
        const chosen = rows.filter(row => !source.value || row.topic_id === source.value);
        sessionStorage.setItem("study-review-round", JSON.stringify({ queue: chosen, results: [] }));
        const first = chosen[0];
        location.hash = `#/review-practice/${encodeURIComponent(first.topic_id)}/${encodeURIComponent(first.item_id)}/${first.sentence_index}`;
      };
      if (source) source.onchange = () => $app.querySelectorAll(".study-review-list a").forEach(link => {
        link.hidden = !!source.value && link.dataset.topic !== source.value;
      });
    } catch (err) {
      if (!viewStale(token)) ExperienceUI.readError("句子库读取失败", err);
    }
  }
  async function reviewDetail(topicId, itemId, index, token, practice = false) {
    leave(); state.topicId = topicId; state.itemId = itemId; state.review = true;
    state.reviewIndex = index; state.reviewDraft = []; state.reviewPassed = false;
    const round = JSON.parse(sessionStorage.getItem("study-review-round") || "{}");
    state.reviewSession = (round.queue || []).some(row => row.topic_id === topicId
      && row.item_id === itemId && row.sentence_index === index);
    state.reviewWrongCount = 0; state.reviewHintUsed = false;
    ExperienceUI.loading("句子详情");
    try {
      const [item, doc, progress] = await Promise.all([
        api("GET", `/api/topics/${encodeURIComponent(topicId)}/items/${encodeURIComponent(itemId)}`),
        api("GET", endpoint()), api("GET", endpoint("/progress")),
      ]);
      if (viewStale(token)) return;
      state.item = item; state.progress = progress; state.material = doc.material;
      if (doc.status !== "ready" || !state.material?.sentences[index]) throw new Error("材料已变化，请先补齐");
      if (practice) renderDictation();
      else renderReviewDetail();
    } catch (err) {
      if (!viewStale(token)) $app.innerHTML = `<div class="study-page"><h1>无法复习这句</h1>
        <p>${esc(err.message)}</p><a href="#/review">返回复习库</a></div>`;
    }
  }
  function renderReviewDetail() {
    const sentence = currentSentence();
    const record = facts(activeIndex());
    shell(`<section class="study-task study-detail"><h1>句子详情</h1>
      <div class="study-question-block"><span>来源题目</span>
        <h2>${esc(state.item.question || state.item.title)}</h2></div>
      <div class="study-detail-sentence"><span>当前句子</span>
        <h2>${esc(sentence.zh)}</h2><p class="study-answer">${esc(sentence.en)}</p>
        <button type="button" data-detail="play">播放本句</button>
        <p id="study-feedback" class="study-feedback" role="status"></p></div>
      <div class="study-explain-grid"><div><h3>讲解</h3><p>${esc(sentence.explanation)}</p>
        <p>${esc(sentence.usage)}</p></div><div><h3>练习记录</h3>
        <p>${record.wrong_attempts ? `与示范不同 ${record.wrong_attempts} 次` : "无不同提交记录"}</p>
        <p>${record.hint_used ? "用过提示" : "未用提示"}</p>
        <p>${record.review_attempts ? `已复习 ${record.review_attempts} 次` : "尚未复习"}</p></div>
        ${sentence.original_error ? `<div><h3>有据的原始表达</h3>
          <blockquote>${esc(sentence.original_error.quote)}</blockquote>
          <p>${esc(sentence.original_error.issue)}</p>
          <p>${esc(sentence.original_error.correction)}</p></div>` : ""}</div>
      <div class="study-actions"><a class="study-button primary" href="#/review-practice/${encodeURIComponent(state.topicId)}/${encodeURIComponent(state.itemId)}/${activeIndex()}">再练这句</a>
        <button type="button" data-detail="favorite">${record.favorite ? "取消收藏" : "收藏这句"}</button>
        <a class="study-button" href="#/review">返回句子复习</a></div>
      <div id="oral-card-control" class="study-actions" role="status">正在读取口答日程…</div>
    </section>`, "dictation");
    $app.querySelector("[data-detail='play']").onclick = () => playSentence().catch(err => toast(err.message));
    $app.querySelector("[data-detail='favorite']").onclick = async () => {
      await save({ facts: { [activeIndex()]: { favorite: !facts(activeIndex()).favorite } } });
      renderReviewDetail();
    };
    refreshOralCardControl();
  }
  async function refreshOralCardControl() {
    const topicId = state.topicId, itemId = state.itemId, index = activeIndex();
    const box = document.getElementById("oral-card-control");
    if (!box) return;
    try {
      const path = `/api/topics/${encodeURIComponent(topicId)}/items/${encodeURIComponent(itemId)}/study/oral-review`;
      const current = await api("GET", `${path}?sentence_index=${index}`);
      if (!document.getElementById("oral-card-control") || topicId !== state.topicId
          || itemId !== state.itemId || index !== activeIndex()) return;
      if (current.status === "not_enrolled") {
        box.innerHTML = `<button type="button" data-oral-card="add">加入口答日程</button>
          <span class="study-muted">明天开始安排跨天口答。</span>`;
      } else if (current.status === "enrolled") {
        box.innerHTML = `<button type="button" data-oral-card="practice" ${current.card.paused ? "disabled" : ""}>现在口答这句</button>
          <button type="button" data-oral-card="pause">${current.card.paused ? "恢复日程" : "暂停日程"}</button>
          <span class="study-muted">${current.card.paused ? "已暂停" : `下次 ${esc(current.card.due_date)}`}</span>`;
      } else { box.textContent = "材料需要复核，暂不能加入日程。"; }
      box.querySelectorAll("[data-oral-card]").forEach(button => button.onclick = async () => {
        button.disabled = true;
        try {
          if (button.dataset.oralCard === "add") await api("POST", `${path}?sentence_index=${index}`);
          if (button.dataset.oralCard === "pause") await api("PATCH", `/api/study/review-cards/${encodeURIComponent(current.card.id)}`,
            { paused: !current.card.paused });
          if (button.dataset.oralCard === "practice") {
            const session = await api("POST", "/api/study/review-sessions", {
              topic_id: topicId, item_id: itemId, sentence_index: index,
            });
            location.hash = `#/oral-review/${encodeURIComponent(session.id)}`;
            return;
          }
          refreshOralCardControl();
        } catch (err) { toast(`口答日程操作失败：${err.message}`); button.disabled = false; }
      });
    } catch (err) { box.textContent = `口答日程暂不可用：${err.message}`; }
  }
  function reviewDone() {
    leave();
    const round = JSON.parse(sessionStorage.getItem("study-review-round") || "{}");
    const rows = round.results || [];
    $app.innerHTML = `<div class="study-page"><h1>本轮句子复习完成</h1>
      <p class="study-muted">以下只记录本轮实际练过的句子。</p>
      <div class="study-review-list">${rows.map(row => `<div class="study-review-result">
        <strong>${esc(row.zh)}</strong><span>${esc(row.source)}</span>
        <p>${row.wrong_attempts ? `与示范不同 ${row.wrong_attempts} 次` : "写出示范句"}${row.hint_used ? " · 使用提示" : ""}</p>
      </div>`).join("")}</div>
      <div class="study-actions"><a class="study-button primary" href="#/review">返回句子复习</a>
        <a class="study-button" href="#/topics">返回我的语料</a></div></div>`;
    $app.scrollTop = 0;
  }
  return { view, review, reviewDetail, reviewPractice: (t, i, n, token) =>
    reviewDetail(t, i, n, token, true), reviewDone, leave };
})();
