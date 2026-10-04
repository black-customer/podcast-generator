// packmode.js — APP 离线包模式数据层（B02）。
// 职责：包加载（zip → 内存索引 + blob 音频 URL）、IndexedDB 持久化、
// packApi（模拟服务端 /api 契约的子集）、mediaUrl（音频地址解析）。
// 视图与播放器代码零改动复用：app.js 的 api() 在 pack 模式下转发到这里。
"use strict";

const PackState = {
  active: false,
  manifest: null,
  bank: null,        // 题库快照（bank.json），无则 null
  topics: new Map(), // tid → {id, name, items: Map<iid, payload>}
  importedAt: "",
  _blobUrls: [],
};

// 与 server/bank.py norm_title 同构：小写、非词字符转空格、压空白
function packNormTitle(text) {
  return (text || "").toLowerCase()
    .replace(/[^\w\u4e00-\u9fff]+/g, " ")
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .join(" ");
}

// 局域网 HTTP 页面没有 SubtleCrypto，离线导入仍需按真实音频字节核对。
async function packAudioFingerprint(bytes) {
  if (globalThis.crypto?.subtle) {
    const hash = await crypto.subtle.digest("SHA-256", bytes);
    return [...new Uint8Array(hash)].map(b => b.toString(16).padStart(2, "0")).join("");
  }
  const constants = [], initial = [];
  for (let n = 2; constants.length < 64; n++) {
    let prime = true;
    for (let d = 2; d * d <= n; d++) if (n % d === 0) { prime = false; break; }
    if (!prime) continue;
    if (initial.length < 8) initial.push((Math.sqrt(n) % 1 * 0x100000000) | 0);
    constants.push((Math.cbrt(n) % 1 * 0x100000000) | 0);
  }
  const length = bytes.byteLength, padded = new Uint8Array(Math.ceil((length + 9) / 64) * 64);
  padded.set(new Uint8Array(bytes)); padded[length] = 0x80;
  const view = new DataView(padded.buffer);
  view.setUint32(padded.length - 8, Math.floor(length / 0x20000000));
  view.setUint32(padded.length - 4, length * 8);
  const rotate = (value, n) => (value >>> n) | (value << (32 - n));
  for (let offset = 0; offset < padded.length; offset += 64) {
    const words = new Int32Array(64);
    for (let i = 0; i < 16; i++) words[i] = view.getInt32(offset + i * 4);
    for (let i = 16; i < 64; i++) {
      const a = words[i - 15], b = words[i - 2];
      words[i] = words[i - 16] + (rotate(a, 7) ^ rotate(a, 18) ^ (a >>> 3)) +
        words[i - 7] + (rotate(b, 17) ^ rotate(b, 19) ^ (b >>> 10));
    }
    let [a, b, c, d, e, f, g, h] = initial;
    for (let i = 0; i < 64; i++) {
      const t1 = (h + (rotate(e, 6) ^ rotate(e, 11) ^ rotate(e, 25)) + ((e & f) ^ (~e & g)) + constants[i] + words[i]) | 0;
      const t2 = ((rotate(a, 2) ^ rotate(a, 13) ^ rotate(a, 22)) + ((a & b) ^ (a & c) ^ (b & c))) | 0;
      [a, b, c, d, e, f, g, h] = [(t1 + t2) | 0, a, b, c, (d + t1) | 0, e, f, g];
    }
    [a, b, c, d, e, f, g, h].forEach((value, i) => { initial[i] = (initial[i] + value) | 0; });
  }
  return initial.map(n => (n >>> 0).toString(16).padStart(8, "0")).join("");
}

