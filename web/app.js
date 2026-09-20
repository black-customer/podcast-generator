/* Bruce Audio Hub · Spotify 风格纯视听媒体库应用 */
"use strict";

const $app = document.getElementById("app");
const $audio = document.getElementById("core-audio");
const $globalPlayer = document.getElementById("global-player");

// 全局播放状态
const PlayerState = {
  currentTopic: null,
  currentItem: null,
  track: "podcast", // 'monologue' | 'podcast'
  isPlaying: false,
  playlist: [],
  currentIndex: -1,
  timeline: [],
  words: [],           // 逐词时间戳（SSE 数据可用时非空）
  timelineMode: "", // measured | estimated | sse | ""
  activeLineIndex: -1,
  activeWordIndex: -1,
  playbackRate: 1.0,
  userIsScrolling: false,
  programmaticScrollUntil: 0, // 程序性滚动窗口：期间 onscroll 不视为用户翻阅
  loopA: null,
  loopB: null,
  mediaRevision: 0,
};

/* ---------------- 基础工具 ---------------- */
function esc(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

async function api(method, url, body = null) {
  // 离线包模式（B02）：拦截请求走本地数据层，视图代码零改动复用
  if (typeof PackState !== "undefined" && PackState.active) {
    return packApi(method, url);
  }
  const opts = { method };
  if (body) {
    opts.headers = { "Content-Type": "application/json" };
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(url, opts);
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try {
      const j = await res.json();
      if (j.detail) msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch (_) {}
    throw new Error(msg);
  }
  return res.json();
}

function fmtDur(sec) {
  if (!sec || sec <= 0) return "0:00";
  const s = Math.round(sec);
  const m = Math.floor(s / 60);
  return `${m}:${String(s % 60).padStart(2, "0")}`;
}

function toast(msg) {
  const root = document.getElementById("toast-root");
  if (!root) return;
  const div = document.createElement("div");
  div.className = "toast-msg";
  div.textContent = msg;
  root.appendChild(div);
  setTimeout(() => {
    div.style.transition = "opacity 0.3s";
    div.style.opacity = "0";
    setTimeout(() => div.remove(), 300);
  }, 2500);
}

async function waitForJob(jobId, timeoutMs = 180000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const job = await api("GET", `/api/jobs/${encodeURIComponent(jobId)}`);
    if (job.state !== "running") return job;
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  throw new Error("生成任务等待超时");
}

/* ---------------- 全局播放器驱动 ---------------- */

// 顶层作用域（playItem 经 setTimeout 调用，函数必须可全局解析——曾因作用域问题截断播放链）
function updateMediaSession() {
  if (!("mediaSession" in navigator) || !PlayerState.currentItem) return;
  try {
    navigator.mediaSession.metadata = new MediaMetadata({
      title: PlayerState.currentItem.title || "未命名曲目",
      artist: "Bruce English Corpus",
      album: (PlayerState.currentTopic && PlayerState.currentTopic.name) || "English Corpus",
    });
  } catch (_) { /* ignore */ }
}

function initGlobalPlayer() {
  const $playBtn = document.getElementById("gp-play");
  const $prevBtn = document.getElementById("gp-prev");
  const $nextBtn = document.getElementById("gp-next");
  const $rewindBtn = document.getElementById("gp-rewind");
  const $forwardBtn = document.getElementById("gp-forward");
  const $speedBtn = document.getElementById("gp-speed");
  const $trackSwitch = document.getElementById("gp-track-switch");
  const $progressTrack = document.getElementById("gp-progress-track");
  const $progressFill = document.getElementById("gp-progress-fill");
  const $curTime = document.getElementById("gp-cur-time");
  const $totalTime = document.getElementById("gp-total-time");

  $playBtn.onclick = () => {
    if (!$audio.src) return;
    if ($audio.paused) {
      $audio.play();
    } else {
      $audio.pause();
    }
  };

  $audio.onerror = () => {
    if (!$audio.src) return;
    toast("音频加载失败（可能尚未生成该音轨）");
    PlayerState.isPlaying = false;
    const pb = document.getElementById("gp-play");
    if (pb) pb.textContent = "播放";
  };

  if ("mediaSession" in navigator) {
    try {
      navigator.mediaSession.setActionHandler("play", () => $audio.play().catch(() => {}));
      navigator.mediaSession.setActionHandler("pause", () => $audio.pause());
      navigator.mediaSession.setActionHandler("previoustrack", () => {
        if (PlayerState.playlist.length && PlayerState.currentIndex > 0) {
          playItem(PlayerState.currentTopic.id, PlayerState.playlist[PlayerState.currentIndex - 1]);
        }
      });
      navigator.mediaSession.setActionHandler("nexttrack", () => {
        if (PlayerState.playlist.length && PlayerState.currentIndex < PlayerState.playlist.length - 1) {
          playItem(PlayerState.currentTopic.id, PlayerState.playlist[PlayerState.currentIndex + 1]);
        }
      });
      navigator.mediaSession.setActionHandler("seekbackward", () => {
        if ($audio.duration) $audio.currentTime = Math.max(0, $audio.currentTime - 15);
      });
      navigator.mediaSession.setActionHandler("seekforward", () => {
        if ($audio.duration) $audio.currentTime = Math.min($audio.duration, $audio.currentTime + 15);
      });
    } catch (_) { /* 浏览器不支持则忽略 */ }
  }

  $audio.onplay = () => {
    PlayerState.isPlaying = true;
    $playBtn.textContent = "暂停";
    const disk = document.getElementById("vinyl-disk");
    if (disk) disk.classList.add("playing");
  };

  $audio.onpause = () => {
    PlayerState.isPlaying = false;
    $playBtn.textContent = "播放";
    const disk = document.getElementById("vinyl-disk");
    if (disk) disk.classList.remove("playing");
  };

  // 快退 15 秒
  if ($rewindBtn) {
    $rewindBtn.onclick = () => {
      if (!$audio.duration) return;
      $audio.currentTime = Math.max(0, $audio.currentTime - 15);
      toast("⏪ 快退 15 秒");
    };
  }

  // 快进 15 秒
  if ($forwardBtn) {
    $forwardBtn.onclick = () => {
      if (!$audio.duration) return;
      $audio.currentTime = Math.min($audio.duration, $audio.currentTime + 15);
      toast("⏩ 快进 15 秒");
    };
  }

  // 播放倍速切换 (0.8x -> 1.0x -> 1.2x -> 1.5x)
  if ($speedBtn) {
    $speedBtn.onclick = () => {
      const rates = [0.8, 1.0, 1.2, 1.5];
      const curIdx = rates.indexOf(PlayerState.playbackRate);
      const nextRate = rates[(curIdx + 1) % rates.length];
      PlayerState.playbackRate = nextRate;
      $audio.playbackRate = nextRate;
      $speedBtn.textContent = `${nextRate}x`;
      $speedBtn.classList.toggle("active-speed", nextRate !== 1.0);
      toast(`播放倍速已切换至 ${nextRate}x`);
    };
  }

  // 核心时间轴驱动：进度更新、A-B 循环与卡拉OK歌词高亮居中平滑跟随
  $audio.ontimeupdate = () => {
    if (!$audio.duration) return;
    const cur = $audio.currentTime;
    const pct = (cur / $audio.duration) * 100;
    $progressFill.style.width = `${pct}%`;
    $curTime.textContent = fmtDur(cur);
    $totalTime.textContent = fmtDur($audio.duration);

    // A-B 循环：到 B 点回跳 A 点
    if (PlayerState.loopA !== null && PlayerState.loopB !== null && PlayerState.loopB > PlayerState.loopA) {
      if (cur >= PlayerState.loopB - 0.03) {
        $audio.currentTime = PlayerState.loopA;
        return;
      }
    }

    // 同步高亮 Live Transcript
    if (PlayerState.timeline && PlayerState.timeline.length > 0) {
      const idx = PlayerState.timeline.findIndex(l => cur >= l.start && cur < l.end);
      if (idx !== -1 && idx !== PlayerState.activeLineIndex) {
        PlayerState.activeLineIndex = idx;
        PlayerState.activeWordIndex = -1;
        const line = PlayerState.timeline[idx];

        document.querySelectorAll(".dialogue-bubble.active, .monologue-line.active").forEach(el => {
          el.classList.remove("active");
        });

        const prefix = PlayerState.track === "podcast" ? "pod-line-" : "mono-line-";
        const activeEl = document.getElementById(`${prefix}${line.id}`);
        if (activeEl) {
          activeEl.classList.add("active");
          if (!PlayerState.userIsScrolling) {
            // 标记程序性滚动窗口：scrollIntoView 触发的 onscroll 不是用户翻阅（修 A24）
            PlayerState.programmaticScrollUntil = Date.now() + 900;
            activeEl.scrollIntoView({ behavior: "smooth", block: "center" });
          }
        }
      }

      // 词级卡拉OK：当前句内逐词点亮（words 数据可用时）
      if (PlayerState.words.length && PlayerState.activeLineIndex >= 0) {
        const line = PlayerState.timeline[PlayerState.activeLineIndex];
        if (cur >= line.start && cur < line.end) {
          const wi = PlayerState.words.findIndex(w => cur >= w.start && cur < w.end);
          if (wi !== PlayerState.activeWordIndex) {
            PlayerState.activeWordIndex = wi;
            const prefix = PlayerState.track === "podcast" ? "pod-word-" : "mono-word-";
            document.querySelectorAll(".karaoke-word.on").forEach(el => el.classList.remove("on"));
            if (wi !== -1) {
              const el = document.getElementById(`${prefix}${wi}`);
              if (el) el.classList.add("on");
            }
          }
        }
      }
    }
  };

  $audio.onended = () => {
    if (PlayerState.playlist.length && PlayerState.currentIndex < PlayerState.playlist.length - 1) {
      playItem(PlayerState.currentTopic.id, PlayerState.playlist[PlayerState.currentIndex + 1]);
    }
  };

  $progressTrack.onclick = (e) => {
    if (!$audio.duration) return;
    const rect = $progressTrack.getBoundingClientRect();
    const ratio = (e.clientX - rect.left) / rect.width;
    $audio.currentTime = ratio * $audio.duration;
  };

  $prevBtn.onclick = () => {
    if (PlayerState.playlist.length && PlayerState.currentIndex > 0) {
      playItem(PlayerState.currentTopic.id, PlayerState.playlist[PlayerState.currentIndex - 1]);
    }
  };

  $nextBtn.onclick = () => {
    if (PlayerState.playlist.length && PlayerState.currentIndex < PlayerState.playlist.length - 1) {
      playItem(PlayerState.currentTopic.id, PlayerState.playlist[PlayerState.currentIndex + 1]);
    }
  };

  $trackSwitch.onclick = async () => {
    const nextTrack = PlayerState.track === "podcast" ? "monologue" : "podcast";
    // 守卫：目标音轨不存在时提示（修 404 静默失败）
    if (PlayerState.currentTopic && PlayerState.currentItem) {
      try {
        const full = await api("GET", `/api/topics/${encodeURIComponent(PlayerState.currentTopic.id)}/items/${encodeURIComponent(PlayerState.currentItem.id)}`);
        const ok = nextTrack === "monologue" ? full.has_audio_monologue : full.has_audio_podcast;
        if (!ok) { toast("该条目没有另一条音轨"); return; }
      } catch (_) { /* 查询失败则照常尝试切换 */ }
    }
    setTrack(nextTrack);
  };

  // ---- A-B 循环与句子导航（M06）----
  const $loopA = document.getElementById("gp-loop-a");
  const $loopB = document.getElementById("gp-loop-b");
  const $loopClear = document.getElementById("gp-loop-clear");
  const $replayBtn = document.getElementById("gp-replay-line");

  function renderLoopUI() {
    const track = document.getElementById("gp-progress-track");
    if ($loopA) $loopA.classList.toggle("active-speed", PlayerState.loopA !== null);
    if ($loopB) $loopB.classList.toggle("active-speed", PlayerState.loopB !== null);
    if ($loopClear) $loopClear.style.display = (PlayerState.loopA !== null || PlayerState.loopB !== null) ? "" : "none";
    for (const [id, val] of [["gp-loop-a-mark", PlayerState.loopA], ["gp-loop-b-mark", PlayerState.loopB]]) {
      const mark = document.getElementById(id);
      if (!mark || !$audio.duration) { if (mark) mark.style.display = "none"; continue; }
      if (val === null) { mark.style.display = "none"; continue; }
      mark.style.display = "block";
      mark.style.left = `${(val / $audio.duration) * 100}%`;
    }
    if (track) track.classList.toggle("has-loop", PlayerState.loopA !== null && PlayerState.loopB !== null);
  }

  window.setLoopPoint = function(which) {
    if (!$audio.duration) { toast("尚未加载音频"); return; }
    const t = Math.min(Math.max(0, $audio.currentTime), $audio.duration - 0.05);
    if (which === "a") {
      PlayerState.loopA = t;
      toast(`循环起点 A = ${fmtDur(t)}${PlayerState.loopB !== null ? "，循环生效" : "（再按 B 设终点）"}`);
    } else {
      if (PlayerState.loopA === null) { toast("请先设置循环起点 A"); return; }
      if (t <= PlayerState.loopA + 0.2) { toast("B 点需晚于 A 点"); return; }
      PlayerState.loopB = t;
      toast(`A-B 循环生效：${fmtDur(PlayerState.loopA)} → ${fmtDur(t)}`);
    }
    renderLoopUI();
  };

  window.clearLoop = function() {
    PlayerState.loopA = null;
    PlayerState.loopB = null;
    renderLoopUI();
    toast("已清除 A-B 循环");
  };

  window.replayCurrentLine = function() {
    const idx = PlayerState.activeLineIndex;
    if (idx === -1 || !PlayerState.timeline[idx]) { toast("当前没有高亮句子"); return; }
    seekToTime(PlayerState.timeline[idx].start);
    toast("🔁 重播当前句");
  };

  window.seekLine = function(delta) {
    const tl = PlayerState.timeline;
    if (!tl || !tl.length) {
      if ($audio.duration) $audio.currentTime = Math.min(Math.max(0, $audio.currentTime + delta * 5), $audio.duration);
      return;
    }
    const cur = $audio.currentTime;
    let target;
    if (delta > 0) {
      target = tl.find(l => l.start > cur + 0.05);
    } else {
      const before = tl.filter(l => l.start < cur - 0.4);
      target = before[before.length - 1];
    }
    if (!target) target = delta > 0 ? tl[tl.length - 1] : tl[0];
    seekToTime(target.start);
  };

  if ($loopA) $loopA.onclick = () => window.setLoopPoint("a");
  if ($loopB) $loopB.onclick = () => window.setLoopPoint("b");
  if ($loopClear) $loopClear.onclick = () => window.clearLoop();
  if ($replayBtn) $replayBtn.onclick = () => window.replayCurrentLine();
  $audio.addEventListener("loadedmetadata", renderLoopUI);

  // ---- 键盘快捷键（输入框内不拦截）----
  document.addEventListener("keydown", (e) => {
    if (e.target && ["INPUT", "TEXTAREA", "SELECT"].includes(e.target.tagName)) return;
    if (e.code === "Space") {
      e.preventDefault();
      if ($audio.src) $audio.paused ? $audio.play().catch(() => {}) : $audio.pause();
    } else if (e.code === "ArrowRight") {
      e.preventDefault();
      window.seekLine(1);
    } else if (e.code === "ArrowLeft") {
      e.preventDefault();
      window.seekLine(-1);
    } else if (e.code === "KeyA") {
      window.setLoopPoint("a");
    } else if (e.code === "KeyB") {
      window.setLoopPoint("b");
    } else if (e.code === "KeyL") {
      window.clearLoop();
    } else if (e.code === "KeyR") {
      window.replayCurrentLine();
    }
  });
}

function setTrack(newTrack) {
  PlayerState.track = newTrack;
  const $switch = document.getElementById("gp-track-switch");
  if ($switch) {
    $switch.textContent = newTrack === "podcast" ? "切换为独白版" : "切换为播客版";
  }
  const shouldPlay = PlayerState.isPlaying || (!$audio.paused && $audio.src);
  if (PlayerState.currentItem && PlayerState.currentTopic) {
    playItem(PlayerState.currentTopic.id, PlayerState.currentItem, shouldPlay);
  }
  // 如果在详情页，同步选项卡
  const monoBtn = document.getElementById("btn-tab-mono");
  const podBtn = document.getElementById("btn-tab-pod");
  const scriptTitle = document.getElementById("script-panel-title");
  if (monoBtn && podBtn) {
    if (newTrack === "monologue") {
      monoBtn.classList.add("active");
      podBtn.classList.remove("active");
      if (scriptTitle) scriptTitle.textContent = "🎧 纯英母语独白文本 (Alex)";
    } else {
      podBtn.classList.add("active");
      monoBtn.classList.remove("active");
      if (scriptTitle) scriptTitle.textContent = "🎙️ 播客剧本实录";
    }
  }
}

async function playItem(topicId, item, autoPlay = true) {
  PlayerState.currentItem = item;
  PlayerState.currentTopic = { id: topicId };
  if (PlayerState.playlist) {
    PlayerState.currentIndex = PlayerState.playlist.findIndex(it => it.id === item.id);
  }
  $globalPlayer.style.display = "flex";
  const nowPlayingNav = document.getElementById("nav-now-playing");
  if (nowPlayingNav) {
    nowPlayingNav.href = `#/play/${encodeURIComponent(topicId)}/${encodeURIComponent(item.id)}`;
    document.querySelectorAll(".nav-item").forEach(el => el.classList.remove("active"));
    nowPlayingNav.classList.add("active");
  }

  const track = PlayerState.track;
  let audioUrl = mediaUrl(`/api/topics/${encodeURIComponent(topicId)}/items/${encodeURIComponent(item.id)}/audio/${track}`);
  if (!audioUrl) audioUrl = `/api/topics/${encodeURIComponent(topicId)}/items/${encodeURIComponent(item.id)}/audio/${track}`;
  if (!(typeof PackState !== "undefined" && PackState.active) && PlayerState.mediaRevision) {
    audioUrl += `?v=${PlayerState.mediaRevision}`;
  }

  $audio.src = audioUrl;
  $audio.playbackRate = PlayerState.playbackRate;
  if (autoPlay) {
    $audio.play().catch(() => {});
  }

  document.getElementById("gp-title").textContent = item.title || "未命名曲目";
  setTimeout(updateMediaSession, 0);
  document.getElementById("gp-sub").textContent = track === "podcast"
    ? "女问男答 · Native English"
    : "纯英母语独白";
  document.getElementById("gp-download").href = audioUrl;

  const disk = document.getElementById("vinyl-disk");
  if (disk) {
    if (autoPlay) disk.classList.add("playing");
    else disk.classList.remove("playing");
  }

  // 高亮列表中当前项
  document.querySelectorAll(".track-row").forEach(r => {
    r.classList.toggle("active", r.dataset.id === item.id);
  });

  // 加载并渲染时间轴
  await loadTimeline(topicId, item.id, track);
}

// 获取并渲染实时时间轴数据（lines=句级，words=逐词可选，mode=数据可信度）
async function loadTimeline(topicId, itemId, track) {
  PlayerState.timeline = [];
  PlayerState.words = [];
  PlayerState.activeLineIndex = -1;
  PlayerState.timelineMode = "";

  const emptyHtml = `<p style="color:var(--text-sub);padding:20px;">该条目暂无${track === "podcast" ? "播客" : "独白"}音频或剧本，可在工作台先生成。</p>`;
  try {
    const data = await api("GET", `/api/topics/${encodeURIComponent(topicId)}/items/${encodeURIComponent(itemId)}/timeline/${track}`);
    if (data && Array.isArray(data.lines) && data.lines.length > 0) {
      PlayerState.timeline = data.lines;
      PlayerState.words = Array.isArray(data.words) ? data.words : [];
      PlayerState.timelineMode = data.mode || "estimated";
      renderLiveTimelineUI();
      return;
    }
  } catch (e) {
    console.warn("未读取到实时时间轴：", e);
  }
  // 空态占位，避免停留在“加载中”
  const podStream = document.getElementById("pod-stream");
  const monoStream = document.getElementById("mono-stream");
  if (track === "podcast" && podStream) podStream.innerHTML = emptyHtml;
  if (track === "monologue" && monoStream) monoStream.innerHTML = emptyHtml;
}

// 格式化文本中的核心语块与标签
function formatBodyText(raw) {
  return esc(raw)
    .replace(/(\[[^\]]+\])/gi, '<em style="color:var(--text-muted);font-size:12px;font-style:italic;">$1</em>');
}

// 句文本渲染：有逐词数据时拆成词 span（供卡拉OK逐词点亮）
function renderLineText(line, lineIndex) {
  const words = PlayerState.words;
  const prefix = PlayerState.track === "podcast" ? "pod-word-" : "mono-word-";
  if (!words.length) return formatBodyText(line.text);
  const inLine = words
    .map((w, i) => ({ ...w, i }))
    .filter(w => w.start >= line.start - 0.01 && w.end <= line.end + 0.01);
  if (inLine.length < 2) return formatBodyText(line.text);
  // 用词表重建句子（词表即模型实际读出的文本）
  return inLine
    .map(w => `<span class="karaoke-word" id="${prefix}${w.i}">${esc(w.text)}</span>`)
    .join(" ");
}

// 渲染实时同步歌词流
function renderLiveTimelineUI() {
  const podStream = document.getElementById("pod-stream");
  const monoStream = document.getElementById("mono-stream");
  if (!podStream && !monoStream) return;

  const timeline = PlayerState.timeline;
  if (!timeline || timeline.length === 0) return;

  // 对齐模式标志：诚实显示数据可信度（measured=实测 / estimated=估算）
  const chip = document.getElementById("tl-mode-chip");
  if (chip) {
    const measured = PlayerState.timelineMode === "measured";
    chip.textContent = measured ? "实测对齐" : "估算对齐（重生成后升级）";
    chip.style.color = measured ? "var(--ok, #34c37e)" : "var(--text-muted, #8b93a5)";
  }

  if (PlayerState.track === "podcast" && podStream) {
    podStream.innerHTML = timeline.map(line => {
      const isA = line.speaker === "A";
      const spkClass = isA ? "a" : "b";
      const displayName = isA ? "Mia" : "Ethan";

      return `
        <div class="dialogue-bubble" id="pod-line-${line.id}" onclick="seekToTime(${line.start})">
          <div class="speaker-avatar ${spkClass}">${isA ? "A" : "B"}</div>
          <div class="bubble-content ${spkClass}">
            <div class="line-meta">
              <span>${esc(displayName)}</span>
              <span class="time-tag">${fmtDur(line.start)} - ${fmtDur(line.end)}</span>
              <span class="play-hint">点击跳播此句</span>
            </div>
            <div style="font-size:14.5px;line-height:1.65;">${renderLineText(line, line.id)}</div>
          </div>
        </div>
      `;
    }).join("");
    podStream.style.display = "flex";
    if (monoStream) monoStream.style.display = "none";
  } else if (PlayerState.track === "monologue" && monoStream) {
    monoStream.innerHTML = timeline.map(line => `
      <div class="monologue-line" id="mono-line-${line.id}" onclick="seekToTime(${line.start})" style="margin-bottom:12px;display:flex;flex-direction:column;gap:4px;">
        <div class="line-meta">
          <span class="time-tag">${fmtDur(line.start)} - ${fmtDur(line.end)}</span>
          <span class="play-hint">点击跳播</span>
        </div>
        <div style="font-size:15px;line-height:1.8;">${renderLineText(line, line.id)}</div>
      </div>
    `).join("");
    monoStream.style.display = "block";
    if (podStream) podStream.style.display = "none";
  }
}

// 点击句子精准跳转（元数据未就绪时排队等待，修 A32）
window.seekToTime = function(seconds) {
  if (!$audio.src) return;
  const apply = () => { $audio.currentTime = seconds; };
  if (!$audio.duration || isNaN($audio.duration)) {
    $audio.addEventListener("loadedmetadata", apply, { once: true });
  } else {
    apply();
  }
  if ($audio.paused) {
    $audio.play().catch(() => {});
  }
};

/* ---------------- 视图层 ---------------- */

// 1. 语料库：阅读索引
async function TopicsGalleryView(token) {
  $app.innerHTML = `<p class="view-loading">正在整理语料索引…</p>`;
  let topics = [];
  try {
    topics = await api("GET", "/api/topics");
  } catch (e) {
    if (viewStale(token)) return;
    $app.innerHTML = `<p style="color:var(--text-sub);padding:40px;">加载失败：${esc(e.message)}</p>`;
    return;
  }
  if (viewStale(token)) return;

  const hash = location.hash;
  let filtered = topics;
  if (hash.includes("cat=ielts")) {
    filtered = topics.filter(t => t.name.toLowerCase().includes("ielts") || t.name.toLowerCase().includes("雅思"));
  } else if (hash.includes("cat=daily")) {
    filtered = topics.filter(t => !t.name.toLowerCase().includes("ielts") && !t.name.toLowerCase().includes("雅思"));
  }

  const cardsHtml = filtered.map((t, idx) => `
    <button class="album-card corpus-index-row"
      onclick="location.hash='#/topic/${encodeURIComponent(t.id)}'">
      <span class="corpus-index-number">${String(idx + 1).padStart(2, "0")}</span>
      <span class="corpus-index-copy">
        <span class="album-name">${esc(t.name)}</span>
        <span class="album-meta">${t.stats.total} 条语料 · ${fmtDur(t.total_sec)} · 已生成 ${t.stats.generated}</span>
      </span>
      <span class="corpus-index-action">打开</span>
    </button>
  `).join("");

  $app.innerHTML = `
    <header class="page-heading">
      <div>
        <h1>语料库</h1>
        <p>把自己的表达整理成可以反复听的英语札记。</p>
      </div>
      <a class="text-action" href="#/bank">去题库选一道题</a>
    </header>

    <div class="album-grid">
      ${cardsHtml || `<p class="empty-state">还没有语料。先从题库选一道题开始。</p>`}
    </div>
  `;
}

// 2. 专辑详情与曲目列表
let topicRandomCtx = { topicId: "", items: [] };
function topicRandomPlay() {
  const { topicId, items } = topicRandomCtx;
  if (!items.length) { toast("本话题还没有已生成的音频"); return; }
  const pick = items[Math.floor(Math.random() * items.length)];
  location.hash = `#/play/${encodeURIComponent(topicId)}/${encodeURIComponent(pick.id)}`;
}

async function TopicDetailView(topicId, token) {
  $app.innerHTML = `<p style="color:var(--text-sub);padding:40px;">加载专辑详情中…</p>`;
  let topic, manifestMono = null, manifestPod = null;
  try {
    topic = await api("GET", `/api/topics/${encodeURIComponent(topicId)}`);
    try { manifestMono = await api("GET", `/api/topics/${encodeURIComponent(topicId)}/episode?track=monologue`); } catch (_) {}
    try { manifestPod = await api("GET", `/api/topics/${encodeURIComponent(topicId)}/episode?track=podcast`); } catch (_) {}
  } catch (e) {
    if (viewStale(token)) return;
    $app.innerHTML = `<p style="color:var(--text-sub);padding:40px;">加载失败：${esc(e.message)}</p>`;
    return;
  }
  if (viewStale(token)) return;

  PlayerState.currentTopic = topic;
  // 只把已生成音频的条目放进播放列表，避免连播时切到无声条目
  PlayerState.playlist = topic.items.filter(it => it.status === "generated");
  topicRandomCtx = { topicId, items: PlayerState.playlist };

  const rowsHtml = topic.items.map((it, idx) => `
    <div class="track-row" data-id="${esc(it.id)}" onclick="location.hash='#/play/${encodeURIComponent(topicId)}/${encodeURIComponent(it.id)}'">
      <div class="track-num">${idx + 1}</div>
      <div class="track-title">${esc(it.title)}</div>
      <div class="track-tags">
        ${it.has_monologue ? '<span class="track-pill mono">独白</span>' : ""}
        ${it.has_podcast ? '<span class="track-pill pod">女问男答</span>' : ""}
        ${it.stale ? '<span class="track-pill" style="color:var(--warn)">待更新</span>' : ""}
        ${it.error ? '<span class="track-pill" style="color:var(--err)">错误</span>' : ""}
        ${!it.has_monologue && !it.has_podcast ? '<span class="track-pill">—</span>' : ""}
      </div>
      <div>${it.duration_sec_podcast ? fmtDur(it.duration_sec_podcast) : (it.duration_sec ? fmtDur(it.duration_sec) : "—")}</div>
      <div><a class="btn-pill" style="padding:4px 12px;font-size:12px;" href="#/play/${encodeURIComponent(topicId)}/${encodeURIComponent(it.id)}">播放</a></div>
    </div>
  `).join("");

  $app.innerHTML = `
    <div class="album-header reading-topic-header">
      <div class="header-details">
        <div class="header-title">${esc(topic.name)}</div>
        <div class="header-meta">
          <span>共 ${topic.items.length} 条表达</span>
          <span>·</span>
          <span>点击标题开始阅读与收听</span>
        </div>
      </div>
    </div>

    <div class="action-bar">
      ${PlayerState.playlist.length ? `
        <button class="btn-pill" onclick="topicRandomPlay()">随机听一题</button>
      ` : ""}
      ${manifestPod ? `
        <a class="btn-round-play" id="btn-play-all-pod" title="打开整集播放器" href="#/episode/${encodeURIComponent(topicId)}/podcast" style="text-decoration:none;display:flex;align-items:center;justify-content:center;">▶</a>
        <span class="episode-summary">整集 ${fmtDur(manifestPod.total_sec)}${manifestPod.stale ? ' <span class="track-pill" style="color:var(--warn)">建议重建</span>' : ""}</span>
        <a class="btn-pill" href="#/episode/${encodeURIComponent(topicId)}/podcast">章节播放</a>
        <a class="btn-pill" href="/api/topics/${encodeURIComponent(topicId)}/episode/audio?track=podcast" download>下载 MP3</a>
      ` : ""}
      ${manifestMono ? `
        <a class="btn-pill" href="#/episode/${encodeURIComponent(topicId)}/monologue">独白整集 ${fmtDur(manifestMono.total_sec)}${manifestMono.stale ? " · 已过期" : ""}</a>
        <a class="btn-pill" href="/api/topics/${encodeURIComponent(topicId)}/episode/audio?track=monologue" download>下载 MP3</a>
      ` : ""}
    </div>

    <div class="tracklist">
      <div class="track-header">
        <div>#</div>
        <div>标题</div>
        <div>可用音轨</div>
        <div>时长</div>
        <div>操作</div>
      </div>
      ${rowsHtml || `<p style="color:var(--text-sub);padding:20px;">该专辑暂无曲目</p>`}
    </div>
  `;

}

// 3. 沉浸式单曲播放与卡拉OK实时剧本页
async function TrackPlayerView(topicId, itemId, token) {
  $app.innerHTML = `<p style="color:var(--text-sub);padding:40px;">加载曲目与双语剧本中…</p>`;
  let item, topic;
  try {
    topic = await api("GET", `/api/topics/${encodeURIComponent(topicId)}`);
    item = await api("GET", `/api/topics/${encodeURIComponent(topicId)}/items/${encodeURIComponent(itemId)}`);
  } catch (e) {
    if (viewStale(token)) return;
    $app.innerHTML = `<p style="color:var(--text-sub);padding:40px;">加载失败：${esc(e.message)}</p>`;
    return;
  }
  if (viewStale(token)) return;

  // 深链/刷新进入播放页也要有播放列表与话题上下文（修 A23：prev/next/连播不再失灵）
  PlayerState.currentTopic = topic;
  PlayerState.playlist = topic.items.filter(it => it.status === "generated");

  $app.innerHTML = `
    <div class="player-detail-container">
      <main class="reading-sheet">
        <a class="reading-breadcrumb" href="#/topic/${encodeURIComponent(topicId)}">语料库 / ${esc(topic.name)}</a>
        <h1 class="player-question">${esc(item.title)}</h1>
        <div class="reading-tags">
          <span>IELTS Speaking</span>
          <span>${PlayerState.track === "podcast" ? "女问男答" : "独白"}</span>
          <span id="tl-mode-chip">对齐模式…</span>
        </div>
        <div class="lyrics-panel" id="lyrics-panel">
          <div id="pod-stream" class="bubble-stream" style="display:${PlayerState.track === 'podcast' ? 'flex' : 'none'}">
            <p class="view-loading">正在整理时间轴…</p>
          </div>
          <div id="mono-stream" style="display:${PlayerState.track === 'monologue' ? 'block' : 'none'};">
            <p class="view-loading">正在整理时间轴…</p>
          </div>
        </div>
      </main>

      <aside class="reference-rail">
        <div class="reference-tabs" role="tablist" aria-label="参考信息">
          <button class="reference-tab active" type="button">中文参考</button>
          <button class="reference-tab" type="button" disabled>重点词汇</button>
          <button class="reference-tab" type="button" disabled>相关表达</button>
        </div>
        <div class="reference-heading">参考译文</div>
        <div id="zh-panel" class="zh-panel">${item.chinese ? esc(item.chinese) : '<p>该条目暂无中文参考</p>'}</div>
        <label class="reference-toggle">
          <input type="checkbox" id="zh-toggle" checked>
          <span>显示中文参考</span>
        </label>
        <div class="reference-divider"></div>
        <div class="reference-heading">音频信息</div>
        <div class="track-toggle-group">
          <button class="track-toggle-btn ${PlayerState.track === 'podcast' ? 'active' : ''}" id="btn-tab-pod"
            ${item.has_audio_podcast ? "" : 'disabled title="该条目没有播客轨音频"'}>女问男答</button>
          <button class="track-toggle-btn ${PlayerState.track === 'monologue' ? 'active' : ''}" id="btn-tab-mono"
            ${item.has_audio_monologue ? "" : 'disabled title="该条目没有独白轨音频"'}>独白</button>
        </div>
        <dl class="audio-facts">
          <div><dt>状态</dt><dd>${item.status === "generated" ? "已生成" : "待生成"}</dd></div>
          <div><dt>时长</dt><dd>${fmtDur(item.duration_sec_podcast || item.duration_sec || 0)}</dd></div>
          <div><dt>语速</dt><dd>${PlayerState.playbackRate.toFixed(1)}x</dd></div>
        </dl>
        <div class="reference-actions">
          ${(() => {
            const dl = mediaUrl(`/api/topics/${encodeURIComponent(topicId)}/items/${encodeURIComponent(itemId)}/audio/${PlayerState.track}`);
            return dl
              ? `<a class="btn-pill" href="${dl}" download="track.mp3">下载当前 MP3</a>`
              : "";
          })()}
          ${typeof PackState !== "undefined" && PackState.active ? "" : `
            <button class="btn-pill" id="remake-item">使用当前音色重制此条</button>
          `}
        </div>
      </aside>
    </div>
  `;

  // 中文参考折叠
  const zhToggle = document.getElementById("zh-toggle");
  const zhPanel = document.getElementById("zh-panel");
  if (zhToggle && zhPanel) {
    zhToggle.addEventListener("change", () => {
      zhPanel.style.display = zhToggle.checked ? "block" : "none";
    });
  }

  // 监听用户手动翻阅滚动，短时间内暂停自动居中抢焦
  // （程序性 scrollIntoView 落在 programmaticScrollUntil 窗口内，不算用户翻阅——修 A24）
  const panel = document.getElementById("lyrics-panel");
  if (panel) {
    let scrollTimer;
    panel.onscroll = () => {
      if (Date.now() < PlayerState.programmaticScrollUntil) return;
      PlayerState.userIsScrolling = true;
      clearTimeout(scrollTimer);
      scrollTimer = setTimeout(() => {
        PlayerState.userIsScrolling = false;
      }, 1400);
    };
  }

  // 绑定音轨切换
  document.getElementById("btn-tab-pod").onclick = () => {
    setTrack("podcast");
  };
  document.getElementById("btn-tab-mono").onclick = () => {
    setTrack("monologue");
  };

  const remakeButton = document.getElementById("remake-item");
  if (remakeButton) {
    remakeButton.onclick = async () => {
      const track = PlayerState.track;
      remakeButton.disabled = true;
      remakeButton.textContent = "正在重制…";
      try {
        const started = await api(
          "POST",
          `/api/topics/${encodeURIComponent(topicId)}/items/${encodeURIComponent(itemId)}/generate`,
          { force: true, track },
        );
        const job = await waitForJob(started.job_id);
        if (job.state !== "done" || (job.errors && job.errors.length)) {
          const detail = job.errors && job.errors.length ? job.errors[0].message : job.state;
          throw new Error(detail || "生成失败");
        }
        PlayerState.mediaRevision = Date.now();
        toast("重制完成，已载入新音频");
        route();
      } catch (e) {
        remakeButton.disabled = false;
        remakeButton.textContent = "使用当前音色重制此条";
        toast(`重制失败：${e.message}`);
      }
    };
  }

  // 自动开始播放当前曲目并载入时间轴
  playItem(topicId, item, true);
}

// 3.5 整集章节播放器（M10）：单文件连播 + 章节跳转 + 过期重建
async function EpisodePlayerView(topicId, track) {
  $app.innerHTML = `<p style="color:var(--text-sub);padding:40px;">加载整集中…</p>`;
  const tr = encodeURIComponent(track);
  let manifest, topic;
  try {
    topic = await api("GET", `/api/topics/${encodeURIComponent(topicId)}`);
    manifest = await api("GET", `/api/topics/${encodeURIComponent(topicId)}/episode?track=${tr}`);
  } catch (e) {
    $app.innerHTML = `<p style="color:var(--text-sub);padding:40px;">整集尚未合成：${esc(e.message)}</p>`;
    return;
  }
  if (viewStale(+ (location.hash.match(/__t=(\d+)/) || [0, routeToken])[1])) { /* noop */ }

  const staleBanner = manifest.stale
    ? `<div class="episode-stale">⚠️ 条目在合成后有更新，本集内容可能已过期。
         <button class="mg-btn tiny primary" id="ep-rebuild">🎬 一键重建</button></div>`
    : "";

  $app.innerHTML = `
    <a class="back-link" href="#/topic/${encodeURIComponent(topicId)}">← ${esc(manifest.topic_name)}</a>
    <div class="album-header">
      <div class="header-art">🎬</div>
      <div class="header-details">
        <div class="header-tag">整集 · ${track === "podcast" ? "播客版" : "独白版"}</div>
        <div class="header-title">${esc(manifest.topic_name)}</div>
        <div class="header-meta"><span>${manifest.item_count} 条 · ${fmtDur(manifest.total_sec)}</span></div>
      </div>
    </div>
    ${staleBanner}
    <div class="player-detail-container" style="grid-template-columns:1fr;">
      <div class="lyrics-panel">
        <div class="lyrics-header"><span>章节</span>
          <a class="btn-pill" href="/api/topics/${encodeURIComponent(topicId)}/episode/audio?track=${tr}" download>⬇ 下载整集</a>
        </div>
        <div id="ep-chapters">
          ${manifest.items.map((it, i) => `
            <div class="ep-chapter" data-offset="${it.offset_sec}" data-i="${i}">
              <span class="track-num">${i + 1}</span>
              <span style="flex:1;">${esc(it.title)}</span>
              <span class="time-tag">${it.offset_sec != null ? fmtDur(it.offset_sec) : ""}</span>
            </div>`).join("")}
        </div>
      </div>
    </div>
    <audio id="ep-audio" style="display:block;width:100%;margin-top:14px;" controls preload="auto"
      src="/api/topics/${encodeURIComponent(topicId)}/episode/audio?track=${tr}"></audio>
  `;

  const audio = document.getElementById("ep-audio");
  const chapters = Array.from(document.querySelectorAll(".ep-chapter"));
  function highlight() {
    const cur = audio.currentTime;
    let active = 0;
    chapters.forEach((ch, i) => {
      const off = parseFloat(ch.dataset.offset) || 0;
      if (cur >= off - 0.01) active = i;
    });
    chapters.forEach((ch, i) => ch.classList.toggle("active", i === active));
    const el = chapters[active];
    if (el && !PlayerState.userIsScrolling) el.scrollIntoView({ block: "nearest" });
  }
  audio.addEventListener("timeupdate", highlight);
  chapters.forEach(ch => {
    ch.onclick = () => {
      audio.currentTime = parseFloat(ch.dataset.offset) || 0;
      audio.play().catch(() => {});
    };
  });
  const rebuild = document.getElementById("ep-rebuild");
  if (rebuild) rebuild.onclick = async () => {
    rebuild.disabled = true; rebuild.textContent = "重建中…";
    try {
      const r = await api("POST", `/api/topics/${encodeURIComponent(topicId)}/episode?track=${tr}`);
      toast("重建任务已开始，完成后刷新本页");
      const timer = setInterval(async () => {
        try {
          const j = await api("GET", `/api/jobs/${r.job_id}`);
          if (j.state !== "running") { clearInterval(timer); EpisodePlayerView(topicId, track); }
        } catch (_) { clearInterval(timer); }
      }, 1500);
    } catch (e) { toast("重建失败：" + e.message); rebuild.disabled = false; }
  };
}

// 4. 音色展台
async function VoicesShowcaseView(token) {
  $app.innerHTML = `<p style="color:var(--text-sub);padding:40px;">加载声学音色展台中…</p>`;
  let voices = [], settings = {};
  try {
    voices = await api("GET", "/api/voices");
    settings = await api("GET", "/api/settings");
  } catch (e) {
    if (viewStale(token)) return;
    $app.innerHTML = `<p style="color:var(--text-sub);padding:40px;">加载失败：${esc(e.message)}</p>`;
    return;
  }
  if (viewStale(token)) return;

  const curVoiceA = (settings.reference_id || "").trim();
  const curVoiceB = (settings.reference_id_b || "").trim();

  const cardHtml = v => {
    const isCurA = v.reference_id === curVoiceA;
    const isCurB = v.reference_id === curVoiceB;

    const avatar = esc((v.name || "Voice").split(/\s|\(/)[0].slice(0, 2).toUpperCase());

    return `
      <div class="voice-card ${isCurA || isCurB ? 'active-voice' : ''}">
        ${isCurA ? `<div class="voice-badge-active">当前首选男声</div>` : (isCurB ? `<div class="voice-badge-active" style="background:#3d7bf6;color:#fff;">当前首选女声</div>` : "")}
        <div class="voice-header">
          <div class="voice-avatar">${avatar}</div>
          <div>
            <div class="voice-name">${esc(v.name)}</div>
            <div class="voice-tag">${esc(v.tag)}</div>
          </div>
        </div>
        <div class="voice-desc">${esc(v.description)}</div>
        <div class="voice-params">
          <span>口音: ${esc(v.accent)}</span>
          <span>语速: ${v.speed ?? 1.0}x</span>
          ${v.temperature != null ? `<span>温度: ${v.temperature}</span>` : ""}
        </div>
        <div>
          <button class="voice-btn" onclick="previewVoice('${esc(v.reference_id)}', this)" title="播放统一试听稿">试听</button>
          ${v.gender === 'male' ? `
            <button class="voice-btn ${isCurA ? 'btn-selected' : ''}" onclick="applyVoicePreset('${esc(v.reference_id)}', 'male', '${esc(v.name)}', ${v.speed ?? 1.0}, ${v.temperature ?? "null"})">
              ${isCurA ? "当前回答男声" : "设为回答男声"}
            </button>
          ` : `
            <button class="voice-btn ${isCurB ? 'btn-selected' : ''}" onclick="applyVoicePreset('${esc(v.reference_id)}', 'female', '${esc(v.name)}', ${v.speed ?? 1.0}, ${v.temperature ?? "null"})">
              ${isCurB ? "当前提问女声" : "设为提问女声"}
            </button>
          `}
        </div>
      </div>
    `;
  };

  const presets = voices.filter(v => v.tier !== "candidate");
  const candidates = voices.filter(v => v.tier === "candidate");
  const maleCandidates = candidates.filter(v => v.gender === "male");
  const femaleCandidates = candidates.filter(v => v.gender === "female");

  $app.innerHTML = `
    <div class="hero-banner voice-page-intro">
      <a class="reading-breadcrumb" href="#/manage">设置 / 音色</a>
      <div class="hero-title">选择长期模仿的声音</div>
      <div class="hero-desc">重点听年龄感、自然度和久听是否疲劳。候选使用同一试听稿与各自参数。</div>
    </div>

    <div class="section-header">
      <div class="section-title">当前预设</div>
    </div>

    <div class="voice-grid">
      ${presets.map(cardHtml).join("")}
    </div>

    ${maleCandidates.length ? `
    <div class="section-header" style="margin-top:28px;">
      <div class="section-title">回答男声候选</div>
      <div class="section-description">四个美式青年声使用同一试听稿</div>
    </div>
    <div class="voice-grid">
      ${maleCandidates.map(cardHtml).join("")}
    </div>` : ""}

    ${femaleCandidates.length ? `
    <div class="section-header" style="margin-top:28px;">
      <div class="section-title">提问女声候选</div>
      <div class="section-description">Mia 暂不更换，可按需试听其他方向</div>
    </div>
    <div class="voice-grid">
      ${femaleCandidates.map(cardHtml).join("")}
    </div>` : ""}
  `;
}

window.previewVoice = function(referenceId, btn) {
  // 单例试听：同一时间只播一个样本；再次点击停止
  let player = window.__voicePreview;
  if (player && !player.paused && player.dataset.ref === referenceId) {
    player.pause();
    return;
  }
  if (player) { player.pause(); }
  player = new Audio(`/api/voices/${encodeURIComponent(referenceId)}/sample`);
  player.dataset.ref = referenceId;
  window.__voicePreview = player;
  if (btn) {
    btn.textContent = "加载中…";
    btn.disabled = true;
    player.addEventListener("canplay", () => { btn.textContent = "停止"; btn.disabled = false; }, { once: true });
  }
  player.play().catch(() => {
    toast("试听加载失败，稍后再试");
    if (btn) { btn.textContent = "试听"; btn.disabled = false; }
  });
  player.addEventListener("ended", () => {
    const cards = document.querySelectorAll(".voice-btn");
    cards.forEach(b => { if (b.textContent === "停止") b.textContent = "试听"; });
  });
};

window.applyVoicePreset = async function(referenceId, gender, voiceName, speed, temperature) {
  try {
    const payload = {};
    if (gender === "male") {
      payload.reference_id = referenceId;
    } else {
      payload.reference_id_b = referenceId;
    }
    // 音色自带表演参数（voices.json 为唯一真源）
    if (speed && speed !== 1.0) payload.speed = speed;
    if (temperature != null) payload.temperature = temperature;
    await api("PUT", "/api/settings", payload);
    toast(`已将【${voiceName}】设为${gender === "male" ? "回答男声" : "提问女声"}`);
    VoicesShowcaseView();
  } catch (e) {
    toast(`设置失败：${e.message}`);
  }
};

/* ---------------- 工作台管理（设置 / 话题 / 条目 / 生成 / 合成） ---------------- */
const ManageState = {
  topicId: null,
  pollTimer: null,
  job: null,
};

const MG_FIELDS = [
  ["question", "问题（Question）", 2],
  ["chinese", "中文自由回答（Chinese）", 6],
  ["natural_english", "Natural English（改写后的地道口语）", 6],
  ["fish_script", "Fish Script（配音稿，可留空）", 6],
  ["monologue_text", "独白轨原文（Monologue Text，可留空）", 6],
  ["monologue_script", "独白轨配音稿（Monologue Script，可留空）", 6],
  ["podcast_text", "播客轨原文（Podcast Text，A:/B: 逐行对话）", 8],
  ["podcast_script", "播客轨配音稿（Podcast Script，可留空）", 8],
];

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    toast("已复制到剪贴板");
  } catch (_) {
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand("copy"); toast("已复制到剪贴板"); }
    catch (e) { toast("复制失败，请手动复制"); }
    ta.remove();
  }
}

