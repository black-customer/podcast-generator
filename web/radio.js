/* 桌面教学电台：异步生成与音频播放。 */

let player = null;

function reset() {
  player?.pause();
  player = null;
}

function itemLink(topic, item) {
  const params = new URLSearchParams({topic, item, generate: "1"});
  return `<a class="study-button" href="#/radio?${esc(params.toString())}">生成本题教学播客</a>`;
}

function renderEpisode(episode, output, autoplay) {
  reset();
  const partner = episode.voices.B === "golden_self" ? "我的母语分身" : "Puck";
  const voices = episode.language_mode === "bilingual"
    ? (episode.mandarin_voices ? `中文 晓晓与云希 · 英文 Bella 与 ${partner}` : "晓晓与云希")
    : `Bella 与 ${partner}`;
  output.innerHTML = `<section class="arcade-frame radio-player">
    <header><div><h2>${esc(episode.title)}</h2>
      <p class="arcade-muted">${esc(voices)} · ${esc(fmtDur(episode.duration))}</p></div>
      <button class="study-button" type="button" data-radio-download>下载 MP3</button>
    </header>
    ${episode.highlights?.length ? `<div class="arcade-chunks" aria-label="本集重点语块">
      ${episode.highlights.map(text => `<mark class="arcade-chunk">${esc(text)}</mark>`).join("")}</div>` : ""}
    ${episode.dry_run ? '<p class="arcade-muted">当前音频是试运行占位。</p>' : ""}
    <div class="radio-playback"><audio controls preload="metadata" src="${esc(episode.audio_url)}"></audio>
      <label>播放速度 <select><option value="0.8">0.8×</option><option value="1" selected>1×</option>
        <option value="1.15">1.15×</option><option value="1.3">1.3×</option><option value="1.5">1.5×</option></select></label>
    </div><p class="arcade-muted" role="status"></p></section>`;
  const audio = player = output.querySelector("audio");
  const status = output.querySelector("[role=status]");
  audio.addEventListener("play", () => $audio.pause());
  audio.addEventListener("error", () => { status.textContent = "电台音频暂时无法播放，请重新打开这一期。"; });
  output.querySelector("select").onchange = event => { audio.playbackRate = Number(event.target.value); };
  const download = output.querySelector("[data-radio-download]");
  download.onclick = async () => {
    download.disabled = true;
    try {
      const data = await localAudioBlob(episode.audio_url);
      const url = URL.createObjectURL(data);
      const link = document.createElement("a");
      link.href = url;
      link.download = `教学电台-${episode.id}.mp3`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 5000);
    } catch (error) {
      status.textContent = `下载失败：${error.message}`;
    } finally { download.disabled = false; }
  };
  if (autoplay) audio.play().catch(() => {
    if (player === audio) status.textContent = "电台已生成，点击播放收听。";
  });
}