async function packLoadBuffer(buffer) {
  const files = parsePackZip(buffer);
  const manifest = JSON.parse(files.get("pack.json").getText());
  if (![1, 2].includes(manifest.pack_version)) throw new Error("语料包版本不受支持，请保留原文件");
  PackState.manifest = manifest;
  PackState.bank = files.has("bank.json") ? JSON.parse(files.get("bank.json").getText()) : null;
  PackState.topics = new Map();
  for (const t of manifest.topics || []) {
    PackState.topics.set(t.id, { id: t.id, name: t.name, items: new Map() });
  }
  for (const [name, ent] of files) {
    const m = name.match(/^topics\/(.+)\/items\/(.+)\/(.+\.(?:json|mp3))$/);
    if (!m) continue;
    const tid = m[1], iid = m[2], fname = m[3];
    const topic = PackState.topics.get(tid);
    if (!topic) continue;
    if (fname === "item.json") {
      const payload = JSON.parse(ent.getText());
      payload.audioUrls = {};
      payload.audioFingerprints = {};
      for (const [track, audioName] of Object.entries(payload.audio || {})) {
        const audioEnt = files.get(`topics/${tid}/items/${iid}/${audioName}`);
        if (audioEnt) {
          const bytes = await audioEnt.getBlob().arrayBuffer();
          payload.audioFingerprints[track] = await packAudioFingerprint(bytes);
          const url = URL.createObjectURL(audioEnt.getBlob());
          payload.audioUrls[track] = url;
          PackState._blobUrls.push(url);
        }
      }
      topic.items.set(iid, payload);
    }
  }
  PackState.importedAt = new Date().toISOString();
  PackState.active = true;
  document.body.classList.add("pack-mode");
  return manifest;
}

function packUnload() {
  PackState._blobUrls.forEach((u) => URL.revokeObjectURL(u));
  PackState.active = false;
  PackState.manifest = null;
  PackState.bank = null;
  PackState.topics = new Map();
  PackState.importedAt = "";
  PackState._blobUrls = [];
  document.body.classList.remove("pack-mode");
}

// ---------- IndexedDB 持久化（存原始 zip，启动时重新解包到内存） ----------

function packIdb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open("ieltspod", 1);
    req.onupgradeneeded = () => {
      if (!req.result.objectStoreNames.contains("packs")) req.result.createObjectStore("packs");
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error || new Error("IndexedDB 打开失败"));
  });
}

async function packPersist(buffer) {
  const db = await packIdb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("packs", "readwrite");
    tx.objectStore("packs").put(buffer, "corpus");
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error || new Error("语料包保存失败"));
  });
}

async function packDeletePersisted() {
  const db = await packIdb();
  return new Promise((resolve) => {
    const tx = db.transaction("packs", "readwrite");
    tx.objectStore("packs").delete("corpus");
    tx.oncomplete = () => resolve();
    tx.onerror = () => resolve();
  });
}

// 启动恢复：有存档则激活 pack 模式（失败静默降级为 server 模式）
async function packRestore() {
  try {
    const db = await packIdb();
    const buffer = await new Promise((resolve, reject) => {
      const req = db.transaction("packs").objectStore("packs").get("corpus");
      req.onsuccess = () => resolve(req.result || null);
      req.onerror = () => reject(req.error);
    });
    if (buffer) await packLoadBuffer(buffer);
  } catch (e) {
    console.warn("语料包恢复失败，按在线模式启动：", e);
  }
}

// ---------- packApi：模拟 /api 契约子集（app.js 的 api() 在 pack 模式转发到此） ----------

function packTopicSummary(t) {
  let total = 0, empty = 0, ready = 0, generated = 0, error = 0, totalSec = 0;
  for (const it of t.items.values()) {
    total++;
    const hasAudio = Object.keys(it.audioUrls || {}).length > 0;
    const st = (it.meta && it.meta.status) || (hasAudio ? "generated" : "empty");
    if (st === "generated") generated++;
    else if (st === "ready") ready++;
    else empty++;
    if (it.meta && it.meta.error) error++;
    totalSec += (it.meta && it.meta.duration_sec) || 0;
  }
  return {
    id: t.id,
    name: t.name,
    stats: { total, empty, ready, generated, error },
    total_sec: Math.round(totalSec * 10) / 10,
  };
}

function packItemSummary(it) {
  const hasMono = !!(it.audioUrls && (it.audioUrls.monologue || it.audioUrls.default));
  const hasPod = !!(it.audioUrls && it.audioUrls.podcast);
  const hasAudio = hasMono || hasPod;
  return {
    id: it.id,
    title: it.title || it.id,
    status: ((it.meta && it.meta.status) || (hasAudio ? "generated" : "empty")),
    has_monologue: hasMono,
    has_podcast: hasPod,
    stale: !!(it.meta && it.meta.stale),
    error: (it.meta && it.meta.error) || "",
    duration_sec: (it.meta && it.meta.duration_sec) || null,
    duration_sec_podcast: (it.meta && it.meta.duration_sec_podcast) || null,
  };
}

