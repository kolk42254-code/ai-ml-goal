/* The customer shop page: the counter, the cart and the AI assistant. */
"use strict";

(() => {
  const { h, money, api, syncClock, serverNow, timeLeft, store, toast, plate } = Common;
  const $ = (id) => document.getElementById(id);
  const isWide = () => window.matchMedia("(min-width: 1000px)").matches;

  const state = {
    shop: null,
    products: [],
    cart: store.get("sc-cart", {}),            // { productId: quantity }
    cartNotes: {},                             // messages like "Only 2 left"
    category: "All",
    search: "",
    chatId: store.get("sc-chat-id", null),
    chatLog: store.get("sc-chat-log", []),
    sending: false,
    reloadSoon: false,
  };
  if (!state.chatId) {
    const bytes = crypto.getRandomValues(new Uint8Array(12));
    state.chatId = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
    store.set("sc-chat-id", state.chatId);
  }

  const productById = (id) => state.products.find((p) => p.id === Number(id));

  /* "21:00" -> "9:00 PM" */
  function hourText(hhmm) {
    const [hours, minutes] = hhmm.split(":").map(Number);
    return `${hours % 12 || 12}:${String(minutes).padStart(2, "0")} ${hours < 12 ? "AM" : "PM"}`;
  }

  // ---------------- loading the shop ----------------

  async function load() {
    try {
      const data = await api("/api/shop");
      syncClock(data.server_now);
      state.shop = data.shop;
      state.products = data.products;
      renderShopInfo(data.status);
      cleanCart();
      renderCounter();
      renderCart();
    } catch (error) {
      if (!state.products.length) $("shelf").replaceChildren(h("p", { class: "notice" }, error.message));
    }
  }

  function renderShopInfo(status) {
    const s = state.shop;
    document.title = s.shop_name;
    $("shop-name").textContent = s.shop_name;
    $("footer-name").textContent = s.shop_name;
    $("tagline").textContent = s.tagline;
    $("status").className = "status " + (status.open ? "open" : "closed");
    $("status-text").textContent = status.text;
    $("footer-address").textContent = s.address;
    $("footer-phone").textContent = `Call ${s.phone}`;
    $("footer-phone").href = "tel:" + s.phone.replace(/[^\d+]/g, "");
    const closed = s.closed_days.length ? `, closed on ${s.closed_days.join(" and ")}` : ", every day";
    $("footer-hours").textContent = `${hourText(s.open_time)} to ${hourText(s.close_time)}${closed}.`;
    $("footer-delivery").textContent = `${deliveryRule()} ${s.delivery_area}`;
    $("delivery-hint").textContent = deliveryRule();
  }

  function deliveryRule() {
    const s = state.shop;
    if (s.delivery_fee === 0) return "Home delivery is free.";
    return `Delivery costs ${money(s.delivery_fee)}, free on orders of ${money(s.free_delivery_above)} or more.`;
  }

  // ---------------- the counter: offers, categories, items ----------------

  function renderCounter() {
    const focusKey = document.activeElement?.dataset?.focus;   // keep keyboard focus after redrawing
    renderOffers();
    renderCategories();
    renderShelf();
    if (focusKey) document.querySelector(`[data-focus="${focusKey}"]`)?.focus();
    tick();
  }

  function priceTag(p) {
    return p.offer_price !== null
      ? h("span", { class: "tag", dataset: { tagFor: p.id } }, h("s", {}, money(p.price)), money(p.offer_price))
      : h("span", { class: "tag", dataset: { tagFor: p.id } }, money(p.price));
  }

  function buyControl(p, where) {
    const qty = state.cart[p.id] || 0;
    if (qty === 0) {
      return h("button", { class: "button add", type: "button", dataset: { focus: `${where}-add-${p.id}` },
        "aria-label": `Add ${p.name}`, onclick: () => changeQty(p.id, 1) }, "Add");
    }
    return h("div", { class: "stepper", role: "group", "aria-label": `${p.name} in your order` },
      h("button", { type: "button", dataset: { focus: `${where}-minus-${p.id}` }, "aria-label": `One less ${p.name}`,
        onclick: () => changeQty(p.id, -1) }, "−"),
      h("output", { "aria-live": "polite" }, qty),
      h("button", { type: "button", dataset: { focus: `${where}-plus-${p.id}` }, "aria-label": `One more ${p.name}`,
        disabled: qty >= p.stock, onclick: () => changeQty(p.id, 1) }, "+"));
  }

  function renderOffers() {
    const offers = state.products.filter((p) => p.offer_price !== null && p.stock > 0);
    $("offers").hidden = offers.length === 0;
    $("offer-rail").replaceChildren(...offers.map((p) =>
      h("article", { class: "offer" },
        plate(p),
        h("div", {},
          h("h3", {}, p.name),
          priceTag(p),
          h("p", { class: "timer", dataset: { ends: p.offer_ends_at } }),
          h("div", { class: "row-end" }, buyControl(p, "offer"))))));
  }

  function renderCategories() {
    const categories = ["All", ...new Set(state.products.map((p) => p.category))];
    if (!categories.includes(state.category)) state.category = "All";
    $("categories").replaceChildren(...categories.map((name) =>
      h("button", { class: "chip", type: "button", "aria-pressed": String(name === state.category),
        dataset: { focus: `cat-${name}` },
        onclick: () => { state.category = name; renderCounter(); } }, name)));
  }

  function renderShelf() {
    const words = state.search.trim().toLowerCase();
    const shown = state.products.filter((p) =>
      (state.category === "All" || p.category === state.category) &&
      (!words || `${p.name} ${p.description} ${p.category}`.toLowerCase().includes(words)));
    if (!shown.length) {
      $("shelf").replaceChildren(h("p", { class: "empty-shelf" }, state.products.length
        ? `Nothing on the counter matches "${state.search.trim()}". Try another word, or ask the assistant.`
        : "The counter is empty right now. Please check back soon."));
      return;
    }
    const groups = new Map();
    for (const p of shown) groups.set(p.category, [...(groups.get(p.category) || []), p]);
    $("shelf").replaceChildren(...[...groups].map(([category, items]) =>
      h("section", { class: "shelf-group" },
        h("h3", {}, category),
        h("div", { class: "shelf-grid" }, items.map(itemTile)))));
  }

  function itemTile(p) {
    const soldOut = p.stock <= 0;
    let note = null;
    if (!soldOut && p.stock <= 3) note = h("p", { class: "stock-note" }, `Only ${p.stock} left`);
    return h("article", { class: "item" + (soldOut ? " sold-out" : "") },
      plate(p),
      h("div", {},
        h("h4", {}, p.name),
        p.description ? h("p", { class: "desc" }, p.description) : null,
        note),
      h("div", { class: "item-foot" },
        soldOut ? h("span", { class: "sold-out-label" }, "Sold out today") : priceTag(p),
        soldOut ? null : buyControl(p, "shelf")),
      p.offer_price !== null && !soldOut ? h("p", { class: "timer", dataset: { ends: p.offer_ends_at } }) : null);
  }

  /* Offer countdowns tick every second, using the server's clock. */
  function tick() {
    for (const el of document.querySelectorAll("[data-ends]")) {
      const left = Date.parse(el.dataset.ends) - serverNow();
      if (left <= 0) {
        el.textContent = "Offer ended";
        if (!state.reloadSoon) { state.reloadSoon = true; setTimeout(() => { state.reloadSoon = false; load(); }, 1500); }
      } else {
        el.textContent = `Offer ends in ${timeLeft(left)}`;
      }
    }
  }

  // ---------------- the cart ----------------

  function changeQty(id, delta) {
    const p = productById(id);
    if (!p) return;
    const now = state.cart[id] || 0;
    const next = Math.max(0, Math.min(p.stock, now + delta));
    if (next === now) {
      if (delta > 0) toast(`Only ${p.stock} ${p.name} left.`);
      return;
    }
    if (next === 0) delete state.cart[id];
    else state.cart[id] = next;
    delete state.cartNotes[id];
    store.set("sc-cart", state.cart);
    renderCounter();
    renderCart();
    if (delta > 0) {
      for (const tag of document.querySelectorAll(`[data-tag-for="${id}"]`)) {
        tag.classList.remove("swing");
        void tag.offsetWidth;                                 // restart the swing animation
        tag.classList.add("swing");
      }
      const count = $("cart-count");
      count.classList.remove("bump");
      void count.offsetWidth;
      count.classList.add("bump");
      if (now === 0) toast(`Added ${p.name}`);
    }
  }

  /* Keep the cart honest when stock or the menu changes. */
  function cleanCart() {
    for (const [id, qty] of Object.entries(state.cart)) {
      const p = productById(id);
      if (!p) { delete state.cart[id]; continue; }
      if (qty > p.stock) {
        if (p.stock <= 0) delete state.cart[id];
        else state.cart[id] = p.stock;
        state.cartNotes[id] = p.stock <= 0 ? `${p.name} just sold out, so it was taken out of your order.`
          : `Only ${p.stock} left, so your order now has ${p.stock}.`;
      }
    }
    store.set("sc-cart", state.cart);
  }

  function cartTotals() {
    const lines = Object.entries(state.cart).map(([id, qty]) => ({ p: productById(id), qty })).filter((l) => l.p);
    const count = lines.reduce((sum, l) => sum + l.qty, 0);
    const subtotal = lines.reduce((sum, l) => sum + l.qty * l.p.current_price, 0);
    const delivery = $("checkout").elements.fulfilment.value === "delivery";
    const fee = delivery && state.shop && subtotal < state.shop.free_delivery_above ? state.shop.delivery_fee : 0;
    return { lines, count, subtotal, delivery, fee, total: subtotal + fee };
  }

  function renderCart() {
    if (!state.shop) return;
    const { lines, count, subtotal, delivery, fee, total } = cartTotals();
    $("cart-count").textContent = count;
    $("cart-bar").hidden = count === 0;
    document.body.classList.toggle("has-cart", count > 0);
    $("cart-bar-text").textContent = `${count} ${count === 1 ? "item" : "items"}, ${money(subtotal)}`;

    if (!$("receipt").hidden) return;                       // the receipt is showing: leave it alone
    const notes = Object.entries(state.cartNotes).filter(([id]) => !productById(id) || !state.cart[id]);
    $("cart-empty").hidden = count > 0;
    $("cart-filled").hidden = count === 0;
    if (count === 0 && notes.length) $("cart-empty").replaceChildren(h("p", { class: "notice" }, notes.map(([, text]) => text).join(" ")));

    const focusKey = document.activeElement?.dataset?.focus;
    $("cart-lines").replaceChildren(...lines.map(({ p, qty }) =>
      h("li", { class: "cart-line" },
        plate(p),
        h("div", {},
          h("h3", {}, p.name),
          h("p", { class: "line-meta" }, `${money(p.current_price)} each, ${money(p.current_price * qty)}`),
          state.cartNotes[p.id] ? h("p", { class: "line-warn" }, state.cartNotes[p.id]) : null),
        h("div", { class: "stepper", role: "group", "aria-label": `${p.name} in your order` },
          h("button", { type: "button", dataset: { focus: `cart-minus-${p.id}` }, "aria-label": `One less ${p.name}`,
            onclick: () => changeQty(p.id, -1) }, "−"),
          h("output", {}, qty),
          h("button", { type: "button", dataset: { focus: `cart-plus-${p.id}` }, "aria-label": `One more ${p.name}`,
            disabled: qty >= p.stock, onclick: () => changeQty(p.id, 1) }, "+")))));
    if (focusKey?.startsWith("cart-")) document.querySelector(`[data-focus="${focusKey}"]`)?.focus();

    $("address-field").hidden = !delivery;
    const rows = [h("dt", {}, "Items"), h("dd", {}, money(subtotal))];
    if (delivery) rows.push(h("dt", {}, "Delivery"), h("dd", {}, fee ? money(fee) : "Free"));
    rows.push(h("dt", { class: "grand" }, "Total"), h("dd", { class: "grand" }, money(total)));
    $("totals").replaceChildren(...rows);
    $("place-order").textContent = `Place order, ${money(total)}`;
  }

  // ---------------- order sheet (open, close, checkout) ----------------

  let focusBeforeSheet = null;

  function openCart() {
    focusBeforeSheet = document.activeElement;
    $("receipt").hidden = true;
    $("checkout-error").hidden = true;
    renderCart();
    $("backdrop").hidden = false;
    $("cart-sheet").hidden = false;
    document.body.classList.add("locked");
    $("close-cart").focus();
  }

  function closeCart() {
    $("cart-sheet").hidden = true;
    $("backdrop").hidden = true;
    if (!$("assistant").classList.contains("open")) document.body.classList.remove("locked");
    state.cartNotes = {};
    focusBeforeSheet?.focus?.();
  }

  function fillSavedDetails() {
    const saved = store.get("sc-customer", {});
    const form = $("checkout");
    for (const key of ["customer_name", "phone", "address"]) if (saved[key]) form.elements[key].value = saved[key];
  }

  async function placeOrder(event) {
    event.preventDefault();
    const form = $("checkout");
    const value = (name) => form.elements[name].value.trim();
    const problem = (message, field) => {
      $("checkout-error").textContent = message;
      $("checkout-error").hidden = false;
      if (field) form.elements[field].focus();
    };
    const { lines, delivery } = cartTotals();
    if (!lines.length) return problem("Your order is empty.");
    if (delivery && value("address").length < 8) return problem("Please write your full delivery address.", "address");
    if (!value("wanted_at")) return problem("Please say when you want your order.", "wanted_at");
    if (!value("customer_name")) return problem("Please write your name.", "customer_name");
    if (value("phone").replace(/\D/g, "").length < 10) return problem("Please write a phone number with 10 digits.", "phone");

    $("checkout-error").hidden = true;
    const button = $("place-order");
    button.disabled = true;
    button.textContent = "Placing your order";
    try {
      const { order } = await api("/api/orders", {
        method: "POST",
        body: {
          customer_name: value("customer_name"), phone: value("phone"), fulfilment: delivery ? "delivery" : "pickup",
          address: delivery ? value("address") : "", wanted_at: value("wanted_at"), notes: value("notes"),
          items: lines.map((l) => ({ product_id: l.p.id, quantity: l.qty })),
        },
      });
      store.set("sc-customer", { customer_name: value("customer_name"), phone: value("phone"), address: value("address") });
      state.cart = {};
      store.set("sc-cart", state.cart);
      form.elements.wanted_at.value = "";
      form.elements.notes.value = "";
      showReceipt(order);
      load();
    } catch (error) {
      problem(error.message);
      load();
    } finally {
      button.disabled = false;
      renderCart();
    }
  }

  function receipt(order) {
    const where = order.fulfilment === "delivery" ? `Delivery to ${order.address}` : "Pickup at the shop";
    return h("div", { class: "receipt" },
      h("h3", {}, `Order #${order.id} is placed`),
      h("ul", {},
        order.items.map((line) => h("li", {}, h("span", {}, `${line.quantity} × ${line.name}`), h("span", {}, money(line.line_total)))),
        order.fulfilment === "delivery"
          ? h("li", {}, h("span", {}, "Delivery"), h("span", {}, order.delivery_fee ? money(order.delivery_fee) : "Free"))
          : null),
      h("p", { class: "total" }, h("span", {}, "Total"), h("span", {}, money(order.total))),
      h("p", { class: "small" }, `${where}, ${order.wanted_at}.`),
      h("p", { class: "small" }, "The shop will call you to confirm. You pay when you pick up or receive your order."));
  }

  function showReceipt(order) {
    $("cart-empty").hidden = true;
    $("cart-filled").hidden = true;
    const done = h("button", { class: "button place-order", type: "button", onclick: closeCart }, "Done");
    $("receipt").replaceChildren(receipt(order), done);
    $("receipt").hidden = false;
    done.focus();
  }

  // ---------------- the assistant ----------------

  function openChat() {
    if (!isWide()) {
      $("assistant").classList.add("open");
      document.body.classList.add("locked");
    }
    scrollChat();
    $("chat-input").focus();
  }

  function closeChat() {
    $("assistant").classList.remove("open");
    if ($("cart-sheet").hidden) document.body.classList.remove("locked");
    $("chat-fab").focus();
  }

  const scrollChat = () => { const list = $("messages"); list.scrollTop = list.scrollHeight; };

  function messageView(entry) {
    if (entry.from === "order") return h("li", { class: "receipt-wrap" }, receipt(entry.order));
    return h("li", { class: `msg ${entry.from}` }, entry.text);
  }

  function renderChat() {
    const greeting = { from: "shop", text: "Hi! I'm the shop's AI assistant. Ask me about cakes, prices, offers or delivery, in any language. Tell me what you'd like and I can place the order for you." };
    const items = [greeting, ...state.chatLog].map(messageView);
    if (!state.chatLog.length) {
      items.push(h("li", { class: "chat-suggestions" },
        ["What's on offer today?", "Which cakes can be made eggless?", "I want to order a birthday cake"].map((text) =>
          h("button", { class: "chip", type: "button", onclick: () => sendChat(text) }, text))));
    }
    $("messages").replaceChildren(...items);
    scrollChat();
  }

  function addMessage(entry) {
    document.querySelector(".chat-suggestions")?.remove();
    state.chatLog = [...state.chatLog, entry].slice(-40);
    store.set("sc-chat-log", state.chatLog);
    $("messages").append(messageView(entry));
    scrollChat();
  }

  async function sendChat(text) {
    text = text.trim();
    if (!text || state.sending) return;
    state.sending = true;
    $("chat-send").disabled = true;
    addMessage({ from: "you", text });
    const typing = h("li", { class: "msg shop typing", "aria-label": "The assistant is typing" }, h("span"), h("span"), h("span"));
    $("messages").append(typing);
    scrollChat();
    try {
      const data = await api("/api/chat", { method: "POST", body: { chat_id: state.chatId, message: text } });
      typing.remove();
      addMessage({ from: "shop", text: data.reply });
      for (const order of data.orders || []) addMessage({ from: "order", order });
      if ((data.orders || []).length) load();               // stock changed
    } catch (error) {
      typing.remove();
      addMessage({ from: "problem", text: error.message });
    } finally {
      state.sending = false;
      $("chat-send").disabled = false;
    }
  }

  // ---------------- keyboard: keep focus inside open dialogs ----------------

  function trapFocus(event, container) {
    const focusable = [...container.querySelectorAll("button, input, textarea, select, a[href]")]
      .filter((el) => !el.disabled && el.offsetParent !== null);
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  }

  document.addEventListener("keydown", (event) => {
    const sheetOpen = !$("cart-sheet").hidden;
    const chatOpen = $("assistant").classList.contains("open");
    if (event.key === "Escape") {
      if (sheetOpen) closeCart();
      else if (chatOpen) closeChat();
    } else if (event.key === "Tab") {
      if (sheetOpen) trapFocus(event, $("cart-sheet"));
      else if (chatOpen) trapFocus(event, $("assistant"));
    }
  });

  // ---------------- wiring ----------------

  $("open-cart").addEventListener("click", openCart);
  $("cart-bar-open").addEventListener("click", openCart);
  $("close-cart").addEventListener("click", closeCart);
  $("backdrop").addEventListener("click", closeCart);
  $("checkout").addEventListener("submit", placeOrder);
  $("checkout").addEventListener("change", (event) => { if (event.target.name === "fulfilment") renderCart(); });
  $("chat-fab").addEventListener("click", openChat);
  $("close-chat").addEventListener("click", closeChat);
  $("search").addEventListener("input", (event) => { state.search = event.target.value; renderShelf(); tick(); });

  $("hero-ask").addEventListener("submit", (event) => {
    event.preventDefault();
    const text = $("hero-input").value;
    if (!text.trim()) return $("hero-input").focus();
    $("hero-input").value = "";
    openChat();
    sendChat(text);
  });
  for (const chip of document.querySelectorAll("[data-ask]")) {
    chip.addEventListener("click", () => { openChat(); sendChat(chip.dataset.ask); });
  }
  $("composer").addEventListener("submit", (event) => {
    event.preventDefault();
    const text = $("chat-input").value;
    $("chat-input").value = "";
    sendChat(text);
  });

  fillSavedDetails();
  renderChat();
  load();
  setInterval(tick, 1000);
  setInterval(() => { if (!document.hidden) load(); }, 20000);   // owner's changes show up within 20 seconds
  document.addEventListener("visibilitychange", () => { if (!document.hidden) load(); });
})();
