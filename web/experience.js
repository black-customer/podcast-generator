/* Q04：页面呈现与操作反馈；不保存学习状态。 */
"use strict";

const ExperienceUI = (() => {
  let keyboardNavigation=false;
  document.addEventListener('pointerdown',()=>{keyboardNavigation=false;});
  document.addEventListener('keydown',event=>{
    if(event.key==='Tab' || event.key==='Enter' && !event.target.matches('input,textarea'))
      keyboardNavigation=true;
  });
  function focus(target) {
    if (!target) return;
    if (!target.matches("input,button,select,textarea,a")) target.tabIndex = -1;
    target.focus({ preventScroll: true });
    target.scrollIntoView({ block: "nearest", behavior: "instant" });
  }
  function loading(title) {
    $app.innerHTML = `<section class="view-state" aria-busy="true"><h1>${esc(title)}</h1>
      <p role="status">正在读取，请稍候…</p><div class="loading-lines" aria-hidden="true"></div></section>`;
  }
  function readError(title, error, retry = () => route(), target = $app) {
    target.inert = false;
    target.removeAttribute("aria-busy");
    target.innerHTML = `<section class="view-state"><h1>${esc(title)}</h1>
      <p role="alert">${esc(error.message || error)}。本次读取不会修改本机数据，可以重试。</p>
      <button type="button" class="study-button primary" id="view-retry">重新读取</button></section>`;
    target.querySelector("#view-retry").onclick = retry;
  }
  function liveTimer(node, started = Date.now()) {
    if (!node) return () => {};
    const update = () => {
      if (!node.isConnected) { clearInterval(timer); return; }
      node.textContent = `已用时 ${Math.max(0, Math.floor((Date.now() - started) / 1000))} 秒`;
    };
    const timer = setInterval(update, 1000);
    update();
    return () => clearInterval(timer);
  }
  function progressBar(host, initial, started = Date.now()) {
    host.innerHTML = `<div class="work-progress">
      <div class="work-progress-meta"><span role="status"></span>
      <span class="work-progress-values"><span data-progress-number></span>
      <span data-progress-time></span></span></div>
      <div class="work-progress-track" role="progressbar" aria-label="任务进度">
        <div class="work-progress-fill"></div>
      </div></div>`;
    const root = host.firstElementChild;
    const track = root.querySelector("[role=progressbar]");
    const status = root.querySelector("[role=status]");
    const number = root.querySelector("[data-progress-number]");
    const stop = liveTimer(root.querySelector("[data-progress-time]"), started);
    const set = (label, percent) => {
      if (status.textContent !== label) status.textContent = label;
      const known = Number.isFinite(percent);
      root.classList.toggle("indeterminate", !known);
      track.classList.toggle("indeterminate", !known);
      if (known) track.setAttribute("aria-valuenow", percent);
      else track.removeAttribute("aria-valuenow");
      track.style.setProperty("--work-progress", (known ? percent : 35) + "%");
      number.textContent = known ? `${percent}%` : "";
    };
    set(initial);
    return { set, stop };
  }
  function pendingNear(control, label) {
    if (!control) return () => {};
    const host = document.createElement("div");
    host.className = "work-progress-inline";
    (control.closest(".arcade-controls, .voice-card-actions, .role-controls") || control).after(host);
    control.classList.add("is-busy");
    const pending = progressBar(host, label);
    return () => { pending.stop(); host.remove(); control.classList.remove("is-busy"); };
  }
  async function busy(button, label, operation) {
    if (!button || button.disabled) return;
    const previous = button.textContent;
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    button.classList.add("is-busy");
    button.textContent = label;
    try { return await operation(); }
    finally {
      if (button.isConnected) {
        button.disabled = false;
        button.removeAttribute("aria-busy");
        button.classList.remove("is-busy");
        button.textContent = previous;
      }
    }
  }
  function recordingExtension(mime) {
    if (mime?.includes("mp4")) return "m4a";
    if (mime?.includes("ogg")) return "ogg";
    return "webm";
  }
  function recordingControls(root, phase, hasSaved = false) {
    const keys = root?.querySelector("[data-rec]") ? ["data-rec", "start", "stop", "save"]
      : ["data-oral", "record-start", "record-stop", "record-save"];
    if (!root) return;
    keys.slice(1).forEach((key, index) => {
      const button = root.querySelector(`[${keys[0]}='${key}']`);
      if (!button) return;
      const current = index === ({ ready: 0, recording: 1, stopped: 2 })[phase];
      button.classList.toggle("primary", current && !(phase === "ready" && hasSaved));
      button.hidden = (index === 0 && phase === "recording") || (index > 0 && !current);
      if (index === 0 && phase === "stopped" && typeof MobileRuntime !== 'undefined' && MobileRuntime.native) button.textContent = '重录一版';
    });
  }
  function memoReads() {
    const pending = new Map();
    return (url) => {
      if (!pending.has(url)) {
        const request = api("GET", url).catch(error => { pending.delete(url); throw error; });
        pending.set(url, request);
      }
      return pending.get(url);
    };
  }
  function guardAsync(root) {
    root.querySelectorAll("button,form").forEach(element => {
      if (element.matches("[data-oral],[data-act],[data-rec]")) return;
      const name = element.tagName === "FORM" ? "onsubmit" : "onclick";
      const original = element[name];
      if (!original || original.constructor.name !== "AsyncFunction" || original.experienceGuard) return;
      const wrapped = function(event) {
        if (name === "onsubmit") event.preventDefault();
        const button = name === "onsubmit" ? element.querySelector("button[type='submit']") : element;
        const label = button?.textContent.includes("保存") ? "正在保存…"
          : button?.textContent.includes("连接") ? "正在测试…" : "正在处理…";
        return busy(button, label, () => original.call(element, event)).catch(error => {
          let output = element.parentElement.querySelector(".action-error");
          if (!output) {
            output = document.createElement("p"); output.className = "action-error study-feedback";
            output.setAttribute("role", "alert"); element.after(output);
          }
          output.textContent = `操作未完成：${error.message}。本页内容仍保留，可以重试。`;
        });
      };
      wrapped.experienceGuard = true;
      element[name] = wrapped;
    });
  }
  const observer = new MutationObserver(records => {
    guardAsync($app);
    if (!keyboardNavigation || $app.querySelector('#training-root')) return;
    if (!records.some(record => record.target === $app && record.addedNodes.length)) return;
    if ($app.querySelector("[aria-busy='true']")) return;
    const target = $app.querySelector(".study-word") || $app.querySelector(".study-explanation h3")
      || $app.querySelector("h1, .section-title, .hero-title, .header-title");
    focus(target);
  });
  window.addEventListener("DOMContentLoaded", () => observer.observe($app, { childList: true, subtree: true }));
  return { focus, loading, readError, busy, recordingExtension, recordingControls, memoReads,
    liveTimer, progressBar, pendingNear };
})();