function packTopicDetail(tid) {
  const t = PackState.topics.get(tid);
  if (!t) throw new Error("话题不在离线包中");
  return {
    id: t.id,
    name: t.name,
    items: [...t.items.values()].map(packItemSummary),
  };
}

function packItemFull(tid, iid) {
  const it = PackState.topics.get(tid) && PackState.topics.get(tid).items.get(iid);
  if (!it) throw new Error("条目不在离线包中");
  const summary = packItemSummary(it);
  const hasMono = summary.has_monologue;
  const hasPod = summary.has_podcast;
  return {
    ...summary,
    ...(it.texts || {}),
    has_audio: summary.has_monologue || summary.has_podcast,
    has_audio_monologue: hasMono,
    has_audio_podcast: hasPod,
    tts_mode: (it.meta && it.meta.tts_mode) || "",
  };
}

// 题库查询：与 server/bank.query_questions 同语义
// （part/topic/set 过滤、core 必考、中英搜索、分页、已作答徽标与条目跳转）
function packBankQuery(qs) {
  if (!PackState.bank) {
    return { available: false, items: [], total: 0, page: 1, pageCount: 0, topics: [], sets: [] };
  }
  const answered = new Map();
  for (const t of PackState.topics.values()) {
    for (const it of t.items.values()) {
      if (!it.title) continue;
      if (!Object.entries(it.texts || {}).some(([field, value]) =>
        ["original_answer", "chinese", "natural_english", "monologue_text", "podcast_text", "podcast_script"].includes(field) && String(value || "").trim())) continue;
      const key = packNormTitle(it.texts?.question || it.title);
      const audioUrls = it.audioUrls || {};
      const entry = {
        topic_id: t.id, item_id: it.id,
        created_at: Number.isFinite(Date.parse(it.meta?.created_at)) ? it.meta.created_at : "",
        has_audio: !!(audioUrls.monologue || audioUrls.podcast || audioUrls.default),
      };
      const prev = answered.get(key);
      const stamp = r => Date.parse(r.created_at) || -Infinity;
      if (!prev || stamp(entry) > stamp(prev) || (stamp(entry) === stamp(prev) &&
        JSON.stringify([entry.topic_id, entry.item_id]) > JSON.stringify([prev.topic_id, prev.item_id]))) answered.set(key, entry);
    }
  }
  const snap = PackState.bank;
  const part = qs.get("part") ? parseInt(qs.get("part"), 10) : null;
  const topicId = qs.get("topic") || null;
  const setFilter = qs.get("set_filter") || "";
  const needle = (qs.get("q") || "").trim().toLowerCase();
  const pageSize = Math.min(Math.max(parseInt(qs.get("page_size") || "20", 10) || 20, 1), 100);
  const topicById = new Map((snap.topics || []).map((t) => [t.id, t]));
  const bookById = new Map((snap.books || []).map((b) => [b.id, b]));

  // 必考话题（固定五件套，与 server/bank.CORE_TOPIC_NORMS 同步）
  const CORE_TOPIC_NORMS = new Set([
    "work or studies", "work or study", "work studies", "work study", "work",
    "home accommodation", "home or accommodation", "home", "accommodation",
    "hometown",
    "the area you live in", "area you live in",
    "the city you live in", "city you live in",
  ]);
  const coreTids = new Set(
    (snap.topics || [])
      .filter((t) => CORE_TOPIC_NORMS.has(packNormTitle(t.name_en || "")))
      .map((t) => t.id)
  );

  // qid -> 题集列表（含短标签），与 server/bank.set_index 同构
  const sets = snap.sets || [];
  for (const s of sets) s.short = `${s.start_month}–${s.end_month}月`;
  const qsets = new Map();
  for (const s of sets) {
    for (const qid of s.question_ids || []) {
      if (!qsets.has(qid)) qsets.set(qid, []);
      qsets.get(qid).push(s);
    }
  }

  const label = (row) => {
    const t = topicById.get(row.topic_id);
    if (t) return [t.name_zh, t.name_en || ""];
    const b = bookById.get(row.book_id);
    if (b) return [b.title_zh, b.title_en || ""];
    return ["未分类", ""];
  };

  const rows = [];
  for (const row of snap.questions || []) {
    if (part && row.part !== part) continue;
    if (topicId && row.topic_id !== topicId) continue;
    if (needle) {
      const inEn = (row.text || "").toLowerCase().includes(needle);
      const inZh = (row.text_zh || "").toLowerCase().includes(needle);
      if (!inEn && !inZh) continue;
    }
    const mySets = qsets.get(row.id) || [];
    const isCore = coreTids.has(row.topic_id);
    if (setFilter === "core" && !isCore) continue;
    if (setFilter && setFilter !== "core" && !mySets.some((s) => s.id === setFilter)) continue;
    const [nameZh, nameEn] = label(row);
    const answeredItem = answered.get(packNormTitle(row.text)) || null;
    const answerStatus = qs.get("answer_status") || "all";
    if (answerStatus === "answered" && !answeredItem) continue;
    if (answerStatus === "unanswered" && answeredItem) continue;
    rows.push({
      ...row,
      topic_name: nameZh,
      topic_name_en: nameEn,
      answered: !!answeredItem,
      has_audio: !!(answeredItem && answeredItem.has_audio),
      answered_item: answeredItem,
      set_labels: mySets.map((s) => s.short),
      core: isCore,
    });
  }
  const total = rows.length;
  if ((qs.get("random") === "1" || qs.get("random") === "true") && rows.length) {
    const index = Math.floor(Math.random() * rows.length), pick = rows[index];
    return { available: true, items: [pick], total, page: 1, pageCount: 1, page_size: 1,
      selected_page: Math.floor(index / pageSize) + 1, topics: [], sets: [] };
  }
  const pageCount = total ? Math.max(1, Math.ceil(total / pageSize)) : 0;
  let page = parseInt(qs.get("page") || "1", 10) || 1;
  if (total) page = Math.min(Math.max(1, page), pageCount);
  else page = 1;

  // 话题筛选器计数（按当前考季过滤）
  const counts = new Map();
  for (const row of snap.questions || []) {
    if (part && row.part !== part) continue;
    if (setFilter === "core" && !coreTids.has(row.topic_id)) continue;
    if (setFilter && setFilter !== "core" && !(qsets.get(row.id) || []).some((s) => s.id === setFilter)) continue;
    if (row.topic_id) counts.set(row.topic_id, (counts.get(row.topic_id) || 0) + 1);
  }
  const topics = (snap.topics || [])
    .filter((t) => counts.get(t.id))
    .map((t) => ({
      id: t.id, name_zh: t.name_zh, name_en: t.name_en || "",
      ielts_part: t.ielts_part, count: counts.get(t.id),
    }))
    .sort((a, b) => (a.ielts_part || 9) - (b.ielts_part || 9) || b.count - a.count);

  // 考季筛选器数据（当前 part 下的计数 + 必考）
  const partRows = (snap.questions || []).filter((r) => !part || r.part === part);
  const setsOut = [];
  for (const s of sets) {
    const n = partRows.filter((r) => (s.question_ids || []).includes(r.id)).length;
    if (n) setsOut.push({ id: s.id, name_zh: s.name_zh, short: s.short, count: n });
  }
  const coreN = partRows.filter((r) => coreTids.has(r.topic_id)).length;
  setsOut.push({ id: "core", name_zh: "必考题", short: "必考", count: coreN });

  return {
    available: true,
    items: rows.slice((page - 1) * pageSize, page * pageSize),
    total, page, pageCount, page_size: pageSize, topics, sets: setsOut,
  };
}

