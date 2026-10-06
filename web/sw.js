/* Service Worker：静态资源缓存优先，API 网络优先（音频/数据保持新鲜）。 */
const CACHE = "ielts-pod-assets-v12";
const STATIC_ASSETS = [
  "/",
  "/static/app.js",
  "/static/experience.js",
  "/static/continuity.js",
  "/static/study.js",
  "/static/oral_review.js",
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
  if (event.request.method !== "GET") return;
  // API：仅网络（数据实时性优先；不提供从未真正写入的"失败回缓存"）
  if (url.pathname.startsWith("/api/")) {
    return;
  }
  // 静态资源：缓存优先，后台更新
  event.respondWith(
    caches.match(event.request).then((cached) => {
      const fresh = fetch(event.request)
        .then((res) => {
          if (res.ok) {
            const copy = res.clone();
            caches.open(CACHE).then((cache) => cache.put(event.request, copy));
          }
          return res;
        })
        .catch(() => cached);
      return cached || fresh;
    })
  );
});
