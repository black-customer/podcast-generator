/* 桌面词书书架。 */

function progress({unseen, learning, mastered}) {
  const total = unseen + learning + mastered;
  return `<div class="deck-progress"><div class="deck-progress-track" aria-hidden="true">
    <span class="deck-mastered" style="flex:${mastered}"></span>
    <span class="deck-learning" style="flex:${learning}"></span>
    <span class="deck-unseen" style="flex:${unseen || Number(!total)}"></span></div>
    <p><span>已掌握 <b>${mastered}</b></span><span>学习中 <b>${learning}</b></span>
    <span>未学 <b>${unseen}</b></span></p></div>`;
}

const toggleLabel = book => book.enabled ? "暂停混练" : "加入混练";

function bookRow(book) {
  const {id, title, level_from, level_to, goal, basis, units, active_unit} = book;
  return `<article class="deck-book" data-deck="${esc(id)}">
    <div class="deck-book-intro">
      <h3>${esc(title)}</h3>
      <p class="deck-level">${esc(level_from)} → ${esc(level_to)}</p>
      <p>${esc(goal)}</p>
    </div>
    <div class="deck-book-actions">
      ${progress(book.progress)}
      ${units.length ? `<div class="arcade-controls">
        <button class="study-button primary" type="button" data-deck-start>开始学习</button>
        <button class="study-button" type="button" data-deck-toggle aria-pressed="${book.enabled}"
          aria-label="${book.enabled ? "暂停" : "启用"}${esc(title)}">${toggleLabel(book)}</button>
      </div>` : '<p class="arcade-muted">暂无可练的个人语块。</p>'}
    </div>
    ${units.length ? `<details class="deck-units">
      <summary>${units.length} 个单元</summary>
      <p class="arcade-muted">${esc(basis)}</p>
      <ul>${units.map(unit => `<li><div><strong>${esc(unit.title)}</strong>
        ${unit.id === active_unit ? '<small>当前单元</small>' : ""}
        <p>${esc(unit.goal)}</p></div>
        ${progress(unit.progress)}
        <button class="study-button" type="button" data-deck-start="${esc(unit.id)}"
          aria-label="练习${esc(unit.title)}">练习本单元</button></li>`).join("")}</ul></details>` : ""}
  </article>`;
}

async function open(token) {
  ExperienceUI.loading("口语词书");
  try {
    const data = await api("GET", "/api/decks");
    if (viewStale(token)) return;
    $app.innerHTML = `<div class="arcade-home deck-shelf">
      <header class="arcade-home-head"><div><h1>口语词书</h1>
      <p>选一本词书开口练。已加入的词书每天共安排最多 ${esc(data.daily_new_deck_cards)} 张新卡。</p>
      </div><a class="study-button" href="#/today">回今日练习</a></header>
      <p class="arcade-status" id="deck-status" role="status"></p>
      ${Object.entries(data.categories).map(([category, label]) => `<section class="deck-category"
        aria-labelledby="deck-category-${esc(category)}">
        <h2 id="deck-category-${esc(category)}">${esc(label)}</h2>
        <div>${data.decks.filter(book => book.category === category).map(bookRow).join("")}</div>
      </section>`).join("")}
    </div>`;
    $app.querySelector(".deck-shelf").onclick = async event => {
      const control = event.target.closest("[data-deck-toggle],[data-deck-start]");
      if (!control) return;
      const article = control.closest("[data-deck]");
      const book = data.decks.find(row => row.id === article.dataset.deck);
      const start = control.hasAttribute("data-deck-start");
      const status = document.getElementById("deck-status");
      const enabled = start || !book.enabled;
      const controls = article.querySelectorAll("button");
      controls.forEach(button => button.disabled = true);
      status.textContent = "";
      try {
        await api("POST", `/api/decks/${encodeURIComponent(book.id)}/toggle`, {
          enabled, ...(control.dataset.deckStart ? {unit_id: control.dataset.deckStart} : {}),
        });
        if (viewStale(token)) return;
        book.enabled = enabled;
        if (start) {
          const query = new URLSearchParams({deck: book.id});
          if (control.dataset.deckStart) query.set("unit", control.dataset.deckStart);
          location.hash = `#/today?${query}`;
          return;
        }
        control.textContent = toggleLabel(book);
        control.setAttribute("aria-pressed", String(enabled));
        control.setAttribute("aria-label", `${enabled ? "暂停" : "启用"}${book.title}`);
        status.textContent = enabled ? `已加入${book.title}。` : `已暂停${book.title}的混练。`;
      } catch (error) {
        if (!viewStale(token)) status.textContent = error.message;
      } finally { controls.forEach(button => button.disabled = false); }
    };
  } catch (error) {
    if (!viewStale(token)) ExperienceUI.readError("暂时无法读取口语词书", error, () => open(token));
  }
}

window.DecksUI = {open};