function mgStatusPill(it) {
  if (it.error) return `<span class="mg-pill err" title="${esc(it.error)}">错误</span>`;
  if (it.stale) return `<span class="mg-pill warn" title="文本已更新，音频待重新生成">待更新</span>`;
  if (it.status === "generated") return `<span class="mg-pill ok">已生成</span>`;
  if (it.status === "ready") return `<span class="mg-pill">待生成</span>`;
  return `<span class="mg-pill">空</span>`;
}

async function ManageView(token) {
  if (ManageState.pollTimer) {
    clearInterval(ManageState.pollTimer);
    ManageState.pollTimer = null;
  }
  $app.innerHTML = `<p style="color:var(--text-sub);padding:40px;">加载工作台中…</p>`;
  let settings, topics, health;
  try {
    settings = await api("GET", "/api/settings");
    topics = await api("GET", "/api/topics");
    health = await api("GET", "/api/health").catch(() => null);
  } catch (e) {
    if (viewStale(token)) return;
    $app.innerHTML = `<p style="color:var(--text-sub);padding:40px;">加载失败：${esc(e.message)}</p>`;
    return;
  }
  if (viewStale(token)) return;

  const modelOpts = (settings.models || [])
    .map(m => `<option value="${esc(m)}" ${m === settings.model ? "selected" : ""}>${esc(m)}</option>`)
    .join("");
  const modeBadge = health
    ? `<span class="mg-pill ${health.mode === "live" ? "ok" : "warn"}">${health.mode === "live" ? "LIVE" : "DRY-RUN"}</span>
       <span class="mg-hint">ffmpeg: ${esc(health.ffmpeg.ok ? "可用" : health.ffmpeg.message)}</span>`
    : "";

  $app.innerHTML = `
    <div class="section-header settings-page-head">
      <div>
        <div class="section-title">设置与内容管理</div>
        <p class="section-description">先选择长期模仿音色；技术参数只在需要排错时调整。</p>
      </div>
      <div>${modeBadge}</div>
    </div>
    <div class="manage-grid">
      <div class="mg-col">
        <!-- 设置卡片 -->
        <div class="mg-card">
          <div class="voice-setting-lead">
            <div>
              <h3>提问与回答音色</h3>
              <p>当前回答使用男声，提问使用女声。试听后再固定长期模仿对象。</p>
            </div>
            <a class="mg-btn primary" href="#/voices">选择音色</a>
          </div>
          <details class="mg-advanced">
            <summary>高级生成设置</summary>
            <form id="mg-settings-form">
            <label class="mg-label">fish.audio API Key ${settings.fish_api_key_set ? '<span class="mg-chip">已配置（留空 = 不变）</span>' : ""}
              <input class="mg-input" type="password" id="mg-s-key" value="" placeholder="${settings.fish_api_key_set ? "已保存（输入新值可替换）" : "留空即 dry-run 模式"}" autocomplete="off">
            </label>
            <label class="mg-label">音色 A Reference ID（独白 / 对话中的 A 声）
              <input class="mg-input" id="mg-s-refa" value="${esc(settings.reference_id || "")}">
            </label>
            <label class="mg-label">音色 B Reference ID（可选：对话中的 B 声，留空按单音色）
              <input class="mg-input" id="mg-s-refb" value="${esc(settings.reference_id_b || "")}">
            </label>
            <div class="mg-row2">
              <label class="mg-label">模型
                <select class="mg-input" id="mg-s-model">${modelOpts}</select>
              </label>
              <label class="mg-label">语速
                <input class="mg-input" type="number" step="0.05" min="0.8" max="2" id="mg-s-speed" value="${esc(String(settings.speed ?? 1.0))}">
              </label>
            </div>
            <div class="mg-row2">
              <label class="mg-label">temperature（0–1，留空=服务默认）
                <input class="mg-input" type="number" step="0.01" min="0" max="1" id="mg-s-temp" value="${settings.temperature == null ? "" : esc(String(settings.temperature))}">
              </label>
              <label class="mg-label">分段字符数
                <input class="mg-input" type="number" min="100" id="mg-s-seg" value="${esc(String(settings.segment_chars ?? 700))}">
              </label>
            </div>
            <div class="mg-row2">
              <label class="mg-label">段间停顿 (ms)
                <input class="mg-input" type="number" min="0" id="mg-s-gap" value="${esc(String(settings.gap_ms ?? 350))}">
              </label>
              <label class="mg-label">整集条目间停顿 (ms)
                <input class="mg-input" type="number" min="0" id="mg-s-egap" value="${esc(String(settings.episode_gap_ms ?? 600))}">
              </label>
            </div>
            <label class="mg-check"><input type="checkbox" id="mg-s-dry" ${settings.dry_run ? "checked" : ""}> 强制 dry-run（生成占位音频，不调用 API）</label>
            <div class="mg-actions">
              <button type="submit" class="mg-btn primary">保存设置</button>
              <button type="button" class="mg-btn" id="mg-test-btn">测试连接</button>
              <span class="mg-hint" id="mg-test-result"></span>
            </div>
            </form>
          </details>
        </div>

        <!-- 话题卡片 -->
        <div class="mg-card">
          <h3>话题与语料</h3>
          <div class="mg-inline">
            <input class="mg-input grow" id="mg-new-topic" placeholder="新话题名称，如：03-travel">
            <button class="mg-btn primary" id="mg-create-topic">新建</button>
          </div>
          <div id="mg-topic-list" class="mg-topic-list"></div>
        </div>
      </div>

      <div class="mg-col mg-col-wide">
        <div class="mg-card" id="mg-topic-panel">
          <p style="color:var(--text-sub);">← 先在左侧选择或新建一个话题</p>
        </div>
      </div>
    </div>
  `;

  // ---- 设置表单 ----
  document.getElementById("mg-settings-form").onsubmit = async (e) => {
    e.preventDefault();
    const tempRaw = document.getElementById("mg-s-temp").value.trim();
    const payload = {
      fish_api_key: document.getElementById("mg-s-key").value,
      reference_id: document.getElementById("mg-s-refa").value.trim(),
      reference_id_b: document.getElementById("mg-s-refb").value.trim(),
      model: document.getElementById("mg-s-model").value,
      speed: parseFloat(document.getElementById("mg-s-speed").value) || 1.0,
      segment_chars: parseInt(document.getElementById("mg-s-seg").value, 10) || 700,
      gap_ms: parseFloat(document.getElementById("mg-s-gap").value) || 0,
      episode_gap_ms: parseFloat(document.getElementById("mg-s-egap").value) || 0,
      dry_run: document.getElementById("mg-s-dry").checked,
    };
    if (tempRaw !== "") payload.temperature = parseFloat(tempRaw);
    try {
      await api("PUT", "/api/settings", payload);
      toast("设置已保存");
    } catch (err) {
      toast("保存失败：" + err.message);
    }
  };
  document.getElementById("mg-test-btn").onclick = async () => {
    const $r = document.getElementById("mg-test-result");
    $r.textContent = "测试中…";
    try {
      const r = await api("POST", "/api/settings/test");
      const fish = r.fish || {};
      $r.textContent = `ffmpeg ${r.ffmpeg.ok ? "✓" : "✗"} · fish ${fish.ok ? "✓" : "✗"} ${fish.message || ""}`;
    } catch (err) {
      $r.textContent = "失败：" + err.message;
    }
  };

  // ---- 话题 ----
  document.getElementById("mg-create-topic").onclick = async () => {
    const $inp = document.getElementById("mg-new-topic");
    const name = $inp.value.trim();
    if (!name) return toast("请输入话题名称");
    try {
      const t = await api("POST", "/api/topics", { name });
      $inp.value = "";
      toast(`话题「${t.name}」已创建`);
      ManageState.topicId = t.id;
      ManageView();
    } catch (err) {
      toast("创建失败：" + err.message);
    }
  };
  mgRenderTopicList(topics);

  if (ManageState.topicId && topics.some(t => t.id === ManageState.topicId)) {
    mgLoadTopic(ManageState.topicId);
  }
  if (ManageState.job) {
    const box = document.getElementById("mg-job-box");
    if (box) mgStartPolling(ManageState.job.id);
  }
}

