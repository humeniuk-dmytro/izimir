"use strict";

const tg = window.Telegram ? window.Telegram.WebApp : null;
if (tg) {
  tg.ready();
  tg.expand();
}
const INIT_DATA = tg ? tg.initData : "";

function toast(msg) {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.classList.add("show");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.remove("show"), 2600);
}

async function api(path, options = {}) {
  const opts = Object.assign({ headers: {} }, options);
  opts.headers["Authorization"] = "tma " + INIT_DATA;
  if (opts.body) opts.headers["Content-Type"] = "application/json";
  const res = await fetch(path, opts);
  if (res.status === 403) {
    toast("Доступ только владельцу");
    throw new Error("forbidden");
  }
  if (!res.ok) {
    toast("Ошибка: " + res.status);
    throw new Error("http " + res.status);
  }
  return res.json();
}

const esc = (s) =>
  (s || "").replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));

// Open a link the Telegram way so it stays inside the app instead of bouncing
// to Telegram Desktop. Falls back to window.open in a plain browser.
function openTg(url) {
  if (!url) return;
  if (tg && tg.openTelegramLink && /^https:\/\/t\.me\//.test(url)) tg.openTelegramLink(url);
  else if (tg && tg.openLink) tg.openLink(url);
  else window.open(url, "_blank");
}

// --- tabs ---------------------------------------------------------------

const loaders = {};
document.querySelectorAll("nav#tabs button").forEach((btn) => {
  btn.onclick = () => {
    document.querySelectorAll("nav#tabs button").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    btn.classList.add("active");
    const id = btn.dataset.tab;
    document.getElementById(id).classList.add("active");
    if (loaders[id]) loaders[id]();
  };
});

// --- leads --------------------------------------------------------------

loaders.leads = async function () {
  const q = document.getElementById("leadSearch").value.trim();
  const data = await api("/api/leads?limit=200&q=" + encodeURIComponent(q));
  const box = document.getElementById("leadsList");
  if (!data.leads.length) {
    box.innerHTML = '<div class="empty">Лидов пока нет</div>';
    return;
  }
  box.innerHTML = data.leads
    .map((f) => {
      const author = f.author_username ? "@" + f.author_username : esc(f.author);
      const btns = [];
      if (f.msg_link)
        btns.push(`<button class="pill" data-url="${esc(f.msg_link)}">🔎 Сообщение</button>`);
      if (f.group_link)
        btns.push(`<button class="pill" data-url="${esc(f.group_link)}">👥 Группа</button>`);
      if (f.author_username)
        btns.push(`<button class="pill" data-url="https://t.me/${esc(f.author_username)}">✉ Автор</button>`);
      return `<div class="card">
        <div class="meta">👤 ${author} · 👥 ${esc(f.group_title)} · 🕒 ${esc((f.found_at || "").slice(0, 16).replace("T", " "))}</div>
        <div class="text">${esc(f.text)}</div>
        <div class="actions">${btns.join("")}</div>
      </div>`;
    })
    .join("");
  box.querySelectorAll(".pill").forEach((b) => {
    b.onclick = () => openTg(b.dataset.url);
  });
};

let searchTimer;
document.getElementById("leadSearch").oninput = () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(loaders.leads, 350);
};

// --- keywords -----------------------------------------------------------

loaders.keywords = async function () {
  const data = await api("/api/keywords");
  const box = document.getElementById("kwList");
  box.innerHTML =
    data.keywords
      .map(
        (k) =>
          `<div class="item"><span>${esc(k)}</span><button class="del" data-kw="${esc(k)}">✕</button></div>`
      )
      .join("") || '<div class="empty">Слов пока нет</div>';
  box.querySelectorAll(".del").forEach((b) => {
    b.onclick = async () => {
      await api("/api/keywords", { method: "DELETE", body: JSON.stringify({ keyword: b.dataset.kw }) });
      toast("Удалено");
      loaders.keywords();
    };
  });
};

document.getElementById("kwAdd").onclick = async () => {
  const inp = document.getElementById("kwInput");
  const kw = inp.value.trim();
  if (!kw) return;
  const r = await api("/api/keywords", { method: "POST", body: JSON.stringify({ keyword: kw }) });
  toast(r.added ? "Добавлено" : "Уже есть");
  inp.value = "";
  loaders.keywords();
};

