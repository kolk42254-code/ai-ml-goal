/* Look and feel for the shop page: the welcome greeting, the hero showcase, and button and card effects.
   It only decorates the page. Prices, the cart and orders stay in shop.js, so nothing here can break an order. */
"use strict";

(() => {
  const { h, money } = Common;
  const $ = (id) => document.getElementById(id);
  const calm = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const finePointer = () => window.matchMedia("(hover: hover) and (pointer: fine)").matches;

  // ---------------- welcome greeting (shop time, from the server's clock) ----------------

  function hourInIndia(iso) {
    const hour = new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Kolkata", hour: "numeric", hourCycle: "h23" })
      .format(new Date(iso));
    return Number(hour);
  }

  function greet(serverNowIso, shop) {
    const hour = hourInIndia(serverNowIso);
    const word = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
    const el = $("greet-time");
    if (el.textContent !== word) el.textContent = word;
    $("hero-shop").textContent = shop.shop_name;
  }

  /* "Hello" in the languages people in the shop's area speak. */
  const HELLOS = ["ನಮಸ್ಕಾರ", "नमस्ते", "Hello", "வணக்கம்", "నమస్కారం", "നമസ്കാരം"];
  let helloIndex = 0;
  let front = $("lang-a");
  let back = $("lang-b");
  function nextHello() {
    if (document.hidden || calm()) return;
    helloIndex = (helloIndex + 1) % HELLOS.length;
    back.textContent = HELLOS[helloIndex];
    back.className = "";
    front.className = "above";
    [front, back] = [back, front];
    setTimeout(() => { back.className = "below"; }, 700);
  }
  setInterval(nextHello, 2600);

  // ---------------- hero showcase: the shop's own items floating on a plate ----------------

  let showcaseKey = "";
  function showcase(data) {
    const inStock = data.products.filter((p) => p.stock > 0);
    const picks = [...inStock.filter((p) => p.offer_price !== null), ...inStock.filter((p) => p.offer_price === null)]
      .slice(0, 4);
    const key = picks.map((p) => `${p.id}:${p.image}:${p.emoji}`).join("|");
    if (key !== showcaseKey) {                       // only redraw when the items change (the page reloads every 20 s)
      showcaseKey = key;
      $("orbit").replaceChildren(...picks.map((p, i) =>
        h("div", { class: `orbit-item o-${i}` },
          p.image ? h("img", { src: p.image, alt: "", loading: "lazy" }) : h("span", {}, p.emoji || "🧁"))));
    }

    const offer = data.products.find((p) => p.offer_price !== null && p.stock > 0);
    const offerCard = $("fc-offer");
    offerCard.hidden = !offer;
    if (offer) {
      offerCard.replaceChildren(
        h("small", {}, "On offer now"),
        h("b", {}, offer.name),
        h("span", { class: "fc-price" }, h("s", {}, money(offer.price)), " ", money(offer.offer_price)));
    }

    const s = data.shop;
    const delivery = $("fc-delivery");
    delivery.hidden = false;
    delivery.replaceChildren(
      h("small", {}, "Home delivery"),
      h("b", {}, s.delivery_fee === 0 ? "Always free" : `Free over ${money(s.free_delivery_above)}`));
  }

  // ---------------- the moving ribbon under the hero ----------------

  function hourText(hhmm) {
    const [hours, minutes] = hhmm.split(":").map(Number);
    const mins = minutes ? `:${String(minutes).padStart(2, "0")}` : "";
    return `${hours % 12 || 12}${mins} ${hours < 12 ? "AM" : "PM"}`;
  }

  let marqueeKey = "";
  function marquee(data) {
    const s = data.shop;
    const facts = [
      `Open ${hourText(s.open_time)} to ${hourText(s.close_time)}`,
      s.delivery_fee === 0 ? "Free home delivery" : `Free delivery over ${money(s.free_delivery_above)}`,
      "Order by chat in any language",
      `${data.products.filter((p) => p.stock > 0).length} items on the counter today`,
      "Pay at pickup or on delivery",
    ];
    if (s.closed_days.length) facts.splice(1, 0, `Closed on ${s.closed_days.join(" and ")}`);
    const key = facts.join("|");
    if (key === marqueeKey) return;
    marqueeKey = key;
    const run = () => facts.map((text) => h("span", {}, text));
    $("marquee-track").replaceChildren(...run(), ...run());   // two copies make the loop seamless
  }

  document.addEventListener("shop:loaded", (event) => {
    const data = event.detail;
    greet(data.server_now, data.shop);
    showcase(data);
    marquee(data);
    document.body.classList.add("ready");
  });

  // ---------------- buttons: light that follows the pointer, and a ripple on press ----------------

  const PRESSABLE = ".button, .chip, .cart-button, .chat-fab";

  document.addEventListener("pointermove", (event) => {
    const el = event.target.closest?.(PRESSABLE);
    if (!el) return;
    const r = el.getBoundingClientRect();
    el.style.setProperty("--mx", `${event.clientX - r.left}px`);
    el.style.setProperty("--my", `${event.clientY - r.top}px`);
  }, { passive: true });

  document.addEventListener("pointerdown", (event) => {
    const el = event.target.closest?.(PRESSABLE);
    if (!el || el.disabled || calm()) return;
    const r = el.getBoundingClientRect();
    const size = Math.max(r.width, r.height) * 2;
    const ripple = h("span", { class: "ripple", "aria-hidden": "true" });
    ripple.style.setProperty("--size", `${size}px`);
    ripple.style.setProperty("--x", `${event.clientX - r.left - size / 2}px`);
    ripple.style.setProperty("--y", `${event.clientY - r.top - size / 2}px`);
    el.append(ripple);
    setTimeout(() => ripple.remove(), 650);
  }, { passive: true });

  // ---------------- item cards tilt toward the mouse ----------------

  let tilted = null;
  document.addEventListener("pointermove", (event) => {
    if (!finePointer() || calm()) return;
    const card = event.target.closest?.(".item:not(.sold-out), .offer");
    if (tilted && tilted !== card) resetTilt(tilted);
    if (!card) return;
    tilted = card;
    const r = card.getBoundingClientRect();
    const x = (event.clientX - r.left) / r.width - 0.5;
    const y = (event.clientY - r.top) / r.height - 0.5;
    card.style.setProperty("--ry", `${(x * 7).toFixed(2)}deg`);
    card.style.setProperty("--rx", `${(-y * 7).toFixed(2)}deg`);
    card.style.setProperty("--gx", `${((x + 0.5) * 100).toFixed(1)}%`);
    card.style.setProperty("--gy", `${((y + 0.5) * 100).toFixed(1)}%`);
  }, { passive: true });
  function resetTilt(card) {
    card.style.setProperty("--ry", "0deg");
    card.style.setProperty("--rx", "0deg");
    tilted = null;
  }

  // ---------------- a dot flies from "Add" into the order button ----------------
  // Runs in the capture phase, before shop.js redraws the button, so we can still measure where it was.

  document.addEventListener("click", (event) => {
    const button = event.target.closest?.("button");
    if (!button || button.disabled || calm()) return;
    const label = button.getAttribute("aria-label") || "";
    const adds = button.classList.contains("add") || label.startsWith("One more");
    if (!adds || button.closest("#cart-sheet")) return;
    const target = $("open-cart");
    const from = button.getBoundingClientRect();
    const to = target.getBoundingClientRect();
    const dot = h("div", { class: "fly", "aria-hidden": "true" });
    document.body.append(dot);
    const sx = from.left + from.width / 2;
    const sy = from.top + from.height / 2;
    const ex = to.left + to.width - 22;
    const ey = to.top + to.height / 2;
    const lift = Math.min(sy, ey) - 140;
    dot.animate([
      { transform: `translate(${sx}px, ${sy}px) scale(.6)`, opacity: 1 },
      { transform: `translate(${(sx + ex) / 2}px, ${lift}px) scale(1.3)`, opacity: 1, offset: 0.45 },
      { transform: `translate(${ex}px, ${ey}px) scale(.35)`, opacity: 0.4 },
    ], { duration: 720, easing: "cubic-bezier(.5, 0, .3, 1)" }).onfinish = () => {
      dot.remove();
      target.classList.remove("caught");
      void target.offsetWidth;
      target.classList.add("caught");
    };
  }, { capture: true });

  // ---------------- top bar gets a shadow once you scroll ----------------

  const topbar = $("topbar");
  const onScroll = () => topbar.classList.toggle("scrolled", window.scrollY > 8);
  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();
})();