function mgRenderTopicList(topics) {
  const $list = document.getElementById("mg-topic-list");
  if (!$list) return;
  $list.innerHTML = topics.map(t => `
    <div class="mg-topic-row ${t.id === ManageState.topicId ? "active" : ""}" data-id="${esc(t.id)}">
      <div class="mg-topic-main">
        <div class="mg-topic-name">${esc(t.name)}</div>
        <div class="mg-hint">${t.stats.total} 条 · 已生成 ${t.stats.generated} · 待生成 ${t.stats.ready + t.stats.empty} · 共 ${fmtDur(t.total_sec)}</div>
      </div>
      <button class="mg-btn tiny danger" data-del="${esc(t.id)}" title="删除话题">🗑</button>
    </div>
  `).join("") || `<p class="mg-hint">还没有话题</p>`;

  $list.querySelectorAll(".mg-topic-row").forEach(row => {
    row.onclick = (e) => {
      if (e.target.closest("[data-del]")) return;
      ManageState.topicId = row.dataset.id;
      $list.querySelectorAll(".mg-topic-row").forEach(r => r.classList.toggle("active", r === row));
      mgLoadTopic(ManageState.topicId);
    };
  });
  $list.querySelectorAll("[data-del]").forEach(btn => {
    btn.onclick = async () => {
      const tid = btn.dataset.del;
      if (!confirm(`确定删除该话题及其全部条目与整集音频？`)) return;
      try {
        await api("DELETE", `/api/topics/${encodeURIComponent(tid)}`);
        if (ManageState.topicId === tid) ManageState.topicId = null;
        toast("话题已删除");
        ManageView();
      } catch (e) {
        toast("删除失败：" + e.message);
      }
    };
  });
}