// --- groups (via command queue) ----------------------------------------

loaders.groups = async function () {
  const data = await api("/api/groups");
  const box = document.getElementById("grpList");
  box.innerHTML =
    data.groups
      .map((g) => {
        const mark = g.is_active ? "✅" : "❌";
        return `<div class="item">
          <span>${mark} ${esc(g.group_title)}<br><span class="muted">${esc(g.group_link)}</span></span>
          <button class="del" data-link="${esc(g.group_link)}">✕</button>
        </div>`;
      })
      .join("") || '<div class="empty">Групп пока нет</div>';
  box.querySelectorAll(".del").forEach((b) => {
    b.onclick = async () => {
      const r = await api("/api/groups", { method: "DELETE", body: JSON.stringify({ link: b.dataset.link }) });
      toast("В очереди…");
      pollCommand(r.command_id, () => loaders.groups());
    };
  });
};

document.getElementById("grpAdd").onclick = async () => {
  const inp = document.getElementById("grpInput");
  const link = inp.value.trim();
  if (!link) return;
  const r = await api("/api/groups", { method: "POST", body: JSON.stringify({ link }) });
  toast("Добавляю группу…");
  inp.value = "";
  pollCommand(r.command_id, () => loaders.groups());
};

// --- stats --------------------------------------------------------------

const fmtTime = (iso) => (iso ? esc(iso.slice(0, 16).replace("T", " ")) : "—");

loaders.stats = async function () {
  const st = await api("/api/status");
  const ls = st.last_scan;
  const lastStr = ls
    ? `${fmtTime(ls.started_at)} · найдено ${ls.messages_found} · ${esc(ls.status)}`
    : "—";
  document.getElementById("statusBox").innerHTML = `
    <div class="item"><span>Групп</span><b>${st.groups}</b></div>
    <div class="item"><span>Ключевых слов</span><b>${st.keywords}</b></div>
    <div class="item"><span>Найдено всего</span><b>${st.total_found}</b></div>
    <div class="item"><span>Последний скан</span><span class="muted">${lastStr}</span></div>
    <div class="item"><span>Следующий скан</span><span class="muted">${fmtTime(st.next_scan)}</span></div>
    <div class="item"><span>Окно поиска</span><span class="muted">${st.scan_hours} ч</span></div>`;

  const s = await api("/api/stats");
  const byGroup = (s.by_group || [])
    .map(([t, c]) => `<div class="item"><span>${esc(t)}</span><b>${c}</b></div>`)
    .join("");
  document.getElementById("statsBox").innerHTML = `
    <div class="muted" style="margin:12px 4px 4px">📈 Лиды:</div>
    <div class="item"><span>Всего</span><b>${s.total}</b></div>
    <div class="item"><span>Сегодня</span><b>${s.today}</b></div>
    <div class="item"><span>За неделю</span><b>${s.week}</b></div>
    ${byGroup ? '<div class="muted" style="margin:8px 4px">По группам:</div>' + byGroup : ""}`;
};

// --- scan + queue polling ----------------------------------------------

async function pollCommand(id, onDone, tries = 0) {
  if (tries > 60) return;
  const cmd = await api("/api/command/" + id);
  if (cmd.status === "done" || cmd.status === "error") {
    toast((cmd.status === "done" ? "Готово: " : "Ошибка: ") + (cmd.result || ""));
    if (onDone) onDone();
    return;
  }
  setTimeout(() => pollCommand(id, onDone, tries + 1), 2000);
}

document.getElementById("scanBtn").onclick = async () => {
  const days = prompt("За сколько дней сканировать? (пусто = 24 часа)", "");
  const body = days && /^\d+$/.test(days) ? { days: parseInt(days, 10) } : {};
  const r = await api("/api/scan", { method: "POST", body: JSON.stringify(body) });
  toast("Сканирую…");
  pollCommand(r.command_id, () => loaders.leads());
};

document.getElementById("exportBtn").onclick = async () => {
  const r = await api("/api/export", { method: "POST", body: JSON.stringify({}) });
  toast("Готовлю CSV…");
  pollCommand(r.command_id);
};

document.getElementById("resetBtn").onclick = async () => {
  const r = await api("/api/reset_seen", { method: "POST", body: JSON.stringify({}) });
  toast("Сброшено: " + r.cleared);
};

// --- init ---------------------------------------------------------------

loaders.leads();
