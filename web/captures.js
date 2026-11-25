/* 私有素材的收集、提炼与分拣。 */

let current = null;
const captions = { inbox: "待分拣收件箱", import: "导入新素材", active: "已入库表达", archived: "已归档" };
const labels = { target_chunk: "目标语块", chunk_in_sentence: "原句中的语块", en: "原句", zh: "中文",
  chunk_zh: "语块意思", trigger_context: "情境", disambiguator: "区别提示", explanation: "讲解",
  usage_boundary: "用法边界", feynman_hook: "理解钩子", transfer_prompt_zh: "迁移提示",
  transfer_example_en: "迁移示范" };

function imageMarkup(source, id) {
  const file = source.assets?.[0];
  if (!file) return "";
  const url = `/api/captures/${encodeURIComponent(id)}/assets/${encodeURIComponent(file)}`;
  return `<a href="${esc(url)}" target="_blank" rel="noopener" class="capture-image">
    <img src="${esc(url)}" loading="lazy" alt="素材的原始截屏"></a>`;
}

function sourceLink(source) {
  if (!source.source_url) return "";
  return `<a href="${esc(source.source_url)}" target="_blank" rel="noopener noreferrer"
    class="study-button">${source.note_id ? "原片复听 ↗" : "打开来源 ↗"}</a>`;
}

async function readImages(files) {
  if (files.length > 3) throw new Error("最多添加三张图片");
  return Promise.all(files.map(file => new Promise((resolve, reject) => {
    if (file.size > 10 * 1024 * 1024 || !/^image\/(png|jpeg|webp)$/.test(file.type)) {
      reject(new Error("每张图片须为不超过 10 MiB 的 PNG、JPEG 或 WebP"));
      return;
    }
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error("截图读取失败"));
    reader.readAsDataURL(file);
  })));
}

