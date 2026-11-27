/* 页面和样式脚本优先读取本机服务，离线时回落到缓存。 */
const CACHE = "ielts-pod-assets-v25";
const STATIC_ASSETS = [
  "/",
  "/static/app.js",
  "/static/experience.js",
  "/static/continuity.js",
  "/static/study.js",
  "/static/oral_review.js",
  "/static/training-core.js",
  "/static/training.js",
  "/static/arcade.js",
  "/static/radio.js",
  "/static/captures.js",
  "/static/training-baseline.js",
  "/static/training.css",
  "/static/ui-continuity.js",
  "/static/product-ui.css",
  "/static/style.css",
  "/static/packmode.js",
  "/static/packreader.js",
  "/static/mobile.js",
  "/static/mobile.css",
  "/manifest.webmanifest",
  "/static/icons/icon-32.png",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(STATIC_ASSETS)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (!["http:", "https:"].includes(url.protocol) || url.origin !== self.location.origin) return;
  if (event.request.method !== "GET") return;
  // API：仅网络（数据实时性优先；不提供从未真正写入的"失败回缓存"）
  if (url.pathname.startsWith("/api/")) {
    return;
  }
  const networkFirst = url.pathname === "/" || /^\/static\/.*\.(?:js|css)$/.test(url.pathname);
  const fresh = fetch(event.request, networkFirst ? {cache: "no-cache"} : undefined).then(response => ({
    response, copy: response.ok && response.type === "basic" ? response.clone() : null,
  }));
  event.waitUntil(fresh.then(async ({copy}) => {
    if (copy) await (await caches.open(CACHE)).put(event.request, copy);
  }).catch(() => {}));
  const cached = () => caches.match(event.request).catch(() => undefined);
  if (networkFirst) {
    event.respondWith(fresh.then(
      async ({response}) => response.ok ? response : (await cached()) || response,
      async error => {
        const fallback = await cached();
        if (fallback) return fallback;
        throw error;
      }));
  } else {
    event.respondWith(cached().then(result => result || fresh.then(({response}) => response)));
  }
});