async function mgLoadTopic(topicId, keepEditorClosed = false, token = null) {
  const $panel = document.getElementById("mg-topic-panel");
  if (!$panel) return;
  $panel.innerHTML = `<p style="color:var(--text-sub);">加载话题中…</p>`;
  let topic;
  try {
    topic = await api("GET", `/api/topics/${encodeURIComponent(topicId)}`);
  } catch (e) {
    if (token !== null && viewStale(token)) return;
    $panel.innerHTML = `<p style="color:var(--text-sub);">加载失败：${esc(e.message)}</p>`;
    return;
  }
  if (token !== null && viewStale(token)) return;

  $panel.innerHTML = `
    <h3>🎬 ${esc(topic.name)}</h3>
    <div class="mg-inline">
      <select class="mg-input" id="mg-gen-track">
        <option value="all">全部轨道</option>
        <option value="podcast">播客轨</option>
        <option value="monologue">独白轨</option>
        <option value="default">默认轨</option>
      </select>
      <label class="mg-check"><input type="checkbox" id="mg-gen-force"> 强制重新生成</label>
      <button class="mg-btn primary" id="mg-gen-topic">⚡ 批量生成音频</button>
    </div>
    <div class="mg-inline">
      <button class="mg-btn" id="mg-ep-pod">🎬 合成播客整集</button>
      <button class="mg-btn" id="mg-ep-mono">🎬 合成独白整集</button>
      <button class="mg-btn" id="mg-export-pod-m4b">📚 导出 M4B（播客）</button>
      <button class="mg-btn" id="mg-export-srt">🎞 导出 SRT 字幕（当前条目）</button>
      <button class="mg-btn" id="mg-export-pack">📱 导出手机语料包（全部话题）</button>
    </div>
    <div id="mg-job-box"></div>
    <div class="mg-divider"></div>
    <div class="mg-inline">
      <input class="mg-input grow" id="mg-new-q" placeholder="新条目的问题，如：Do you work or are you a student?">
      <button class="mg-btn" id="mg-create-item">新建条目</button>
    </div>
    <div class="mg-inline">
      <textarea class="mg-input grow" id="mg-bulk" rows="2" placeholder="批量粘贴题目，每行一个"></textarea>
      <button class="mg-btn" id="mg-bulk-btn">批量创建</button>
    </div>
    <div id="mg-item-list"></div>
    <div id="mg-editor"></div>
  `;

  document.getElementById("mg-gen-topic").onclick = async () => {
    const track = document.getElementById("mg-gen-track").value;
    const force = document.getElementById("mg-gen-force").checked;
    try {
      const r = await api("POST", `/api/topics/${encodeURIComponent(topicId)}/generate`, { force, track });
      toast(`已开始批量生成（${r.total} 条）`);
      mgStartPolling(r.job_id);
    } catch (e) {
      toast("启动失败：" + e.message);
    }
  };
  document.getElementById("mg-ep-pod").onclick = () => mgAssemble(topicId, "podcast");
  document.getElementById("mg-export-pod-m4b").onclick = async () => {
    try {
      const r = await api("POST", `/api/topics/${encodeURIComponent(topicId)}/export/m4b?track=podcast`);
      toast(`M4B 已导出（${Math.round(r.size / 1024)} KB）→ data/exports/`);
    } catch (e) { toast("导出失败：" + e.message); }
  };
  document.getElementById("mg-export-srt").onclick = async () => {
    const iid = ManageState.topicId && document.querySelector("#mg-item-list [data-edit]");
    if (!iid) { toast("请先选择条目（编辑其一）"); return; }
    try {
      const cur = ManageState.editingItemId;
      if (!cur) { toast("请先打开某条目的编辑器"); return; }
      const r = await api("POST", `/api/topics/${encodeURIComponent(topicId)}/items/${encodeURIComponent(cur)}/export/srt?track=podcast`);
      toast(`SRT 已导出 → ${r.file}`);
    } catch (e) { toast("导出失败：" + e.message); }
  };
  document.getElementById("mg-ep-mono").onclick = () => mgAssemble(topicId, "monologue");
  document.getElementById("mg-export-pack").onclick = () => {
    window.open("/api/pack/export", "_blank");
    toast("语料包生成中——下载完成后传到手机，或手机端直接局域网拉取");
  };

  document.getElementById("mg-create-item").onclick = async () => {
    const $q = document.getElementById("mg-new-q");
    const q = $q.value.trim();
    if (!q) return toast("请输入问题");
    try {
      await api("POST", `/api/topics/${encodeURIComponent(topicId)}/items`, { question: q });
      toast("条目已创建");
      mgLoadTopic(topicId);
    } catch (e) {
      toast("创建失败：" + e.message);
    }
  };
  document.getElementById("mg-bulk-btn").onclick = async () => {
    const text = document.getElementById("mg-bulk").value.trim();
    if (!text) return toast("请先粘贴题目");
    try {
      const r = await api("POST", `/api/topics/${encodeURIComponent(topicId)}/items/bulk`, { text });
      toast(`已创建 ${r.created} 个条目`);
      mgLoadTopic(topicId);
    } catch (e) {
      toast("批量创建失败：" + e.message);
    }
  };

  const $list = document.getElementById("mg-item-list");
  $list.innerHTML = topic.items.map(it => `
    <div class="mg-item-row" data-id="${esc(it.id)}">
      <div class="mg-item-main">
        <div class="mg-item-title">${esc(it.title)}</div>
        <div class="mg-hint">${mgStatusPill(it)} ${it.duration_sec ? "· " + fmtDur(it.duration_sec) : ""}</div>
      </div>
      <div class="mg-item-actions">
        <button class="mg-btn tiny" data-edit="${esc(it.id)}">编辑</button>
        <button class="mg-btn tiny" data-gen="${esc(it.id)}">⚡ 生成</button>
        <button class="mg-btn tiny danger" data-del-item="${esc(it.id)}">🗑</button>
      </div>
    </div>
  `).join("") || `<p class="mg-hint">该话题暂无条目</p>`;

  $list.querySelectorAll("[data-edit]").forEach(btn => {
    btn.onclick = () => mgOpenEditor(topicId, btn.dataset.edit);
  });
  $list.querySelectorAll("[data-gen]").forEach(btn => {
    btn.onclick = async () => {
      const track = document.getElementById("mg-gen-track").value;
      const force = document.getElementById("mg-gen-force").checked;
      try {
        const r = await api("POST", `/api/topics/${encodeURIComponent(topicId)}/items/${encodeURIComponent(btn.dataset.gen)}/generate`, { force, track });
        toast("已开始生成");
        mgStartPolling(r.job_id);
      } catch (e) {
        toast("生成失败：" + e.message);
      }
    };
  });
  $list.querySelectorAll("[data-del-item]").forEach(btn => {
    btn.onclick = async () => {
      if (!confirm("确定删除该条目（含音频）？")) return;
      try {
        await api("DELETE", `/api/topics/${encodeURIComponent(topicId)}/items/${encodeURIComponent(btn.dataset.delItem)}`);
        toast("条目已删除");
        mgLoadTopic(topicId);
      } catch (e) {
        toast("删除失败：" + e.message);
      }
    };
  });
}

