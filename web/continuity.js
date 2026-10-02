/* 私有草稿与收听恢复；页面呈现复用现有路由，学习业务仍由学习模块负责。 */
"use strict";

const AnswerExperience = (() => {
  let current = null;
  let pendingLeave = Promise.resolve();
  const key = qid => `q05-draft:${qid}`;
  const offline = () => typeof PackState !== "undefined" && PackState.active;
  const readLocal = qid => { try { return JSON.parse(localStorage.getItem(key(qid))); } catch (_) { return null; } };
  const stash = ctx => { try { localStorage.setItem(key(ctx.qid), JSON.stringify({
    question_text: ctx.text, answer: ctx.answer, mode: ctx.mode, revision: ctx.revision,
  })); ctx.localFailed = false; } catch (_) { ctx.localFailed = true; status(ctx, "浏览器应急保存不可用，请保持页面打开直到服务保存成功。"); } };
  const status = (ctx, text) => { if (ctx === current) {
    const el = document.getElementById("draft-status"); if (el) el.textContent = text;
  } };
  function flush(ctx = current) {
    if (!ctx || !ctx.dirty || ctx.blocked) return ctx?.chain || Promise.resolve();
    clearTimeout(ctx.timer);
    ctx.chain = ctx.chain.catch(() => {}).then(async () => {
      if (!ctx.dirty || ctx.blocked) return;
      const snapshot = {question_text: ctx.text, answer: ctx.answer, mode: ctx.mode, revision: ctx.revision};
      status(ctx, "保存中 · 草稿未提交");
      try {
        const saved = await api("PUT", `/api/answer-drafts/${encodeURIComponent(ctx.qid)}`, snapshot);
        ctx.revision = saved.revision;
        ctx.dirty = ctx.answer !== snapshot.answer || ctx.mode !== snapshot.mode;
        if (!ctx.dirty) { localStorage.removeItem(key(ctx.qid)); status(ctx, "草稿已保存 · 未提交"); }
        else { stash(ctx); status(ctx, "新文字待保存 · 未提交"); }
      } catch (e) {
        stash(ctx); ctx.blocked = true;
        status(ctx, `保存失败：${e.message}。本页文字仍保留，请查看服务草稿或重试。`);
      }
    });
    return ctx.chain;
  }
  function leave() { if (current) { pendingLeave = flush(current); current = null; } }
  function change(ctx) {
    ctx.answer = ctx.input.value;
    ctx.mode = document.querySelector("[name='bank-gen-mode']:checked")?.value || "agent";
    ctx.dirty = true; stash(ctx); status(ctx, "等待保存 · 草稿未提交");
    clearTimeout(ctx.timer); ctx.timer = setTimeout(() => flush(ctx), 800);
  }
  async function recover(ctx) {
    try {
      const saved = await api("GET", `/api/answer-drafts/${encodeURIComponent(ctx.qid)}`);
      if (ctx !== current) return;
      const output = document.getElementById("draft-conflict");
      output.innerHTML = `<p>电脑服务上的草稿：</p><pre class="answer-text">${esc(saved.answer || "（空草稿）")}</pre>
        <button class="btn-pill" id="draft-use-server">使用服务草稿</button>
        <button class="btn-pill" id="draft-keep-local">保留本页文字并保存</button>`;
      const changed = saved.question_changed || saved.question_missing;
      document.getElementById("draft-use-server").onclick = () => {
        if (changed) { status(ctx, "题目已变化，请复制原草稿；不会套用到当前题目。"); return; }
        ctx.input.value = saved.answer || ""; ctx.answer = ctx.input.value;
        ctx.mode = saved.mode || "agent"; ctx.revision = saved.revision;
        document.querySelector(`[name='bank-gen-mode'][value='${ctx.mode}']`).checked = true;
        ctx.blocked = false; ctx.dirty = false; localStorage.removeItem(key(ctx.qid));
        output.innerHTML = ""; status(ctx, "已恢复服务草稿 · 未提交");
      };
      document.getElementById("draft-keep-local").onclick = () => {
        if (changed) { status(ctx, "题目已变化，请复制本页文字；原草稿仍保留。"); return; }
        ctx.revision = saved.revision; ctx.blocked = false; ctx.dirty = true;
        output.innerHTML = ""; stash(ctx); flush(ctx);
      };
    } catch (e) { status(ctx, `读取失败：${e.message}。本页内容仍保留，请重试。`); }
  }
  async function bindDraft(question) {
    const input = document.getElementById("bank-answer-input");
    if (!input || offline()) return;
    const ctx = {qid: question.id, text: question.text, input, answer: input.value, mode: "agent",
      revision: 0, dirty: false, blocked: true, chain: Promise.resolve()};
    current = ctx;
    input.disabled = true;
    await pendingLeave;
    if (ctx !== current || !input.isConnected) return;
    try {
      const saved = await api("GET", `/api/answer-drafts/${encodeURIComponent(ctx.qid)}`);
      if (ctx !== current || !input.isConnected) return;
      const pending = readLocal(ctx.qid);
      ctx.revision = saved.revision;
      const restored = pending || saved;
      if (restored.question_text && restored.question_text !== ctx.text) {
        document.getElementById("draft-conflict").innerHTML = `<p>题干已变化；原草稿仍保留，可复制后重新作答。</p>
          <pre class="answer-text">${esc(restored.answer)}</pre>`;
        status(ctx, "题干变化，自动保存已暂停");
      } else {
        input.value = restored.answer || ""; ctx.answer = input.value; ctx.mode = restored.mode || "agent";
        document.querySelector(`[name='bank-gen-mode'][value='${ctx.mode}']`).checked = true;
        ctx.blocked = !!pending && pending.revision !== saved.revision;
        ctx.dirty = !!pending;
        status(ctx, ctx.blocked ? "草稿存在不同版本；本页文字仍保留，请查看服务草稿。" :
          (input.value ? "草稿已恢复 · 未提交" : "草稿未提交 · 输入后自动保存"));
        if (ctx.blocked) recover(ctx); else if (ctx.dirty) flush(ctx);
      }
    } catch (e) {
      const pending = readLocal(ctx.qid);
      if (pending?.question_text === ctx.text) {
        input.value = pending.answer; ctx.answer = pending.answer;
        ctx.mode = ["agent", "api"].includes(pending.mode) ? pending.mode : "agent";
        ctx.revision = pending.revision;
        document.querySelector(`[name='bank-gen-mode'][value='${ctx.mode}']`).checked = true;
      }
      status(ctx, `草稿读取失败：${e.message}。输入会保留在本页，请重试读取后保存。`);
    } finally {
      if (ctx === current && input.isConnected) {
        input.disabled = false;
        input.addEventListener("input", () => change(ctx));
        document.querySelectorAll("[name='bank-gen-mode']").forEach(el => el.addEventListener("change", () => change(ctx)));
        document.getElementById("draft-retry").onclick = () => ctx.blocked ? recover(ctx) : flush(ctx);
        document.getElementById("draft-discard").onclick = async () => {
          if (!confirm("丢弃这道题的未提交草稿？已提交回答会保留。")) return;
          await ctx.chain;
          try {
            const saved = await api("DELETE", `/api/answer-drafts/${encodeURIComponent(ctx.qid)}?revision=${ctx.revision}`);
            ctx.revision = saved.revision; ctx.input.value = ""; ctx.answer = "";
            ctx.dirty = false; ctx.blocked = false; clearTimeout(ctx.timer);
            localStorage.removeItem(key(ctx.qid)); status(ctx, "草稿已丢弃 · 未提交");
          } catch (e) { status(ctx, `丢弃失败：${e.message}。文字仍保留。`); }
        };
      }
    }
  }
  async function submitted(ctx, answer, mode) {
    if (!ctx) return;
    await flush(ctx);
    if (ctx.blocked || ctx.dirty || ctx.answer.trim() !== answer || ctx.mode !== mode) return;
    try {
      await api("DELETE", `/api/answer-drafts/${encodeURIComponent(ctx.qid)}?revision=${ctx.revision}`);
      localStorage.removeItem(key(ctx.qid)); ctx.dirty = false;
    } catch (_) { toast("回答已提交；草稿清除结果未确认，稍后可查看草稿列表。"); }
  }
  async function savedAnswer(question, token) {
    const root = document.getElementById("saved-answer");
    if (!root) return;
    try {
      const list = await api("GET", `/api/bank/questions/${encodeURIComponent(question.id)}/answers`);
      if (!root.isConnected || viewStale(token)) return;
      const select = document.getElementById("answer-version");
      select.innerHTML = (list.answers || []).map((ref, i) => `<option value="${i}">${esc(ref.created_at ?
        new Date(ref.created_at).toLocaleString() : "历史回答")} · ${ref.has_audio ? "已有音频" : "音频未完成"}</option>`).join("");
      let sequence = 0;
      async function show(index) {
        const seq = ++sequence, ref = list.answers[index];
        if (!ref) { root.innerHTML = '<p>已有回答已删除，请刷新列表或重新作答。</p>'; return; }
        root.innerHTML = '<p role="status">正在读取回答…</p>';
        try {
          const item = await api("GET", `/api/topics/${encodeURIComponent(ref.topic_id)}/items/${encodeURIComponent(ref.item_id)}`);
          if (seq !== sequence || !root.isConnected || viewStale(token)) return;
          const t = encodeURIComponent(ref.topic_id), id = encodeURIComponent(ref.item_id);
          root.innerHTML = `<h3>原始回答</h3>${item.original_answer ? `<pre class="answer-text">${esc(item.original_answer)}</pre>` :
            '<p class="study-muted">此旧条目未保存原始回答。下面展示已有文本。</p>'}
            ${item.chinese ? `<details open><summary>已有中文</summary><pre class="answer-text">${esc(item.chinese)}</pre></details>` : ""}
            ${item.natural_english || item.monologue_text || item.podcast_text ? `<details open><summary>已有英文</summary>
              <pre class="answer-text">${esc(item.natural_english || item.monologue_text || item.podcast_text)}</pre></details>` : ""}
            <div class="study-actions">${item.has_audio ? `<a class="study-button primary" href="#/play/${t}/${id}">播放音频</a>` :
              `<button class="study-button primary" id="existing-generate">继续生成 · Agent</button>`}
            ${!offline() && item.has_audio_podcast ? `<a class="study-button" href="#/learn/${t}/${id}">${item.study_status === "ready" ? "开始／继续学习" : "补齐学习材料"}</a>` : ""}
            <a class="btn-pill" href="#/done/${t}/${id}">查看回答详情</a></div>
            ${!offline() ? `<p class="study-muted">${studyStatusName(item.study_status)}</p>` : ""}`;
          document.getElementById("existing-generate")?.addEventListener("click", async () => {
            try {
              const req = await api("GET", `/api/topics/${t}/items/${id}/agent-task`);
              showAgentWait(req);
            } catch (e) { toast(`生成指令读取失败：${e.message}。已有回答仍保留，请重试。`); }
          });
        } catch (e) {
          if (seq === sequence && root.isConnected) ExperienceUI.readError("回答读取失败", e, () => show(index), root);
        }
      }
      select.onchange = () => show(Number(select.value));
      await show(0);
    } catch (e) { if (root.isConnected) ExperienceUI.readError("回答列表读取失败", e, () => savedAnswer(question, token), root); }
  }
  async function recoveryList(token) {
    if (offline()) return;
    const el = document.getElementById("draft-library"); if (!el) return;
    try {
      const data = await api("GET", "/api/answer-drafts");
      if (!el.isConnected || viewStale(token)) return;
      const pending = [];
      for (let i = 0; i < localStorage.length; i++) {
        const k = localStorage.key(i);
        if (k?.startsWith("q05-draft:")) {
          const r = readLocal(k.slice(10));
          if (r?.answer) pending.push({question_id: k.slice(10), ...r, emergency: true});
        }
      }
      const rows = [...(data.drafts || []), ...pending];
      el.innerHTML = `<summary>找回未提交草稿 · ${rows.length}</summary>${rows.length ? rows.map((r, i) =>
        `<section class="draft-library-row"><h3>${esc(r.question_text || r.question_id)}</h3>
        <p>${r.emergency ? "浏览器待保存副本" : r.question_changed || r.question_missing ? "题目已变化或不存在 · 原草稿保留" : "电脑服务草稿 · 未提交"}</p>
        <pre class="answer-text">${esc(r.answer)}</pre><button class="btn-pill" data-copy-draft="${i}">复制文字</button></section>`).join("") : '<p>没有未提交草稿。</p>'}`;
      el.querySelectorAll("[data-copy-draft]").forEach(btn => btn.onclick = async () => {
        try { await navigator.clipboard.writeText(rows[Number(btn.dataset.copyDraft)].answer); toast("草稿文字已复制"); }
        catch (_) { toast("复制失败，请选中草稿文字手动复制。"); }
      });
    } catch (e) { el.innerHTML = `<summary>找回未提交草稿</summary><p>${esc(e.message)}</p>`; }
  }
  window.addEventListener("pagehide", () => { if (current?.dirty) { stash(current); flush(current); } });
  window.addEventListener("beforeunload", e => {
    if (current?.dirty && current.localFailed) { e.preventDefault(); e.returnValue = ""; }
  });
  return {bindDraft, savedAnswer, recoveryList, leave, submitted, flush, get current() { return current; }};
})();

