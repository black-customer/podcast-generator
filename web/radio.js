/* 桌面教学电台与带定位的双人台词。 */

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
  output.innerHTML = `<section class="arcade-frame radio-player">
    <header><div><h2>${esc(episode.title)}</h2>
      <p class="arcade-muted">${episode.language_mode === "bilingual" ? "晓晓与云希" :
        episode.voices.B === "golden_self" ? "Bella 与我的母语分身" : "Bella 与 Puck"} · ${esc(fmtDur(episode.duration))}</p></div>
      <button class="study-button" type="button" data-radio-download>下载 MP3</button>
    </header>
    <div class="radio-playback"><audio controls preload="metadata" src="${esc(episode.audio_url)}"></audio>
      <label>播放速度 <select><option value="0.8">0.8×</option><option value="1" selected>1×</option>
        <option value="1.15">1.15×</option><option value="1.3">1.3×</option><option value="1.5">1.5×</option></select></label>
    </div>
    <ol class="radio-transcript" aria-label="主持台词">
      ${episode.lines.map(line => `<li><button type="button" data-start="${esc(line.start)}">
        <span>${line.speaker === "A" ? "导师" : "搭档"}</span><span>${esc(line.text)}</span>
        <time>${esc(fmtDur(line.start))}</time></button></li>`).join("")}
    </ol><p class="arcade-muted" role="status"></p></section>`;
  const audio = player = output.querySelector("audio");
  const status = output.querySelector("[role=status]");
  const list = output.querySelector(".radio-transcript");
  const rows = [...list.querySelectorAll("button")];
  let highlighted = -1;
  const highlight = () => {
    const index = episode.lines.findIndex(line => audio.currentTime >= line.start && audio.currentTime < line.end);
    if (index === highlighted) return;
    rows[highlighted]?.removeAttribute("aria-current");
    highlighted = index;
    const current = rows[index];
    if (!current) return;
    current.setAttribute("aria-current", "true");
    if (audio.paused) return;
    const top = current.offsetTop - list.offsetTop;
    if (top < list.scrollTop || top + current.offsetHeight > list.scrollTop + list.clientHeight)
      list.scrollTop = top - list.clientHeight / 3;
  };
  audio.addEventListener("timeupdate", highlight);
  audio.addEventListener("seeked", highlight);
  audio.addEventListener("play", () => { $audio.pause(); highlight(); });
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
  list.onclick = event => {
    const row = event.target.closest("[data-start]");
    if (!row) return;
    audio.currentTime = Number(row.dataset.start);
    audio.play().catch(() => { status.textContent = "点击播放器上的播放按钮继续。"; });
  };
  if (autoplay) audio.play().catch(() => { if (player === audio) status.textContent = "电台已生成，点击播放收听。"; });
  highlight();
}

async function open(token) {
  const params = new URLSearchParams(location.hash.split("?")[1]);
  const topic = params.get("topic"), item = params.get("item");
  const itemScope = Boolean(topic && item);
  const endpoint = itemScope ? `/api/topics/${encodeURIComponent(topic)}/items/${encodeURIComponent(item)}/teaching-podcast`
    : "/api/teaching-podcasts/daily";
  $app.innerHTML = `<main class="arcade-home radio-home" aria-labelledby="radio-title">
    <header class="arcade-home-head"><div><h1 id="radio-title">教学电台</h1><p>听女导师和男搭档把重点语块带进一段对话。</p></div>
    <a class="study-button" href="${itemScope ? `#/train/${esc(encodeURIComponent(topic))}/${esc(encodeURIComponent(item))}` : "#/today"}">${itemScope ? "返回本题" : "今日练习"}</a></header>
    <section class="arcade-frame radio-controls">
      <h2>${itemScope ? "本题教学播客" : "今日电台"}</h2>
      <form class="arcade-controls">
        <label>语言 <select name="language_mode"><option value="en">全英文漫谈</option>
          <option value="bilingual">中英结合电台</option></select></label>
        <label>男搭档 <select name="partner_voice"><option value="am_puck">Puck</option>
          <option value="golden_self">我的母语分身</option></select></label>
        <button class="study-button primary" type="submit">${itemScope ? "生成本题播客" : "生成今日电台"}</button>
      </form>
      <p class="arcade-muted" id="radio-engine">Bella 和 Puck 使用本地语音。</p>
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
    voice.disabled = pending || language.value === "bilingual";
    document.getElementById("radio-engine").textContent = language.value === "bilingual"
      ? "晓晓和云希使用在线语音服务，生成的双人台词会发送给该服务。"
      : `Bella 和 ${voice.value === "golden_self" ? "我的母语分身" : "Puck"}使用本地语音。`;
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
  const generate = async () => {
    if (pending) return;
    pending = true;
    submit.disabled = language.disabled = true;
    describe();
    status.textContent = "正在编排台词并合成双人音频…";
    try {
      const body = {language_mode: language.value,
        partner_voice: language.value === "en" ? voice.value : "am_puck"};
      const episode = await api("POST", endpoint, body);
      if (viewStale(token)) return;
      episodes = [episode, ...episodes.filter(row => row.id !== episode.id)];
      choose(episode, true);
      status.textContent = "电台已生成。";
    } catch (error) {
      if (!viewStale(token)) status.textContent = error.message;
    } finally {
      if (!viewStale(token)) {
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
  if (itemScope && params.get("generate") === "1") {
    params.delete("generate");
    window.history.replaceState(null, "", `#/radio?${params}`);
    generate();
  }
}

window.RadioUI = { open, reset, itemLink };