async function mgOpenEditor(topicId, itemId) {
  ManageState.editingItemId = itemId;
  const $editor = document.getElementById("mg-editor");
  if (!$editor) return;
  $editor.innerHTML = `<p class="mg-hint">加载条目中…</p>`;
  let item;
  try {
    item = await api("GET", `/api/topics/${encodeURIComponent(topicId)}/items/${encodeURIComponent(itemId)}`);
  } catch (e) {
    $editor.innerHTML = `<p class="mg-hint">加载失败：${esc(e.message)}</p>`;
    return;
  }

  $editor.innerHTML = `
    <div class="mg-divider"></div>
    <div class="mg-editor-head">
      <h4>✏️ 编辑条目</h4>
      <div class="mg-actions">
        <button class="mg-btn tiny" id="mg-copy-rewrite">📋 复制改写请求</button>
        <button class="mg-btn tiny" id="mg-copy-voice">🎚 复制配音请求</button>
        <button class="mg-btn tiny" id="mg-preview-item">▶ 试听</button>
      </div>
    </div>
    ${MG_FIELDS.map(([f, label, rows]) => `
      <label class="mg-label">${label}
        <textarea class="mg-input" id="mg-f-${f}" rows="${rows}">${esc(item[f] || "")}</textarea>
      </label>
    `).join("")}
    <div class="mg-actions">
      <button class="mg-btn primary" id="mg-save-item">保存</button>
      <button class="mg-btn" id="mg-close-editor">收起</button>
      <span class="mg-hint" id="mg-save-result"></span>
    </div>
  `;
  $editor.scrollIntoView({ behavior: "smooth", block: "nearest" });

  document.getElementById("mg-close-editor").onclick = () => { $editor.innerHTML = ""; };
  document.getElementById("mg-save-item").onclick = async () => {
    const fields = {};
    for (const [f] of MG_FIELDS) fields[f] = document.getElementById(`mg-f-${f}`).value;
    try {
      await api("PATCH", `/api/topics/${encodeURIComponent(topicId)}/items/${encodeURIComponent(itemId)}`, fields);
      document.getElementById("mg-save-result").textContent = "已保存 ✓";
      toast("条目已保存");
      mgLoadTopic(topicId);
    } catch (e) {
      document.getElementById("mg-save-result").textContent = "保存失败：" + e.message;
    }
  };
  document.getElementById("mg-copy-rewrite").onclick = async () => {
    try {
      const r = await api("GET", `/api/topics/${encodeURIComponent(topicId)}/items/${encodeURIComponent(itemId)}/rewrite-request`);
      copyText(r.text);
    } catch (e) { toast("获取失败：" + e.message); }
  };
  document.getElementById("mg-copy-voice").onclick = async () => {
    try {
      const r = await api("GET", `/api/topics/${encodeURIComponent(topicId)}/items/${encodeURIComponent(itemId)}/voice-direct-request`);
      copyText(r.text);
    } catch (e) { toast("获取失败：" + e.message); }
  };
  document.getElementById("mg-preview-item").onclick = () => {
    location.hash = `#/play/${encodeURIComponent(topicId)}/${encodeURIComponent(itemId)}`;
  };
}