async function open(token) {
  const params = new URLSearchParams(location.hash.split("?")[1]);
  const topic = params.get("topic"), item = params.get("item");
  const capture = params.get("capture") || null;
  const itemScope = Boolean(topic && item && !capture);
  const kind = capture ? "capture" : itemScope ? "item" : "daily";
  const autoGenerate = itemScope && params.get("generate") === "1";
  const endpoint = capture ? `/api/captures/${encodeURIComponent(capture)}/teaching-podcast`
    : itemScope ? `/api/topics/${encodeURIComponent(topic)}/items/${encodeURIComponent(item)}/teaching-podcast`
    : "/api/teaching-podcasts/daily";
  const back = capture ? "#/captures"
    : itemScope ? `#/train/${encodeURIComponent(topic)}/${encodeURIComponent(item)}` : "#/today";
  const heading = capture ? "剧集表达复盘" : itemScope ? "本题教学播客" : "今日电台";
  const action = capture ? "生成剧集复盘" : itemScope ? "生成本题播客" : "生成今日电台";
  $app.innerHTML = `<main class="arcade-home radio-home" aria-labelledby="radio-title">
    <header class="arcade-home-head"><div><h1 id="radio-title">教学电台</h1><p>听女导师和男搭档把重点语块带进一段对话。</p></div>
    <a class="study-button" href="${esc(back)}">${capture ? "返回素材" : itemScope ? "返回本题" : "今日练习"}</a></header>
    <section class="arcade-frame radio-controls">
      <h2>${heading}</h2>
      <form class="arcade-controls">
        <label>语言 <select name="language_mode"><option value="en">全英文漫谈</option>
          <option value="bilingual">中英结合电台</option></select></label>
        <label>男搭档 <select name="partner_voice"><option value="am_puck">Puck</option>
          <option value="golden_self">我的母语分身</option></select></label>
        <button class="study-button primary" type="submit">${action}</button>
      </form>
      <p class="arcade-muted" id="radio-engine">Bella 和 Puck 使用本地语音。</p>
      <div id="radio-progress"></div>
      <button class="study-button" id="radio-cancel" type="button" hidden>取消生成</button>
      <p id="radio-status" role="status"></p>
    </section>
    <div id="radio-output"></div>
    <section class="radio-history" aria-labelledby="radio-history-title"><h2 id="radio-history-title">已生成电台</h2>
      <div id="radio-history"></div></section></main>`;
  const form = $app.querySelector(".radio-controls form");
  const submit = form.querySelector("button");
  const status = $app.querySelector("#radio-status");
  const output = $app.querySelector("#radio-output");
  const history = $app.querySelector("#radio-history");
  const language = form.elements.language_mode, voice = form.elements.partner_voice;
  let episodes = [], selected = null, pending = false;
  const describe = () => {
    voice.disabled = pending;
    const partner = voice.value === "golden_self" ? "我的母语分身" : "Puck";
    document.getElementById("radio-engine").textContent = language.value === "bilingual"
      ? `中文由晓晓和云希朗读，英文使用 Bella 和 ${partner}。语音在本机合成。`
      : `Bella 和 ${partner}使用本地语音。`;
  };
  language.onchange = voice.onchange = describe;
  const historyRows = () => {
    history.innerHTML = episodes.length ? `<ul>${episodes.map(row =>
      `<li><button type="button" class="study-button" data-id="${esc(row.id)}"
        ${selected === row.id ? 'aria-current="true"' : ""}>${esc(row.title)}</button>
        <span>${row.language_mode === "bilingual" ? "中英结合" : "全英文"} · ${esc(fmtDur(row.duration))}</span></li>`
    ).join("")}</ul>` : "<p>生成的电台会保存在这里。</p>";
  };
  const choose = (episode, autoplay) => {
    selected = episode.id;
    historyRows();
    renderEpisode(episode, output, autoplay);
  };
  history.onclick = event => {
    const entry = event.target.closest("[data-id]");
    const episode = entry && episodes.find(row => row.id === entry.dataset.id);
    if (episode) choose(episode, true);
  };
  const host = $app.querySelector("#radio-progress");
  const cancel = $app.querySelector("#radio-cancel");
  const generate = async (restore = false) => {
    if (pending) return;
    pending = submit.disabled = language.disabled = true;
    describe();
    let progress;
    try {
      let existing;
      if (restore) {
        const jobs = await api("GET", "/api/jobs").catch(() => []);
        if (viewStale(token)) return;
        existing = jobs.find(({state, radio_scope: scope}) => state === "running" &&
          scope?.[0] === kind && scope[3] === (itemScope ? topic : null) &&
          scope[4] === (itemScope ? item : null) && scope[5] === capture);
        if (!existing && !autoGenerate) return;
        if (existing) {
          language.value = existing.radio_scope[1];
          voice.value = existing.radio_scope[2];
          describe();
        }
      }
      submit.classList.add("is-busy");
      status.textContent = existing?.cancel ? "正在取消…" : "";
      progress = ExperienceUI.progressBar(host, "文本引擎正在编排双人播客…",
        Date.parse(existing?.started_at) || Date.now());
      const id = existing?.id || (await api("POST", endpoint, {
        language_mode: language.value, partner_voice: voice.value,
      })).job_id;
      if (viewStale(token)) return;
      const url = `/api/jobs/${encodeURIComponent(id)}`;
      cancel.hidden = false;
      cancel.disabled = Boolean(existing?.cancel);
      cancel.onclick = async () => {
        cancel.disabled = true;
        try {
          const result = await api("POST", url + "/cancel");
          if (result.cancelled && !viewStale(token) && cancel.onclick) status.textContent = "正在取消…";
        } catch (error) {
          cancel.disabled = false;
          status.textContent = error.message;
        }
      };
      while (!viewStale(token)) {
        const job = await api("GET", url);
        if (viewStale(token)) return;
        if (job.state === "done") {
          const episode = job.episode;
          episodes = [episode, ...episodes.filter(row => row.id !== episode.id)];
          choose(episode, true);
          status.textContent = "电台已生成。";
          return;
        }
        if (job.state === "cancelled") { status.textContent = "已取消生成。"; return; }
        if (job.state !== "running") throw new Error(job.errors?.[0]?.message || "电台生成中断，请重试");
        const total = job.total, done = job.done;
        const label = job.phase === "tts" && total ? `本地语音已合成 ${done} / ${total} 段` :
          job.phase === "master" ? "正在统一响度并检查静音…" : "文本引擎正在编排双人播客…";
        progress.set(label, job.phase === "tts" && total ? Math.round(100 * done / total) : undefined);
        await new Promise(resolve => setTimeout(resolve, 650));
      }
    } catch (error) {
      if (!viewStale(token)) status.textContent = error.message;
    } finally {
      progress?.stop();
      if (!viewStale(token)) {
        host.replaceChildren();
        cancel.hidden = true;
        cancel.disabled = false;
        cancel.onclick = null;
        submit.classList.remove("is-busy");
        pending = submit.disabled = language.disabled = false;
        describe();
      }
    }
  };
  form.onsubmit = event => { event.preventDefault(); generate(); };
  api("GET", "/api/teaching-podcasts").then(result => {
    if (viewStale(token)) return;
    episodes = [...episodes, ...result.episodes.filter(row => !episodes.some(old => old.id === row.id))];
    historyRows();
    if (!itemScope && !selected && episodes.length) choose(episodes[0], false);
  }).catch(error => { if (!viewStale(token)) history.textContent = error.message; });
  if (autoGenerate) {
    params.delete("generate");
    window.history.replaceState(null, "", `#/radio?${params}`);
  }
  generate(true);
}

window.RadioUI = { open, reset, itemLink };
