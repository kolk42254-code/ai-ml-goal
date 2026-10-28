/* Small helpers shared by the shop page and the owner page. */
"use strict";

const Common = (() => {
  /* Build HTML elements safely. Text is always added as text (never as HTML),
     so a customer can't sneak code into the page through their name or message. */
  function h(tag, attrs = {}, ...children) {
    const el = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs)) {
      if (value === null || value === undefined || value === false) continue;
      if (key === "class") el.className = value;
      else if (key === "dataset") Object.assign(el.dataset, value);
      else if (key.startsWith("on") && typeof value === "function") el.addEventListener(key.slice(2), value);
      else if (value === true) el.setAttribute(key, "");
      else el.setAttribute(key, value);
    }
    for (const child of children.flat()) {
      if (child === null || child === undefined || child === false) continue;
      el.append(child instanceof Node ? child : String(child));
    }
    return el;
  }

  /* 1050 -> "₹1,050", 105000 -> "₹1,05,000" */
  const money = (amount) => "₹" + Number(amount).toLocaleString("en-IN");

  /* Talk to our server. Throws an Error with a readable message if something goes wrong. */
  async function api(path, { method = "GET", body } = {}) {
    let response;
    try {
      response = await fetch(path, {
        method,
        headers: body === undefined ? {} : { "Content-Type": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body),
        credentials: "same-origin",
      });
    } catch {
      throw Object.assign(new Error("No connection to the shop. Check your internet and try again."), { status: 0 });
    }
    let data = {};
    try { data = await response.json(); } catch { /* empty reply */ }
    if (!response.ok) {
      const message = typeof data.detail === "string" ? data.detail : "Please check the details and try again.";
      throw Object.assign(new Error(message), { status: response.status });
    }
    return data;
  }

  /* The server's clock is the one that counts (a phone or laptop clock can be wrong). */
  let clockOffset = 0;
  function syncClock(serverNowIso) {
    const serverNow = Date.parse(serverNowIso);
    if (!Number.isNaN(serverNow)) clockOffset = serverNow - Date.now();
  }
  const serverNow = () => Date.now() + clockOffset;

  /* 8040000 ms -> "2 h 14 min", 65000 -> "1 min 5 s" */
  function timeLeft(ms) {
    const total = Math.max(0, Math.floor(ms / 1000));
    const hours = Math.floor(total / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    const seconds = total % 60;
    if (hours >= 24) return `${Math.floor(hours / 24)} d ${hours % 24} h`;
    if (hours > 0) return `${hours} h ${minutes} min`;
    if (minutes > 0) return `${minutes} min ${seconds} s`;
    return `${seconds} s`;
  }

  /* An ISO time shown in India time, like "9:00 pm" */
  function clockText(iso) {
    return new Date(iso).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit", timeZone: "Asia/Kolkata" });
  }

  /* "5 min ago", "2 h ago", or a date */
  function ago(iso) {
    const minutes = Math.round((serverNow() - Date.parse(iso)) / 60000);
    if (minutes < 1) return "just now";
    if (minutes < 60) return `${minutes} min ago`;
    if (minutes < 24 * 60) return `${Math.floor(minutes / 60)} h ago`;
    return new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short", timeZone: "Asia/Kolkata" });
  }

  /* Browser storage can be blocked (private mode), so every use is wrapped. */
  const store = {
    get(key, fallback) {
      try { const raw = localStorage.getItem(key); return raw === null ? fallback : JSON.parse(raw); }
      catch { return fallback; }
    },
    set(key, value) {
      try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* storage blocked */ }
    },
  };

  let toastTimer;
  function toast(message, isError = false) {
    let el = document.getElementById("toast");
    if (!el) {
      el = h("div", { id: "toast", class: "toast", role: "status", "aria-live": "polite" });
      document.body.append(el);
    }
    el.textContent = message;
    el.classList.toggle("error", isError);
    el.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove("show"), 3200);
  }

  /* A picture of the item: the owner's photo, or the emoji on a plate. */
  function plate(product, className = "plate") {
    return h("div", { class: className, "aria-hidden": "true" },
      product.image ? h("img", { src: product.image, alt: "", loading: "lazy" }) : h("span", { class: "emoji" }, product.emoji || "🧁"));
  }

  return { h, money, api, syncClock, serverNow, timeLeft, clockText, ago, store, toast, plate };
})();