const CorpusExperience = (() => {
  let timer;
  function go(q, page = 1) {
    clearTimeout(timer);
    const qs = new URLSearchParams(location.hash.split("?")[1] || "");
    if (q.trim()) qs.set("q", q.trim()); else qs.delete("q");
    if (page > 1) qs.set("page", String(page)); else qs.delete("page");
    location.hash = `#/topics?${qs}`;
  }
  function controls(params) {
    return `<form id="corpus-search" class="corpus-search"><label for="corpus-q">搜索${PackState.active ? "当前离线包" : "全部语料"}</label>
      <div class="study-actions"><input id="corpus-q" type="search" value="${esc(params.get("q") || "")}" placeholder="题目、原始回答或中英文正文">
      <button class="study-button" type="submit">搜索</button><button class="btn-pill" type="button" id="corpus-clear">清空搜索</button></div></form>`;
  }
  function bind() {
    const input = document.getElementById("corpus-q"); if (!input) return;
    input.oninput = () => { clearTimeout(timer); timer = setTimeout(() => {
      if (input.isConnected) go(input.value);
    }, 300); };
    document.getElementById("corpus-search").onsubmit = e => { e.preventDefault(); go(input.value); };
    document.getElementById("corpus-clear").onclick = () => go("");
  }
  async function search(params, token) {
    const root = document.getElementById("corpus-results");
    root.inert = true; root.setAttribute("aria-busy", "true");
    root.innerHTML = '<p role="status">正在搜索全部语料…</p>';
    try {
      const data = await api("GET", `/api/search?q=${encodeURIComponent(params.get("q"))}&page=${params.get("page") || 1}&page_size=20`);
      if (!root.isConnected || viewStale(token)) return;
      root.innerHTML = `<p class="study-muted">${PackState.active ? "当前离线包" : "全部语料"} · 共 ${data.total ?? data.results.length} 条</p>` +
        data.results.map(r => {
          const t = encodeURIComponent(r.topic_id), id = encodeURIComponent(r.item_id);
          return `<article class="corpus-search-result"><h2>${esc(publicTitle(r.title))}</h2><p class="study-muted">${esc(r.topic_name)} · ${r.has_audio ? "已有音频" : "音频未完成"}</p>
            <p class="search-snippet">${esc(r.snippet)}</p><div class="study-actions"><a class="study-button" href="#/done/${t}/${id}">查看回答</a>
            ${r.has_audio ? `<a class="study-button primary" href="#/play/${t}/${id}">播放音频</a>` : `<a class="study-button" href="#/topic/${t}">继续生成</a>`}
            ${!PackState.active && r.study_status ? `<a class="study-button" href="#/learn/${t}/${id}">${r.study_status === "ready" ? "开始／继续学习" : "补齐学习材料"}</a>` : ""}</div></article>`;
        }).join("") + (!data.results.length ? '<p>没有匹配内容。可以换个词，或清空搜索返回分类浏览。</p>' : "") +
        (data.pageCount > 1 ? `<div class="bank-pager"><button class="btn-pill" id="corpus-prev" ${data.page <= 1 ? "disabled" : ""}>上一页</button>
          <span>第 ${data.page} / ${data.pageCount} 页</span><button class="btn-pill" id="corpus-next" ${data.page >= data.pageCount ? "disabled" : ""}>下一页</button></div>` : "");
      document.getElementById("corpus-prev")?.addEventListener("click", () => go(params.get("q"), data.page - 1));
      document.getElementById("corpus-next")?.addEventListener("click", () => go(params.get("q"), data.page + 1));
    } catch (e) { if (root.isConnected && !viewStale(token)) ExperienceUI.readError("搜索读取失败", e, () => search(params, token), root); }
    finally { if (root.isConnected) { root.inert = false; root.removeAttribute("aria-busy"); } }
  }
  return {controls, bind, search};
})();

