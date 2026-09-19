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

async function packLoadBuffer(buffer) {
  const files = parsePackZip(buffer);
  const manifest = JSON.parse(files.get("pack.json").getText());
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
      for (const [track, audioName] of Object.entries(payload.audio || {})) {
        const audioEnt = files.get(`topics/${tid}/items/${iid}/${audioName}`);
        if (audioEnt) {
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

// 题库查询：与 server/bank.query_questions 同语义（part/topic 过滤、中英搜索、分页、已作答徽标）
function packBankQuery(qs) {
  if (!PackState.bank) {
    return { available: false, items: [], total: 0, page: 1, pageCount: 0, topics: [] };
  }
  const answered = new Set();
  for (const t of PackState.topics.values()) {
    for (const it of t.items.values()) {
      if (it.title) answered.add(packNormTitle(it.title));
    }
  }
  const snap = PackState.bank;
  const part = qs.get("part") ? parseInt(qs.get("part"), 10) : null;
  const topicId = qs.get("topic") || null;
  const needle = (qs.get("q") || "").trim().toLowerCase();
  const pageSize = Math.min(Math.max(parseInt(qs.get("page_size") || "20", 10) || 20, 1), 100);
  const topicById = new Map((snap.topics || []).map((t) => [t.id, t]));
  const bookById = new Map((snap.books || []).map((b) => [b.id, b]));

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
    const [nameZh, nameEn] = label(row);
    rows.push({
      ...row,
      topic_name: nameZh,
      topic_name_en: nameEn,
      answered: answered.has(packNormTitle(row.text)),
    });
  }
  const total = rows.length;
  if ((qs.get("random") === "1" || qs.get("random") === "true") && rows.length) {
    const pick = rows[Math.floor(Math.random() * rows.length)];
    return { available: true, items: [pick], total, page: 1, pageCount: 1, page_size: 1, topics: [] };
  }
  const pageCount = total ? Math.max(1, Math.ceil(total / pageSize)) : 0;
  let page = parseInt(qs.get("page") || "1", 10) || 1;
  if (total) page = Math.min(Math.max(1, page), pageCount);
  else page = 1;

  // 话题筛选器计数
  const counts = new Map();
  for (const row of snap.questions || []) {
    if (part && row.part !== part) continue;
    if (row.topic_id) counts.set(row.topic_id, (counts.get(row.topic_id) || 0) + 1);
  }
  const topics = (snap.topics || [])
    .filter((t) => counts.get(t.id))
    .map((t) => ({
      id: t.id, name_zh: t.name_zh, name_en: t.name_en || "",
      ielts_part: t.ielts_part, count: counts.get(t.id),
    }))
    .sort((a, b) => (a.ielts_part || 9) - (b.ielts_part || 9) || b.count - a.count);

  return {
    available: true,
    items: rows.slice((page - 1) * pageSize, page * pageSize),
    total, page, pageCount, page_size: pageSize, topics,
  };
}

async function packApi(method, url) {
  const [path, qsStr] = url.split("?");
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
  throw new Error(`离线包模式不支持该操作：${method} ${path}`);
}

// 音频地址解析：server 模式原样返回；pack 模式解析到 blob URL（不支持返回 null）
function mediaUrl(path) {
  if (!PackState.active) return path;
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