async function mgAssemble(topicId, track) {
  const btnId = track === "podcast" ? "mg-ep-pod" : "mg-ep-mono";
  const btn = document.getElementById(btnId);
  const label = btn ? btn.textContent : "合成";
  try {
    if (btn) { btn.disabled = true; btn.textContent = "合成中…"; }
    const r = await api("POST", `/api/topics/${encodeURIComponent(topicId)}/episode?track=${track}`);
    if (r.already_running) { toast("已有合成任务进行中"); return; }
    // 后台任务：轮询到完成
    const job = await new Promise((resolve, reject) => {
      const timer = setInterval(async () => {
        try {
          const j = await api("GET", `/api/jobs/${r.job_id}`);
          if (j.state !== "running") { clearInterval(timer); resolve(j); }
        } catch (e) { clearInterval(timer); reject(e); }
      }, 1200);
    });
    if (job.state === "error" || (job.errors && job.errors.length)) {
      toast("合成失败：" + (job.errors[0] || {}).message, "err");
    } else {
      const m = job.result || {};
      toast(`整集已合成：${m.item_count ?? "?"} 条 · ${fmtDur(m.total_sec || 0)}`);
      mgLoadTopic(topicId);
    }
  } catch (e) {
    toast("合成失败：" + e.message, "err");
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = label; }
  }
}