const ListeningExperience = (() => {
  const bindings = new WeakMap();
  let writeQueue = Promise.resolve();
  let sequence = 0;
  const pendingKey = "q05-listen-pending";
  const localKey = "q05-listen-offline";
  const read = key => { try { return JSON.parse(localStorage.getItem(key) || "{}"); } catch (_) { return {}; } };
  const write = (key, data) => { try { localStorage.setItem(key, JSON.stringify(data)); return true; } catch (_) { toast("收听位置无法本地保存；当前播放仍可继续。"); return false; } };
  const key = source => JSON.stringify([source.kind, source.topic_id, source.item_id || "", source.track]);
  const query = source => new URLSearchParams(source).toString();
  async function prepare(source) {
    try {
      let info;
      if (PackState.active) {
        const it = PackState.topics.get(source.topic_id)?.items.get(source.item_id);
        const track = it?.audioUrls[source.track] ? source.track : Object.keys(it?.audioUrls || {})[0];
        if (!track) return null;
        const fingerprint = it.audioFingerprints[track];
        const actual = {...source, track, audio_fingerprint: fingerprint, title: it.title};
        const saved = read(localKey)[key(actual)];
        info = {...saved, ...actual, position: saved?.audio_fingerprint === fingerprint && !saved.completed ? saved.position : 0,
          completed: saved?.audio_fingerprint === fingerprint && Boolean(saved.completed),
          state: saved && saved.audio_fingerprint !== fingerprint ? "audio_changed" : "ready"};
      } else info = await api("GET", `/api/listening-progress?${query(source)}`);
      const pending = read(pendingKey)[key(info)];
      if (!PackState.active && pending?.audio_fingerprint === info.audio_fingerprint) info = {...info, ...pending};
      return info;
    } catch (e) { toast(`收听位置读取失败：${e.message}。音频仍可播放，请稍后重试。`); return null; }
  }
  function save(b, completed = false) {
    if (!b || !b.started || !b.info || !Number.isFinite(b.audio.currentTime)) return b?.chain || Promise.resolve();
    const body = {...b.source, track: b.info.track, audio_fingerprint: b.info.audio_fingerprint,
      position: b.audio.currentTime, duration: Number.isFinite(b.audio.duration) ? b.audio.duration : 0,
      completed, saved_at: new Date().toISOString(), title: b.info.title,
      _local_id: `${Date.now()}-${++sequence}`};
    const k = key(body);
    if (b.offline) { const records = read(localKey); records[k] = body; write(localKey, records); return Promise.resolve(); }
    const pending = read(pendingKey); pending[k] = body; const durable = write(pendingKey, pending);
    b.chain = writeQueue = writeQueue.catch(() => {}).then(async () => {
      try {
        const {_local_id, ...payload} = body;
        await api("PUT", "/api/listening-progress", payload);
        const latest = read(pendingKey);
        if (latest[k]?._local_id === body._local_id) { delete latest[k]; write(pendingKey, latest); }
        b.warned = false;
      } catch (e) {
        if (!b.warned) { toast(`收听位置保存失败：${e.message}。${durable ? "本机待保存位置仍保留" : "本页位置仍保留，请保持页面打开"}，播放可继续。`); b.warned = true; }
      }
    });
    return b.chain;
  }
  function detach(audio) {
    const b = bindings.get(audio); if (!b) return;
    save(b, b.completed); b.listeners.forEach(([event, fn]) => audio.removeEventListener(event, fn));
    bindings.delete(audio);
  }
  function attach(audio, source, info) {
    const b = {audio, source, info, offline: PackState.active, started: false, explicit: false,
      chain: Promise.resolve(), listeners: [], last: Date.now(), completed: false};
    bindings.set(audio, b);
    const on = (event, fn) => { audio.addEventListener(event, fn); b.listeners.push([event, fn]); };
    const restore = () => {
      if (bindings.get(audio) !== b || b.explicit) return;
      b.explicit = true;
      if (info?.state === "audio_changed") toast("音频已更新；本次从头播放。");
      if (info?.position > 0 && Number.isFinite(audio.duration)) audio.currentTime = Math.min(info.position, Math.max(0, audio.duration - 0.05));
    };
    on("loadedmetadata", restore);
    on("seeking", () => { b.explicit = true; if (b.started) save(b); });
    on("playing", () => {
      for (const id of ["core-audio", "ep-audio", "done-audio"]) {
        const other = document.getElementById(id); if (other && other !== audio) other.pause();
      }
      b.started = true; b.completed = false; save(b);
    });
    on("timeupdate", () => { if (Date.now() - b.last >= 5000) { b.last = Date.now(); save(b); } });
    on("pause", () => save(b, b.completed));
    on("ended", () => { b.completed = true; save(b, true); });
    const buttons = source.kind === "episode" ? ["ep-restart"] : audio.id === "done-audio" ? ["done-restart"] : ["gp-restart", "track-restart"];
    for (const id of buttons) {
      const button = document.getElementById(id);
      if (button) button.onclick = () => { b.explicit = true; b.completed = false; audio.currentTime = 0; save(b); audio.play().catch(() => {}); };
    }
  }
  async function latest() {
    if (!PackState.active) {
      try { return await api("GET", "/api/listening-progress/latest"); } catch (_) { return null; }
    }
    for (const saved of Object.values(read(localKey)).sort((a, b) => b.saved_at.localeCompare(a.saved_at))) {
      if (!PackState.topics.get(saved.topic_id)?.items.has(saved.item_id)) continue;
      return prepare({kind: "item", topic_id: saved.topic_id, item_id: saved.item_id, track: saved.track});
    }
    return null;
  }
  const explicit = audio => { const b = bindings.get(audio); if (b) b.explicit = true; };
  const complete = audio => { const b = bindings.get(audio); if (b) b.completed = true; };
  window.addEventListener("pagehide", () => { save(bindings.get($audio)); save(bindings.get(document.getElementById("ep-audio"))); });
  document.addEventListener("visibilitychange", () => { if (document.hidden) save(bindings.get($audio)); });
  return {prepare, attach, detach, latest, explicit, complete};
})();