async function packApi(method, url) {
  const [rawPath, qsStr] = url.split("?");
  const path = rawPath.split("/").map(decodeURIComponent).join("/");
  const qs = new URLSearchParams(qsStr || "");
  if (method === "GET" && path === "/api/health") return { ok: true, mode: "pack" };
  if (method === "GET" && path === "/api/topics") {
    return [...PackState.topics.values()].map(packTopicSummary);
  }
  let m = path.match(/^\/api\/topics\/(.+)$/);
  if (method === "GET" && m && !m[1].includes("/")) return packTopicDetail(m[1]);
  m = path.match(/^\/api\/topics\/(.+)\/items\/(.+)$/);
  if (method === "GET" && m && !m[2].includes("/")) return packItemFull(m[1], m[2]);
  m = path.match(/^\/api\/topics\/(.+)\/items\/(.+)\/timeline\/(\w+)$/);
  if (method === "GET" && m) {
    const topic = PackState.topics.get(m[1]);
    const it = topic && topic.items.get(m[2]);
    const track = m[3] === "default" ? "podcast" : m[3];
    const tl = it && it.timelines && it.timelines[track];
    if (!tl) throw new Error("该条目暂无此音轨时间轴");
    return tl;
  }
  if (method === "GET" && path === "/api/bank/questions") return packBankQuery(qs);
  const answerMatch = path.match(/^\/api\/bank\/questions\/([^/]+)\/answers$/);
  if (method === "GET" && answerMatch) {
    const question = PackState.bank?.questions.find(q => q.id === answerMatch[1]);
    const answers = [];
    for (const topic of PackState.topics.values()) for (const item of topic.items.values()) {
      if (question && packNormTitle(item.texts?.question || item.title) === packNormTitle(question.text) &&
        ["original_answer", "chinese", "natural_english", "monologue_text", "podcast_text", "podcast_script"].some(f => String(item.texts?.[f] || "").trim()))
        answers.push({topic_id: topic.id, item_id: item.id, has_audio: Object.keys(item.audioUrls).length > 0,
          created_at: Number.isFinite(Date.parse(item.meta?.created_at)) ? item.meta.created_at : ""});
    }
    const stamp = r => Number.isFinite(Date.parse(r.created_at)) ? Date.parse(r.created_at) : -Infinity;
    answers.sort((a, b) => stamp(b) - stamp(a) || b.topic_id.localeCompare(a.topic_id) || b.item_id.localeCompare(a.item_id));
    return {answers};
  }
  if (method === "GET" && path === "/api/search") {
    const needle = (qs.get("q") || "").trim().toLowerCase(), results = [];
    for (const topic of PackState.topics.values()) for (const item of topic.items.values()) {
      const fields = [item.title, ...["question", "original_answer", "chinese", "natural_english", "monologue_text", "podcast_text", "podcast_script"].map(f => item.texts?.[f])];
      const matched = fields.find(text => needle && String(text || "").toLowerCase().includes(needle));
      if (matched) {
        const offset = Math.max(0, matched.toLowerCase().indexOf(needle) - 45);
        results.push({topic_id: topic.id, topic_name: topic.name, item_id: item.id, title: item.title,
          has_audio: Object.keys(item.audioUrls).length > 0, snippet: matched.slice(offset, offset + 180)});
      }
    }
    const size = Math.min(100, Math.max(1, Number(qs.get("page_size")) || 20));
    const pageCount = Math.ceil(results.length / size), page = Math.max(1, Math.min(Number(qs.get("page")) || 1, pageCount || 1));
    return {results: qs.has("page") ? results.slice((page - 1) * size, page * size) : results, total: results.length, page, pageCount};
  }
  throw new Error(`离线包模式不支持该操作：${method} ${path}`);
}

// 音频地址解析：server 模式原样返回；pack 模式解析到 blob URL（不支持返回 null）
function mediaUrl(path) {
  if (typeof MobileRuntime !== "undefined" && MobileRuntime.native) return MobileRuntime.mediaUrl(path);
  if (!PackState.active) return path;
  path = path.split("/").map(decodeURIComponent).join("/");
  const m = path.match(/^\/api\/topics\/(.+)\/items\/(.+)\/audio\/(\w+)$/);
  if (m) {
    const it = PackState.topics.get(m[1]) && PackState.topics.get(m[1]).items.get(m[2]);
    if (!it) return null;
    const urls = it.audioUrls || {};
    return urls[m[3]] || urls.default || urls.monologue || urls.podcast || null;
  }
  return null;
}

if (typeof window !== "undefined") {
  window.PackState = PackState;
  window.packLoadBuffer = packLoadBuffer;
  window.packUnload = packUnload;
  window.packPersist = packPersist;
  window.packDeletePersisted = packDeletePersisted;
  window.packRestore = packRestore;
  window.packApi = packApi;
  window.mediaUrl = mediaUrl;
}