function mgStartPolling(jobId) {
  if (ManageState.pollTimer) clearInterval(ManageState.pollTimer);
  let consecutiveErrors = 0;
  const tick = async () => {
    // 已离开工作台 → 停止轮询（修审计 A22 定时器泄漏）
    if (!location.hash.startsWith("#/manage")) {
      clearInterval(ManageState.pollTimer);
      ManageState.pollTimer = null;
      return;
    }
    let job;
    try {
      job = await api("GET", `/api/jobs/${jobId}`);
      consecutiveErrors = 0;
    } catch (e) {
      // 404 = 任务被清理或服务重启；连续失败 4 次（约 6 秒）停止轮询，避免永久空转
      consecutiveErrors += 1;
      if (consecutiveErrors >= 4) {
        clearInterval(ManageState.pollTimer);
        ManageState.pollTimer = null;
        toast("任务查询失败，已停止跟踪（可能服务已重启）");
        const box = document.getElementById("mg-job-box");
        if (box) box.innerHTML = `<div class="mg-hint">⚠️ 任务跟踪中断（服务可能重启过）。请刷新工作台。</div>`;
      }
      return;
    }
    ManageState.job = job;
    const box = document.getElementById("mg-job-box");
    if (!box) {
      if (job.state !== "running" && ManageState.pollTimer) {
        clearInterval(ManageState.pollTimer);
        ManageState.pollTimer = null;
      }
      return;
    }
    const pct = job.total ? Math.round((job.done / job.total) * 100) : 0;
    const stateText = {
      running: "⏳ 生成中", done: "✅ 已完成", cancelled: "已取消",
      error: "❌ 出错", interrupted: "⚠️ 已中断（服务重启）",
    }[job.state] || job.state;
    box.innerHTML = `
      <div class="mg-progress"><div class="mg-progress-fill" style="width:${pct}%"></div></div>
      <div class="mg-hint mg-job-line">
        <span>${stateText} · ${job.done}/${job.total}${job.current ? " · 当前: " + esc(job.current) : ""}</span>
        ${job.state === "running" ? `<button class="mg-btn tiny" id="mg-cancel-job">取消</button>` : ""}
      </div>
      ${job.errors.length ? `<div class="mg-errors">${job.errors.map(e => `<div>⚠️ ${esc(e.item_id)}：${esc(e.message)}</div>`).join("")}</div>` : ""}
    `;
    const cancelBtn = document.getElementById("mg-cancel-job");
    if (cancelBtn) cancelBtn.onclick = async () => {
      try { await api("POST", `/api/jobs/${jobId}/cancel`); toast("已请求取消任务"); }
      catch (e) { toast("取消失败：" + e.message); }
    };
    if (job.state !== "running") {
      if (ManageState.pollTimer) {
        clearInterval(ManageState.pollTimer);
        ManageState.pollTimer = null;
      }
      if (ManageState.topicId) mgLoadTopic(ManageState.topicId);
    }
  };
  tick();
  ManageState.pollTimer = setInterval(tick, 1500);
}

/* ---------------- 路由调度 ---------------- */

// 路由令牌：每次导航递增；视图的异步 continuation 写 DOM 前核对，
// 8. 雅思题库（B01）——URL 参数驱动：#/bank?part=&topic=&q=&page=&sel=
function bankParams() {
  const p = new URLSearchParams(location.hash.split("?")[1] || "");
  return {
    part: p.get("part") || "1",
    topic: p.get("topic") || "",
    set: p.get("set") || "",
    q: p.get("q") || "",
    page: parseInt(p.get("page") || "1", 10) || 1,
    sel: p.get("sel") || "",
  };
}

function bankGo(overrides) {
  const cur = bankParams();
  const next = { ...cur, ...overrides };
  const filterChanged = ["part", "topic", "set", "q"].some(
    (k) => overrides[k] !== undefined && overrides[k] !== cur[k]
  );
  if (filterChanged) next.page = 1;
  const qs = new URLSearchParams();
  qs.set("part", next.part);
  if (next.topic) qs.set("topic", next.topic);
  if (next.set) qs.set("set", next.set);
  if (next.q) qs.set("q", next.q);
  if (next.page > 1) qs.set("page", String(next.page));
  if (next.sel) qs.set("sel", next.sel);
  location.hash = `#/bank?${qs.toString()}`;
}

// 随机来一题（保持当前 part/topic 过滤，随机结果钉在作答卡展示）
let bankRandomPick = null;
async function bankRandomGo() {
  const p = bankParams();
  const query = `/api/bank/questions?part=${encodeURIComponent(p.part)}&random=1` +
    (p.topic ? `&topic=${encodeURIComponent(p.topic)}` : "") +
    (p.set ? `&set_filter=${encodeURIComponent(p.set)}` : "");
  try {
    const res = await api("GET", query);
    if (!res.items || !res.items.length) { toast("该筛选下没有题目"); return; }
    bankRandomPick = res.items[0];
    BankView(null); // 程序性重渲染（null 不受路由令牌约束）
  } catch (e) {
    toast(`随机取题失败：${e.message}`);
  }
}

async function bankSubmitAnswer(questionId) {
  const input = document.getElementById("bank-answer-input");
  const btn = document.getElementById("bank-answer-submit");
  const answer = (input && input.value || "").trim();
  if (!answer) { toast("先写下你的回答（中文或英文都可以）"); return; }
  btn.disabled = true;
  btn.textContent = "提交中…";
  try {
    const res = await api("POST", "/api/bank/answer", { question_id: questionId, answer });
    toast(`已入库：话题「${res.topic_name}」`);
    location.hash = `#/topic/${encodeURIComponent(res.topic_id)}`;
  } catch (e) {
    toast(`提交失败：${e.message}`);
    btn.disabled = false;
    btn.textContent = "提交作答";
  }
}