function open(token) {
  const ctx = {token, tab: "inbox", index: 0, cards: [], entries: [], images: [], busy: false};
  current = ctx;
  $app.innerHTML = `<main class="arcade-home captures-page" aria-labelledby="captures-title">
    <header class="arcade-home-head"><h1 id="captures-title">素材收集</h1>
      <a class="study-button" href="#/today">返回今日练习</a></header>
    <nav class="capture-tabs arcade-controls" aria-label="素材状态">
      ${Object.entries(captions).map(([key, label]) =>
        `<button class="study-button" type="button" data-capture-tab="${key}">${label}</button>`).join("")}
    </nav>
    <div class="arcade-controls" id="capture-actions">
      <button type="button" class="study-button" data-distill>多模态 API 批量提炼</button>
      <button type="button" class="study-button" data-agent>复制 Agent 批量制卡指令</button>
      <button type="button" class="study-button" data-cancel hidden>取消提炼</button>
    </div>
    <div id="capture-progress"></div><p id="capture-status" role="status"></p>
    <div id="capture-body"></div>
  </main>`;
  const root = $app.firstElementChild;
  const body = root.querySelector("#capture-body");
  const status = root.querySelector("#capture-status");
  const live = () => current === ctx && !viewStale(token);
  const notify = message => { if (live()) status.textContent = message; };

  function render() {
    if (!live()) return;
    const pending = ctx.entries.filter(row => row.extract_state !== "ready");
    for (const control of root.querySelectorAll("[data-capture-tab]")) {
      const key = control.dataset.captureTab, count = ctx.cards.filter(row => row.status === key).length;
      control.setAttribute("aria-pressed", key === ctx.tab);
      control.textContent = captions[key] + (key === "import" ? "" : `（${count}）`);
    }
    root.querySelector("[data-agent]").disabled = !pending.length;
    root.querySelector("[data-distill]").disabled = ctx.busy || !pending.length;
    if (ctx.tab === "import") {
      body.innerHTML = `<section class="arcade-frame capture-form">
        <h2>随手摘录或粘贴截图</h2><form id="capture-snippet">
          <label>标题（可选）<input class="mg-input" name="title"></label>
          <label>英文摘录<textarea class="mg-input" name="text" rows="4" placeholder="粘贴你想学的表达，或用 Ctrl+V 添加截图"></textarea></label>
          <label>截图（可选）<input type="file" accept="image/png,image/jpeg,image/webp" multiple name="images"></label>
          <div id="capture-images" class="capture-thumbnails"></div>
          <label>来源链接（可选）<input class="mg-input" name="source_url" type="url"></label>
          <label>备注（可选）<input class="mg-input" name="note"></label>
          <button class="study-button primary" type="submit">保存素材</button>
        </form></section>`;
      const form = body.querySelector("form");
      const thumbs = form.querySelector("#capture-images");
      const renderImages = () => {
        thumbs.innerHTML = ctx.images.map((image, index) =>
          `<div><img src="${esc(image)}" alt="待保存截图 ${index + 1}">
          <button type="button" class="study-button" data-remove="${index}">移除</button></div>`).join("");
      };
      const addImages = async files => {
        try {
          const images = await readImages(files);
          if (ctx.images.length + images.length > 3) throw new Error("最多添加三张图片");
          ctx.images = ctx.images.concat(images);
          if (form.isConnected) renderImages();
        } catch (error) { notify(error.message); }
      };
      form.onpaste = event => {
        const files = [...event.clipboardData.files].filter(file => file.type.startsWith("image/"));
        if (files.length) { event.preventDefault(); addImages(files); }
      };
      form.elements.images.onchange = () => addImages([...form.elements.images.files]);
      thumbs.onclick = event => {
        if (!event.target.matches("[data-remove]")) return;
        ctx.images.splice(Number(event.target.dataset.remove), 1);
        renderImages();
      };
      form.onsubmit = async event => {
        event.preventDefault();
        const data = Object.fromEntries(new FormData(form));
        try {
          await api("POST", "/api/captures/snippet", {...data, images: ctx.images});
          ctx.images = [];
          ctx.tab = "inbox";
          notify("素材已保存，可在收件箱提炼。");
          await refresh();
        } catch (error) { notify(error.message); }
      };
      renderImages();
      return;
    }
    const rows = ctx.cards.filter(row => row.status === ctx.tab);
    ctx.index = Math.max(0, Math.min(ctx.index, rows.length - 1));
    const row = rows[ctx.index];
    const source = row?.capture.source;
    const stateLabel = {pending: "待提炼", extracting: "提炼中", failed: "提炼失败"};
    body.innerHTML = (row ? `<section class="arcade-frame capture-current">
      <div class="capture-card-header"><div><p class="arcade-muted">${esc(row.capture.title)}</p>
        <h2 lang="en">${esc(row.target_chunk)}</h2></div><span>${ctx.index + 1} / ${rows.length}</span></div>
      <div class="capture-scene">${imageMarkup(source, row.capture_id)}<div>
        <p lang="en">${esc(row.en)}</p><p>${esc(row.zh)}</p>
        <p class="arcade-muted">${esc(row.trigger_context)}</p>${sourceLink(source)}</div></div>
      <div class="arcade-controls"><button class="study-button" type="button" data-step="-1"
        ${ctx.index === 0 ? "disabled" : ""}>上一张</button>
        <button class="study-button" type="button" data-step="1"
        ${ctx.index === rows.length - 1 ? "disabled" : ""}>下一张</button>
        ${row.status !== "active" ? '<button class="study-button primary" type="button" data-approve>确认入库 <kbd>Enter</kbd></button>' : ""}
        ${row.status !== "archived" ? '<button class="study-button" type="button" data-archive>归档 <kbd>Backspace</kbd></button>' : ""}
        ${row.status === "active" ? `<a class="study-button" href="${esc('/api/cards/' + row.id + '/audio')}" target="_blank" rel="noopener">听示范</a>` : ""}
      </div>
      <details><summary>编辑卡片</summary><form class="capture-edit">
      ${Object.entries(labels).map(([key, label]) =>
        `<label>${label}<input class="mg-input" name="${key}" value="${esc(row[key])}"></label>`).join("")}
      <button class="study-button" type="submit">保存卡片</button></form></details></section>` :
      `<section class="arcade-frame"><h2>${ctx.tab === "inbox" ? "没有待分拣的卡片" : captions[ctx.tab]}</h2>
        <p>${ctx.tab === "inbox" && pending.length ? "先提炼下面的素材，再确认语块入库。" :
          "收集一句想学的英文或一张截图，随时开始。"}</p>
        <button class="study-button" type="button" data-open-import>导入新素材</button></section>`)
      + (ctx.tab === "inbox" && pending.length ? `<section class="capture-pending">
        <h2>待提炼素材</h2><ul>${pending.map(entry =>
          `<li><strong>${esc(entry.title)}</strong><span>${esc(stateLabel[entry.extract_state])}</span>
            ${entry.extract_error ? `<p>${esc(entry.extract_error)}</p>` : ""}
            <button type="button" class="study-button" data-distill-one="${esc(entry.id)}">提炼这条</button></li>`).join("")}</ul></section>` : "");
    const edit = body.querySelector(".capture-edit");
    if (edit) edit.onsubmit = async event => {
      event.preventDefault();
      try {
        await api("PATCH", `/api/cards/${row.id}`, Object.fromEntries(new FormData(edit)));
        notify("卡片已更新。");
        await refresh();
      } catch (error) { notify(error.message); }
    };
    ctx.row = row;
  }

  async function refresh() {
    try {
      const [entries, cards] = await Promise.all([api("GET", "/api/captures"), api("GET", "/api/cards")]);
      if (!live()) return;
      ctx.entries = entries.captures;
      ctx.cards = cards.cards;
      const badge = document.getElementById("nav-inbox-count");
      const count = ctx.cards.filter(row => row.status === "inbox").length;
      if (badge) {
        badge.hidden = !count;
        badge.textContent = count || "";
      }
      render();
    } catch (error) { notify(error.message); }
  }

  async function sortCard(action) {
    if (ctx.saving || !ctx.row) return;
    ctx.saving = true;
    try {
      await api("POST", `/api/cards/${ctx.row.id}/${action}`, {});
      notify(action === "approve" ? "已入库，本机正在准备示范音频。" : "已归档。");
      await refresh();
    } catch (error) { notify(error.message); }
    finally { ctx.saving = false; }
  }

  async function distill(endpoint) {
    if (ctx.busy || !confirm("发送所选素材文字与截图给当前配置的模型进行提炼？")) return;
    ctx.busy = true;
    const host = root.querySelector("#capture-progress");
    const progress = ExperienceUI.progressBar(host, "正在提炼语块…");
    const cancel = root.querySelector("[data-cancel]");
    try {
      const {job_id: id} = await api("POST", endpoint);
      cancel.hidden = false;
      cancel.onclick = async () => {
        try { await api("POST", `/api/jobs/${id}/cancel`); }
        catch (error) { notify(error.message); }
      };
      while (live()) {
        const job = await api("GET", `/api/jobs/${id}`);
        progress.set(`已处理 ${job.done} / ${job.total} 条`, Math.round(100 * job.done / job.total));
        if (job.state !== "running") {
          notify(job.errors?.map(entry => entry.message).join("；") ||
            (job.state === "done" ? "提炼结束，可以开始分拣。" : "提炼已停止。"));
          break;
        }
        await new Promise(resolve => setTimeout(resolve, 650));
      }
    } catch (error) { notify(error.message); }
    finally {
      ctx.busy = false;
      progress.stop();
      host.replaceChildren();
      cancel.hidden = true;
      if (live()) await refresh();
    }
  }

  root.addEventListener("click", async event => {
    const control = event.target.closest("button");
    if (!control) return;
    if (control.dataset.captureTab || control.hasAttribute("data-open-import")) {
      ctx.tab = control.dataset.captureTab || "import";
      ctx.index = 0;
      render();
    } else if (control.dataset.step) {
      ctx.index += Number(control.dataset.step); render();
    } else if (control.hasAttribute("data-approve")) sortCard("approve");
    else if (control.hasAttribute("data-archive")) sortCard("archive");
    else if (control.hasAttribute("data-distill")) distill("/api/captures/distill-pending");
    else if (control.dataset.distillOne) distill(`/api/captures/${control.dataset.distillOne}/distill`);
    else if (control.hasAttribute("data-agent")) {
      try {
        const task = await api("GET", "/api/captures/agent-task");
        if (live()) copyText(task.prompt);
      } catch (error) { notify(error.message); }
    }
  });
  ctx.key = event => {
    if (!live() || ctx.tab !== "inbox" || !ctx.row || event.repeat ||
        event.target.closest("input,textarea,select,[contenteditable]") ||
        event.ctrlKey || event.altKey || event.metaKey) return;
    if (event.key === "Enter" && !event.target.closest("button,a,summary")) {
      event.preventDefault(); sortCard("approve");
    } else if (event.key === "Backspace") { event.preventDefault(); sortCard("archive"); }
    else if (["ArrowLeft", "ArrowRight"].includes(event.key)) {
      event.preventDefault(); ctx.index += event.key === "ArrowLeft" ? -1 : 1; render();
    }
  };
  document.addEventListener("keydown", ctx.key);
  refresh();
}

function reset() {
  if (current) document.removeEventListener("keydown", current.key);
  current = null;
}

window.CapturesUI = {open, reset, imageMarkup, sourceLink};