async function BankView(token) {
  $app.innerHTML = `<p style="color:var(--text-sub);padding:40px;">加载雅思题库中…</p>`;
  const p = bankParams();
  let data;
  try {
    const query = `/api/bank/questions?part=${encodeURIComponent(p.part)}&page=${p.page}` +
      (p.topic ? `&topic=${encodeURIComponent(p.topic)}` : "") +
      (p.set ? `&set_filter=${encodeURIComponent(p.set)}` : "") +
      (p.q ? `&q=${encodeURIComponent(p.q)}` : "");
    data = await api("GET", query);
  } catch (e) {
    if (viewStale(token)) return;
    $app.innerHTML = `<p style="color:var(--text-sub);padding:40px;">题库加载失败：${esc(e.message)}</p>`;
    return;
  }
  if (viewStale(token)) return;

  if (!data.available) {
    $app.innerHTML = `
      <div class="hero-banner">
        <div class="hero-title">雅思题库</div>
        <div class="hero-desc">题库快照尚未导入。在项目目录运行 <code>python -m server.bank --sync</code>
        从 RoastDuck 导入题库后刷新本页。</div>
      </div>`;
    return;
  }

  const partTabs = [["1", "Part 1 · 日常问答"], ["2", "Part 2 · 独白描述"], ["3", "Part 3 · 深入讨论"]]
    .map(([v, label]) =>
      `<button class="bank-tab ${p.part === v ? "active" : ""}" onclick="bankGo({part: '${v}'})">${label}</button>`
    ).join("");

  const topicOptions = [`<option value="">全部话题（${data.total}）</option>`]
    .concat((data.topics || []).map(
      (t) => `<option value="${esc(t.id)}" ${p.topic === t.id ? "selected" : ""}>${esc(t.name_zh)}（${t.count}）</option>`
    )).join("");

  const setOptions = [`<option value="">全部考季（${data.total}）</option>`]
    .concat((data.sets || []).map(
      (s) => `<option value="${esc(s.id)}" ${(p.set || "") === s.id ? "selected" : ""}>${esc(s.name_zh)}（${s.count}）</option>`
    )).join("");

  const selItem = (p.sel && data.items.find((it) => it.id === p.sel)) || bankRandomPick;
  const packMode = typeof PackState !== "undefined" && PackState.active;
  const selJump = selItem && selItem.answered_item ? `
      <div class="bank-answer-actions" style="margin-top:12px;">
        ${selItem.answered_item.has_audio
          ? `<button class="bank-submit-btn" onclick="location.hash='#/play/${encodeURIComponent(selItem.answered_item.topic_id)}/${encodeURIComponent(selItem.answered_item.item_id)}'">▶ 去听已有的音频</button>`
          : `<button class="btn-pill" onclick="location.hash='#/topic/${encodeURIComponent(selItem.answered_item.topic_id)}'">查看已作答条目（还没有音频，需先生成）</button>`}
      </div>` : "";
  const answerCard = selItem ? `
    <div class="bank-answer-card">
      <div class="bank-answer-q">${esc(selItem.text)}</div>
      ${selItem.text_zh ? `<div class="bank-answer-zh">${esc(selItem.text_zh)}</div>` : ""}
      ${selItem.core ? `<div class="bank-row-meta" style="margin-top:8px;"><span class="bank-badge">必考题</span>${(selItem.set_labels || []).map((l) => `<span class="bank-topic-tag">${esc(l)}</span>`).join("")}</div>` : ""}
      ${selJump}
      ${packMode ? `<p class="bank-answer-hint">📱 APP 浏览模式：随机练题口头作答即可，提交作答请在电脑端进行。</p>` : `
      <textarea id="bank-answer-input" rows="6"
        placeholder="用中文或英文自由作答——说出你想表达的意思，母语者版本由 Agent 会话改写后生成音频"></textarea>
      <div class="bank-answer-actions">
        <button id="bank-answer-submit" class="bank-submit-btn" onclick="bankSubmitAnswer('${esc(selItem.id)}')">提交作答</button>
        <button class="btn-pill" onclick="bankGo({sel: ''})">收起</button>
      </div>
      <p class="bank-answer-hint">提交后条目进入话题「${esc(selItem.topic_name_en || selItem.topic_name)}」；
      改写与音频生成在工作台或 Agent 会话中完成。</p>`}
    </div>` : "";

  const rowsHtml = data.items.map((it) => `
    <div class="bank-row ${it.id === p.sel ? "selected" : ""}" onclick="bankGo({sel: '${esc(it.id)}'})">
      <div class="bank-row-text">${esc(it.text)}</div>
      <div class="bank-row-meta">
        <span class="bank-topic-tag">${esc(it.topic_name)}</span>
        ${it.has_audio ? `<span class="bank-badge">▶ 已有音频</span>` : (it.answered ? `<span class="bank-badge bank-badge-dim">已作答·未生成</span>` : "")}
        ${it.core ? `<span class="bank-part-tag">必考</span>` : ""}
        ${(it.set_labels || []).map((l) => `<span class="bank-topic-tag">${esc(l)}</span>`).join("")}
        ${it.part !== 1 ? `<span class="bank-part-tag">Part ${it.part}</span>` : ""}
      </div>
    </div>`).join("");

  const hasPrev = data.page > 1;
  const hasNext = data.page < data.pageCount;

  $app.innerHTML = `
    <div class="hero-banner">
      <div class="hero-title">雅思题库</div>
      <div class="hero-desc">选题 → 自由作答 → 母语者音频。题目来自本地 RoastDuck 题库快照。</div>
    </div>

    <div class="bank-toolbar">
      <div class="bank-tabs">${partTabs}</div>
      <select class="bank-select" onchange="bankGo({topic: this.value})">${topicOptions}</select>
      <select class="bank-select" onchange="bankGo({set: this.value})">${setOptions}</select>
      <div class="bank-search">
        <input id="bank-q" value="${esc(p.q)}" placeholder="搜索题干（中英文）"
          onkeydown="if(event.key==='Enter')bankGo({q: document.getElementById('bank-q').value.trim()})">
        <button class="btn-pill" onclick="bankGo({q: document.getElementById('bank-q').value.trim()})">搜索</button>
      </div>
      <button class="bank-tab bank-random" onclick="bankRandomGo()" title="从当前筛选中随机抽一题">随机来一题</button>
    </div>

    ${answerCard}

    <div class="bank-list">
      ${rowsHtml || `<p style="color:var(--text-sub);padding:24px 0;">没有匹配的题目</p>`}
    </div>

    ${data.pageCount > 0 ? `
    <div class="bank-pager">
      <button class="btn-pill" ${hasPrev ? "" : "disabled"} onclick="bankGo({page: ${data.page - 1}})">上一页</button>
      <span>第 ${data.page} / ${data.pageCount} 页 · 共 ${data.total} 题</span>
      <button class="btn-pill" ${hasNext ? "" : "disabled"} onclick="bankGo({page: ${data.page + 1}})">下一页</button>
    </div>` : ""}
  `;
}

// 9. 语料包导入管理（B02）：LAN 直传 / 文件导入 / 存档清除
async function packImportFromBuffer(buffer) {
  await packLoadBuffer(buffer);
  await packPersist(buffer);
  toast(`语料包导入成功：${PackState.manifest.counts.topics} 话题 / ${PackState.manifest.counts.items} 条目`);
  const prev = location.hash;
  location.hash = "#/topics";
  if (prev === location.hash) route(); // hash 未变不触发 hashchange，手动渲染
}

async function packImportFromServer(addrRaw) {
  const addr = (addrRaw || "").trim().replace(/\/+$/, "");
  if (!/^https?:\/\/.+/i.test(addr)) throw new Error("地址需以 http:// 开头，如 http://192.168.1.5:8765");
  const resp = await fetch(`${addr}/api/pack/export`);
  if (!resp.ok) throw new Error(`服务器返回 ${resp.status}（电脑端服务需以 --host 0.0.0.0 启动）`);
  await packImportFromBuffer(await resp.arrayBuffer());
}

async function packImportFromFile(file) {
  if (!file) return;
  await packImportFromBuffer(await file.arrayBuffer());
}

async function packClearAll() {
  await packDeletePersisted();
  packUnload();
  toast("已清除离线语料包");
  const prev = location.hash;
  location.hash = "#/import";
  if (prev === location.hash) route();
}

async function ImportView(token) {
  if (viewStale(token)) return;
  const info = PackState.active ? `
    <div class="bank-answer-card" style="border-color:var(--accent);">
      <div class="bank-answer-q">📦 当前离线语料包</div>
      <div class="bank-row-meta" style="margin-top:10px;">
        <span class="bank-topic-tag">${PackState.manifest.counts.topics} 话题</span>
        <span class="bank-topic-tag">${PackState.manifest.counts.items} 条目</span>
        <span class="bank-topic-tag">${PackState.bank ? "含题库" : "无题库"}</span>
        <span class="bank-topic-tag">指纹 ${esc(PackState.manifest.content_hash)}</span>
      </div>
      <p class="bank-answer-hint">导入于 ${esc(new Date(PackState.importedAt).toLocaleString())}。清除后回到在线模式。</p>
      <div class="bank-answer-actions">
        <button class="btn-pill" onclick="packClearAll()">清除离线包</button>
        <a class="btn-pill" href="#/topics" style="text-decoration:none;">去媒体库 →</a>
      </div>
    </div>` : `
    <div class="bank-answer-card">
      <div class="bank-answer-q">尚未导入语料包</div>
      <p class="bank-answer-hint">导入后无需网络即可离线收听，媒体库与播放页全部可用。</p>
    </div>`;

  $app.innerHTML = `
    <div class="hero-banner">
      <div class="hero-title">语料包管理</div>
      <div class="hero-desc">从电脑端拉取语料包（同一 Wi-Fi），或导入之前下载的 .zip 包文件。</div>
    </div>
    ${info}
    <div class="bank-answer-card">
      <div class="bank-answer-q">📶 方式一：局域网直传</div>
      <p class="bank-answer-hint">电脑端运行 <code>python run.py --host 0.0.0.0</code>，
      在下方输入它显示的地址（手机与电脑须同一 Wi-Fi）。</p>
      <div class="bank-search" style="margin-top:10px;">
        <input id="pack-addr" placeholder="http://192.168.1.5:8765"
          onkeydown="if(event.key==='Enter')packImportClick('lan')">
        <button class="bank-submit-btn" id="pack-lan-btn" onclick="packImportClick('lan')">拉取语料包</button>
      </div>
    </div>
    <div class="bank-answer-card">
      <div class="bank-answer-q">📁 方式二：导入 zip 文件</div>
      <p class="bank-answer-hint">电脑端「工作台管理」导出，或用任意方式（QQ/微信/USB）把 corpus.pack.zip 传到手机。</p>
      <div class="bank-answer-actions">
        <input type="file" id="pack-file" accept=".zip" style="display:none;" onchange="packImportClick('file')">
        <button class="bank-submit-btn" onclick="document.getElementById('pack-file').click()">选择文件导入</button>
      </div>
    </div>
  `;
}

async function packImportClick(kind) {
  const btn = document.getElementById(kind === "lan" ? "pack-lan-btn" : "pack-file");
  if (kind === "lan") btn.disabled = true, btn.textContent = "拉取中…";
  try {
    if (kind === "lan") {
      await packImportFromServer(document.getElementById("pack-addr").value);
    } else {
      await packImportFromFile(btn.files && btn.files[0]);
    }
  } catch (e) {
    toast(`导入失败：${e.message}`);
    if (kind === "lan") { btn.disabled = false; btn.textContent = "拉取语料包"; }
  }
}

// 过期即放弃写入（修审计 A21——快速导航时旧视图覆盖新视图）。
let routeToken = 0;
function currentRouteToken() {
  return routeToken;
}

// 视图统一入口：装载路由令牌并驱动视图
function mountView(viewFn) {
  const token = ++routeToken;
  viewFn(token);
}

// 异步视图安全写 DOM：令牌过期返回 true（调用方应立即 return）
function viewStale(token) {
  // null/undefined = 程序性重渲染（如操作后刷新面板），不受路由令牌约束
  return token != null && token !== routeToken;
}

function route() {
  const token = ++routeToken;
  const hash = location.hash || "#/bank";
  document.querySelectorAll(".nav-item").forEach(el => {
    const href = el.getAttribute("href");
    if (href === hash || (hash.startsWith("#/bank") && href === "#/bank")) {
      el.classList.add("active");
    } else {
      el.classList.remove("active");
    }
  });

  // 导航离开工作台时清理轮询定时器（修审计 A22）
  if (!hash.startsWith("#/manage") && ManageState.pollTimer) {
    clearInterval(ManageState.pollTimer);
    ManageState.pollTimer = null;
  }

  if (hash.startsWith("#/import")) {
    ImportView(token);
    return;
  }

  if (hash.startsWith("#/bank")) {
    BankView(token);
    return;
  }

  if (hash.startsWith("#/voices")) {
    VoicesShowcaseView(token);
    return;
  }

  if (hash.startsWith("#/manage")) {
    ManageView(token);
    return;
  }

  if (hash.startsWith("#/episode/")) {
    const parts = hash.slice(10).split("/");
    if (parts.length >= 2) {
      EpisodePlayerView(decodeURIComponent(parts[0]), decodeURIComponent(parts[1]));
      return;
    }
  }

  if (hash.startsWith("#/play/")) {
    const parts = hash.slice(7).split("/");
    if (parts.length >= 2) {
      TrackPlayerView(decodeURIComponent(parts[0]), decodeURIComponent(parts[1]), token);
      return;
    }
  }

  if (hash.startsWith("#/topic/")) {
    const tid = hash.slice(8);
    TopicDetailView(decodeURIComponent(tid), token);
    return;
  }

  TopicsGalleryView(token);
}

window.addEventListener("hashchange", route);
window.addEventListener("DOMContentLoaded", async () => {
  initGlobalPlayer();
  // APP 离线包恢复：IndexedDB 有存档则激活 pack 模式（失败静默按在线模式启动）
  if (typeof packRestore === "function") {
    await packRestore();
  }
  // 壳内（Capacitor APP）且无离线包：没有服务端可连，首屏直接落在语料包导入页
  const inAppShell = typeof window.Capacitor !== "undefined";
  if (inAppShell && !PackState.active) {
    document.body.classList.add("app-shell");
    if (!location.hash || location.hash === "#/" || location.hash === "#/topics") {
      location.hash = "#/import";
    }
  }
  route();
});
