/* The customer shop page: the counter, the cart, my orders and the AI assistant. */
"use strict";

(() => {
  const { h, money, api, syncClock, serverNow, timeLeft, clockText, store, toast, plate } = Common;
  const $ = (id) => document.getElementById(id);
  const isWide = () => window.matchMedia("(min-width: 1000px)").matches;

  const ACTIVE = ["new", "preparing", "ready"];          // orders the shop is still working on
  const STEPS = ["new", "preparing", "ready", "completed"];
  /* Saved tracking codes: [{ id, token, status }]. Anything that doesn't look right is dropped. */
  const savedOrders = (list) => (Array.isArray(list) ? list : [])
    .filter((entry) => entry && typeof entry.token === "string" && /^[A-Za-z0-9_-]{16,64}$/.test(entry.token));

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
    vegOnly: store.get("sc-veg-only", false) === true,
    mine: savedOrders(store.get("sc-orders", [])),   // this browser's orders (only their secret codes)
    views: [],                                 // those orders as the shop sees them right now
    loadingMine: false,
    mineAgain: false,
    mineKey: "",
    confirmCancel: null,                       // the order whose "Cancel this order?" question is showing
    cancelling: null,
    shownIds: new Set(),                       // orders already drawn in the open My orders list
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
      document.dispatchEvent(new CustomEvent("shop:loaded", { detail: data }));   // motion.js decorates the page
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
    const emoji = s.shop_emoji || "🛍️";
    for (const el of document.querySelectorAll("[data-shop-emoji]")) el.textContent = emoji;
    setFavicon(emoji);
    renderQuickQuestions(s.quick_questions || []);
    $("checkout").elements.notes.placeholder = s.notes_hint || "Anything the shop should know";
  }

  function deliveryRule() {
    const s = state.shop;
    if (s.delivery_fee === 0 || s.free_delivery_above <= 0) return "Home delivery is free.";
    return `Delivery costs ${money(s.delivery_fee)}, free on orders of ${money(s.free_delivery_above)} or more.`;
  }

  /* The browser-tab icon becomes the shop's own icon. */
  let faviconEmoji = "";
  function setFavicon(emoji) {
    if (emoji === faviconEmoji) return;
    faviconEmoji = emoji;
    const svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><text x="50" y="55" font-size="80" ' +
      `text-anchor="middle" dominant-baseline="middle">${emoji.replace(/[&<>"']/g, "")}</text></svg>`;
    $("favicon").href = `data:image/svg+xml,${encodeURIComponent(svg)}`;
  }

  /* The owner's quick questions, under the "Ask" box and in an empty chat. */
  let questionsKey = null;
  function renderQuickQuestions(questions) {
    const key = JSON.stringify(questions);
    if (key === questionsKey) return;
    questionsKey = key;
    $("suggestions").replaceChildren(...questions.map((text) =>
      h("button", { class: "chip", type: "button", dataset: { ask: text } }, text)));
    if (!state.chatLog.length) renderChat();
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

  /* The Indian food mark: green dot = veg, brown triangle = non-veg. */
  function dietMark(p) {
    if (p.diet !== "veg" && p.diet !== "nonveg") return null;
    const name = p.diet === "veg" ? "Veg" : "Non-veg";
    return h("span", { class: `diet diet-${p.diet}`, role: "img", "aria-label": name, title: name });
  }

  const dishName = (tag, p) => h(tag, { class: "dish-name" }, dietMark(p), h("span", {}, p.name));

  function renderOffers() {
    const offers = state.products.filter((p) => p.offer_price !== null && p.stock > 0);
    $("offers").hidden = offers.length === 0;
    $("offer-rail").replaceChildren(...offers.map((p) =>
      h("article", { class: "offer" },
        plate(p),
        h("div", {},
          dishName("h3", p),
          priceTag(p),
          h("p", { class: "timer", dataset: { ends: p.offer_ends_at } }),
          h("div", { class: "row-end" }, buyControl(p, "offer"))))));
  }

  function renderCategories() {
    const categories = ["All", ...new Set(state.products.map((p) => p.category))];
    if (!categories.includes(state.category)) state.category = "All";
    const chips = categories.map((name) =>
      h("button", { class: "chip", type: "button", "aria-pressed": String(name === state.category),
        dataset: { focus: `cat-${name}` },
        onclick: () => {
          state.category = name;
          if (document.startViewTransition && !matchMedia("(prefers-reduced-motion: reduce)").matches) {
            document.startViewTransition(renderCounter);          // a smooth cross-fade between categories
          } else {
            renderCounter();
          }
        } }, name));
    if (state.products.some((p) => p.diet === "veg") && state.products.some((p) => p.diet === "nonveg")) {
      chips.unshift(h("button", { class: "chip veg-chip", type: "button", "aria-pressed": String(state.vegOnly),
        dataset: { focus: "veg-only" },
        onclick: () => { state.vegOnly = !state.vegOnly; store.set("sc-veg-only", state.vegOnly); renderCounter(); } },
      h("span", { class: "diet diet-veg", "aria-hidden": "true" }), "Veg only"));
    }
    $("categories").replaceChildren(...chips);
  }

  function renderShelf() {
    const words = state.search.trim().toLowerCase();
    const vegOnly = state.vegOnly && state.products.some((p) => p.diet === "nonveg");
    const shown = state.products.filter((p) =>
      (!vegOnly || p.diet === "veg") &&
      (state.category === "All" || p.category === state.category) &&
      (!words || `${p.name} ${p.description} ${p.category}`.toLowerCase().includes(words)));
    if (!shown.length) {
      $("shelf").replaceChildren(h("p", { class: "empty-shelf" }, state.products.length
        ? (state.search.trim() ? `Nothing on the counter matches "${state.search.trim()}". Try another word, or ask the assistant.`
          : "No veg items in this category. Tap \"Veg only\" again to see everything.")
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
        dishName("h4", p),
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
    $("open-cart").setAttribute("aria-label", count ? `Cart, ${count} ${count === 1 ? "item" : "items"}` : "Cart");
    $("cart-bar").hidden = count === 0;
    document.body.classList.toggle("has-cart", count > 0);
    $("cart-bar-text").textContent = `${count} ${count === 1 ? "item" : "items"}, ${money(subtotal)}`;

    if (!$("receipt").hidden) return;                       // the receipt is showing: leave it alone
    const notes = Object.entries(state.cartNotes).filter(([id]) => !productById(id) || !state.cart[id]);
    $("cart-empty").hidden = count > 0;
    $("cart-filled").hidden = count === 0;
    if (count === 0) renderEmptyCart(notes);

    const focusKey = document.activeElement?.dataset?.focus;
    $("cart-lines").replaceChildren(...lines.map(({ p, qty }) =>
      h("li", { class: "cart-line" },
        plate(p),
        h("div", {},
          h("h3", {}, p.name),
          h("p", { class: "line-meta" }, `${money(p.current_price)} each, ${money(p.current_price * qty)}`),
          state.cartNotes[p.id] ? h("p", { class: "line-warn" }, state.cartNotes[p.id]) : null),
        h("div", { class: "stepper", role: "group", "aria-label": `${p.name} in your cart` },
          h("button", { type: "button", dataset: { focus: `cart-minus-${p.id}` }, "aria-label": `One less ${p.name}`,
            onclick: () => changeQty(p.id, -1) }, "−"),
          h("output", {}, qty),
          h("button", { type: "button", dataset: { focus: `cart-plus-${p.id}` }, "aria-label": `One more ${p.name}`,
            disabled: qty >= p.stock, onclick: () => changeQty(p.id, 1) }, "+")))));
    if (focusKey?.startsWith("cart-")) document.querySelector(`[data-focus="${focusKey}"]`)?.focus();

    $("address-field").hidden = !delivery;
    renderFreeMeter(subtotal, delivery);
    const rows = [h("dt", {}, "Items"), h("dd", {}, money(subtotal))];
    if (delivery) rows.push(h("dt", {}, "Delivery"), h("dd", {}, fee ? money(fee) : "Free"));
    rows.push(h("dt", { class: "grand" }, "Total"), h("dd", { class: "grand" }, money(total)));
    $("totals").replaceChildren(...rows);
    $("place-order").textContent = `Place order, ${money(total)}`;
  }

  /* An empty cart also points to orders already placed, so nobody thinks their order disappeared. */
  function renderEmptyCart(notes) {
    const active = state.views.filter((o) => ACTIVE.includes(o.status)).length;
    const focusKey = document.activeElement?.dataset?.focus;
    const parts = [];
    if (notes.length) parts.push(h("p", { class: "notice" }, notes.map(([, text]) => text).join(" ")));
    parts.push(h("p", {}, "Your cart is empty. Add something from the counter, or ask the assistant to order for you."));
    if (active) {
      parts.push(h("div", { class: "orders-nudge" },
        h("p", {}, `You have ${active} ${active === 1 ? "order" : "orders"} in progress.`),
        h("button", { class: "button", type: "button", dataset: { focus: "cart-see-orders" },
          onclick: () => { closeCart(false); openOrders(); } }, "See my orders")));
    }
    $("cart-empty").replaceChildren(...parts);
    if (focusKey === "cart-see-orders") document.querySelector('[data-focus="cart-see-orders"]')?.focus();
  }

  /* "Add ₹60 more for free delivery", with a bar that fills up. Only shown for home delivery. */
  function renderFreeMeter(subtotal, delivery) {
    const s = state.shop;
    const show = delivery && s.delivery_fee > 0 && s.free_delivery_above > 0;
    $("free-meter").hidden = !show;
    if (!show) return;
    const need = s.free_delivery_above - subtotal;
    $("free-text").textContent = need > 0
      ? `Add ${money(need)} more for free delivery.`
      : "Your order gets free delivery.";
    $("free-meter").classList.toggle("reached", need <= 0);
    $("free-bar").style.setProperty("--fill", `${Math.min(100, Math.round((subtotal / s.free_delivery_above) * 100))}%`);
  }

  // ---------------- cart sheet (open, close, checkout) ----------------

  let focusBeforeSheet = null;

  function openCart() {
    if (!$("orders-sheet").hidden) closeOrders(false);
    // coming from a sheet that just closed: give focus back to the Cart button later
    focusBeforeSheet = document.activeElement?.closest("[hidden]") ? $("open-cart") : document.activeElement;
    $("receipt").hidden = true;
    $("checkout-error").hidden = true;
    renderCart();
    $("backdrop").hidden = false;
    $("cart-sheet").hidden = false;
    document.body.classList.add("locked");
    $("close-cart").focus();
  }

  function closeCart(restoreFocus = true) {
    $("cart-sheet").hidden = true;
    if ($("orders-sheet").hidden) $("backdrop").hidden = true;
    if (!$("assistant").classList.contains("open") && $("orders-sheet").hidden) document.body.classList.remove("locked");
    state.cartNotes = {};
    if (restoreFocus) focusBeforeSheet?.focus?.();
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
    if (!lines.length) return problem("Your cart is empty.");
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
      rememberOrder(order);
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
      h("p", { class: "small" }, "The shop will confirm it soon. You pay when you pick up or receive your order."));
  }

  function showReceipt(order) {
    $("cart-empty").hidden = true;
    $("cart-filled").hidden = true;
    const done = h("button", { class: "button place-order", type: "button", onclick: () => closeCart() }, "Done");
    const follow = h("button", { class: "button button-quiet place-order", type: "button",
      onclick: () => { closeCart(false); openOrders(); } }, "Follow it in My orders");
    $("receipt").replaceChildren(receipt(order), done, follow);
    $("receipt").hidden = false;
    done.focus();
  }

  // ---------------- my orders: live status of the orders placed in this browser ----------------

  function saveMine() { store.set("sc-orders", state.mine); }

  function rememberOrder(order) {
    const token = order.track_token || order.token;
    if (!token || state.mine.some((entry) => entry.token === token)) return false;
    state.mine.unshift({ id: order.id, token, status: order.status });
    while (state.mine.length > 30) {                         // keep the list short: forget old finished orders first
      let i = state.mine.length - 1;
      while (i >= 0 && ACTIVE.includes(state.mine[i].status)) i -= 1;
      state.mine.splice(i >= 0 ? i : state.mine.length - 1, 1);
    }
    saveMine();
    loadMyOrders();
    return true;
  }

  async function loadMyOrders() {
    if (state.loadingMine) { state.mineAgain = true; return; }
    const sent = state.mine.map((entry) => entry.token);
    if (!sent.length) { state.views = []; renderMine(); return; }
    state.loadingMine = true;
    try {
      const data = await api("/api/my-orders", { method: "POST", body: { tokens: sent } });
      syncClock(data.server_now);
      const byToken = new Map(data.orders.map((o) => [o.token, o]));
      // forget codes the shop doesn't know any more (for example, the shop started a fresh database)
      state.mine = state.mine.filter((entry) => !sent.includes(entry.token) || byToken.has(entry.token));
      const changes = [];
      for (const entry of state.mine) {
        const o = byToken.get(entry.token);
        if (!o) continue;
        if (entry.status && entry.status !== o.status) changes.push(o);
        entry.status = o.status;
        entry.id = o.id;
      }
      saveMine();
      state.views = data.orders;
      renderMine();
      announce(changes);
    } catch {
      /* offline for a moment: the next round tries again */
    } finally {
      state.loadingMine = false;
      if (state.mineAgain) { state.mineAgain = false; loadMyOrders(); }
    }
  }

  function announce(changes) {
    if (!changes.length) return;
    toast(changes.length === 1 ? changeText(changes[0])
      : `${changes.length} of your orders were updated. Open My orders to see them.`);
    const button = $("open-orders");
    button.classList.remove("caught");
    void button.offsetWidth;                                 // restart the little wobble
    button.classList.add("caught");
  }

  function changeText(o) {
    const delivery = o.fulfilment === "delivery";
    switch (o.status) {
      case "preparing": return `Order #${o.id} is confirmed. The shop is preparing it.`;
      case "ready": return delivery ? `Order #${o.id} is ready and will be delivered soon.` : `Order #${o.id} is ready for pickup.`;
      case "completed": return delivery ? `Order #${o.id} was delivered. Thank you!` : `Order #${o.id} was picked up. Thank you!`;
      case "cancelled": return o.cancelled_by === "customer" ? `Order #${o.id} is cancelled.`
        : `The shop cancelled order #${o.id}. Please call them if you have questions.`;
      default: return `Order #${o.id} was updated.`;
    }
  }

  function statusLabel(o) {
    const delivery = o.fulfilment === "delivery";
    switch (o.status) {
      case "new": return "Waiting for the shop";
      case "preparing": return "Confirmed";
      case "ready": return delivery ? "Ready for delivery" : "Ready for pickup";
      case "completed": return delivery ? "Delivered" : "Picked up";
      default: return "Cancelled";
    }
  }

  function statusSentence(o) {
    const delivery = o.fulfilment === "delivery";
    switch (o.status) {
      case "new": return "Waiting for the shop to confirm. You can still cancel it.";
      case "preparing":
        return `The shop confirmed your order${o.times.preparing ? ` at ${clockText(o.times.preparing)}` : ""} and is preparing it.`;
      case "ready": return delivery ? "Your order is ready and will be delivered soon." : "Your order is ready. You can pick it up now.";
      case "completed": return delivery ? "Delivered. Thank you for your order!" : "Picked up. Thank you for your order!";
      default: return o.cancelled_by === "customer" ? "You cancelled this order."
        : "The shop cancelled this order. Please call them if you have questions.";
    }
  }

  /* "today at 6:40 pm", "yesterday at 9:05 am" or "Sat, 14 Nov at 6:40 pm" (India time, the shop's clock) */
  function whenText(iso) {
    const dayOf = (ms) => new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata", year: "numeric", month: "2-digit",
      day: "2-digit" }).format(new Date(ms));
    const at = Date.parse(iso);
    const time = clockText(iso);
    if (dayOf(at) === dayOf(serverNow())) return `today at ${time}`;
    if (dayOf(at) === dayOf(serverNow() - 86400000)) return `yesterday at ${time}`;
    const date = new Date(at).toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short",
      timeZone: "Asia/Kolkata" });
    return `${date} at ${time}`;
  }

  function renderMine() {
    const active = state.views.filter((o) => ACTIVE.includes(o.status)).length;
    $("orders-count").hidden = active === 0;
    $("orders-count").textContent = active;
    $("open-orders").setAttribute("aria-label", active ? `My orders, ${active} in progress` : "My orders");
    if (!$("cart-sheet").hidden && $("receipt").hidden && !Object.keys(state.cart).length) renderCart();
    if ($("orders-sheet").hidden) return;
    const key = JSON.stringify([state.views, state.confirmCancel, state.cancelling, state.shop?.phone]);
    if (key === state.mineKey) return;                       // nothing changed: leave the list and keyboard focus alone
    state.mineKey = key;
    const focusKey = document.activeElement?.dataset?.focus;
    const shown = state.shownIds;                            // only orders new to the list get the pop-in animation
    $("orders-list").replaceChildren(...(state.views.length ? state.views.map((o) => {
      const card = myOrderCard(o);
      if (!shown.has(o.id)) card.classList.add("appear");
      return card;
    }) : [h("p", { class: "orders-empty" }, state.mine.length ? "Loading your orders"
        : "No orders yet. When you place an order, you can follow it here.")]));
    state.shownIds = new Set(state.views.map((o) => o.id));
    if (focusKey) $("orders-list").querySelector(`[data-focus="${focusKey}"]`)?.focus();
  }

  function myOrderCard(o) {
    const delivery = o.fulfilment === "delivery";
    const lines = o.items.map((line) =>
      h("li", {}, h("span", {}, `${line.quantity} × ${line.name}`), h("span", {}, money(line.line_total))));
    if (delivery) lines.push(h("li", { class: "fee" }, h("span", {}, "Delivery"), h("span", {}, o.delivery_fee ? money(o.delivery_fee) : "Free")));
    return h("article", { class: `my-order status-${o.status}`, "aria-label": `Order ${o.id}` },
      h("div", { class: "my-order-head" },
        h("div", {}, h("h3", {}, `Order #${o.id}`), h("p", { class: "small" }, `Placed ${whenText(o.created_at)}`)),
        h("span", { class: `pill pill-${o.status}` }, statusLabel(o))),
      o.status === "cancelled" ? null : progress(o),
      h("p", { class: "status-sentence" }, statusSentence(o)),
      h("ul", { class: "my-order-items" }, lines),
      h("p", { class: "my-order-total" }, h("span", {}, "Total"), h("span", {}, money(o.total))),
      h("p", { class: "small" }, `${delivery ? `Delivery to ${o.address}` : "Pickup at the shop"}. Wanted: ${o.wanted_at}.`),
      o.notes ? h("p", { class: "small" }, `Your note: ${o.notes}`) : null,
      myOrderActions(o));
  }

  function progress(o) {
    const reached = STEPS.indexOf(o.status);
    const names = ["Placed", "Confirmed", "Ready", o.fulfilment === "delivery" ? "Delivered" : "Picked up"];
    return h("ol", { class: "steps", "aria-label": "Order progress" }, STEPS.map((step, i) =>
      h("li", { class: i < reached ? "done" : i === reached ? "current" : "todo", "aria-current": i === reached ? "step" : null },
        h("span", { class: "step-dot", "aria-hidden": "true" }),
        h("span", { class: "step-name" }, names[i]),
        i <= reached && o.times[step] ? h("span", { class: "step-time" }, clockText(o.times[step])) : null)));
  }

  function myOrderActions(o) {
    const actions = [];
    const focusIn = (name) => $("orders-list").querySelector(`[data-focus="${name}-${o.id}"]`)?.focus();
    if (o.can_cancel && state.confirmCancel === o.token) {
      const busy = state.cancelling === o.token;
      actions.push(
        h("span", { class: "confirm-text" }, "Cancel this order?"),
        h("button", { class: "button button-small danger-button", type: "button", disabled: busy,
          dataset: { focus: `yes-${o.id}` }, onclick: () => cancelMyOrder(o) }, busy ? "Cancelling" : "Yes, cancel it"),
        h("button", { class: "button button-quiet button-small", type: "button", disabled: busy, dataset: { focus: `keep-${o.id}` },
          onclick: () => { state.confirmCancel = null; renderMine(); focusIn("cancel"); } }, "Keep it"));
    } else if (o.can_cancel) {
      actions.push(h("button", { class: "button button-quiet button-small", type: "button", dataset: { focus: `cancel-${o.id}` },
        onclick: () => { state.confirmCancel = o.token; renderMine(); focusIn("keep"); } }, "Cancel order"));
    }
    if (!ACTIVE.includes(o.status)) {
      actions.push(h("button", { class: "button button-small", type: "button", dataset: { focus: `again-${o.id}` },
        onclick: () => orderAgain(o) }, "Order again"));
    }
    if (state.shop?.phone) {
      actions.push(h("a", { class: "button button-quiet button-small", href: "tel:" + state.shop.phone.replace(/[^\d+]/g, "") },
        "Call the shop"));
    }
    return actions.length ? h("div", { class: "my-order-actions" }, actions) : null;
  }

  async function cancelMyOrder(o) {
    if (state.cancelling) return;
    state.cancelling = o.token;
    renderMine();
    try {
      const { order } = await api("/api/my-orders/cancel", { method: "POST", body: { token: o.token } });
      const entry = state.mine.find((e) => e.token === o.token);
      if (entry) entry.status = order.status;                // so it isn't announced again as a change
      saveMine();
      state.views = state.views.map((v) => (v.token === o.token ? order : v));
      toast(`Order #${o.id} is cancelled.`);
      load();                                                // its items are back on the counter
    } catch (error) {
      toast(error.message, true);
      loadMyOrders();                                        // maybe the shop confirmed it a moment ago
    } finally {
      state.cancelling = null;
      state.confirmCancel = null;
      renderMine();
    }
  }

  /* Put a past order's items back in the cart, as far as they're still available. */
  function orderAgain(o) {
    let added = 0;
    let short = false;
    for (const line of o.items) {
      const p = productById(line.product_id);
      const room = p ? p.stock - (state.cart[p.id] || 0) : 0;
      const qty = Math.min(line.quantity, room);
      if (qty < line.quantity) short = true;
      if (qty <= 0) continue;
      state.cart[p.id] = (state.cart[p.id] || 0) + qty;
      added += qty;
    }
    if (!added) return toast("Those items aren't available right now.", true);
    store.set("sc-cart", state.cart);
    renderCounter();
    closeOrders(false);
    openCart();
    toast(short ? "Added what's available now. Some items are sold out or have less stock." : "Added to your cart");
  }

  async function trackOrder(event) {
    event.preventDefault();
    const form = $("track-form");
    const problem = (message, field) => {
      $("track-error").textContent = message;
      $("track-error").hidden = false;
      if (field) form.elements[field].focus();
    };
    const id = Number(form.elements.order_id.value.replace(/\D/g, ""));
    const phone = form.elements.phone.value.trim();
    if (!Number.isInteger(id) || id < 1) return problem("Type the order number, for example 12.", "order_id");
    if (phone.replace(/\D/g, "").length < 10) return problem("Type the phone number used for the order (10 digits).", "phone");
    $("track-error").hidden = true;
    $("track-submit").disabled = true;
    try {
      const { order } = await api("/api/track", { method: "POST", body: { order_id: id, phone } });
      form.reset();
      $("track-box").open = false;
      toast(rememberOrder(order) ? `Order #${order.id} is now in My orders` : `Order #${order.id} is already in My orders`);
    } catch (error) {
      problem(error.message);
    } finally {
      $("track-submit").disabled = false;
    }
  }

  let focusBeforeOrders = null;

  function openOrders() {
    if (!$("cart-sheet").hidden) closeCart(false);
    focusBeforeOrders = document.activeElement?.closest("[hidden]") ? $("open-orders") : document.activeElement;
    state.mineKey = "";                                      // draw the list fresh
    state.shownIds = new Set();
    $("backdrop").hidden = false;
    $("orders-sheet").hidden = false;
    document.body.classList.add("locked");
    renderMine();
    loadMyOrders();
    $("close-orders").focus();
  }

  function closeOrders(restoreFocus = true) {
    $("orders-sheet").hidden = true;
    state.confirmCancel = null;
    if ($("cart-sheet").hidden) $("backdrop").hidden = true;
    if (!$("assistant").classList.contains("open") && $("cart-sheet").hidden) document.body.classList.remove("locked");
    if (restoreFocus) focusBeforeOrders?.focus?.();
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
    if ($("cart-sheet").hidden && $("orders-sheet").hidden) document.body.classList.remove("locked");
    $("chat-fab").focus();
  }

  const scrollChat = () => { const list = $("messages"); list.scrollTop = list.scrollHeight; };

  function messageView(entry) {
    if (entry.from === "order") {
      return h("li", { class: "receipt-wrap" }, receipt(entry.order),
        h("button", { class: "chip follow-chip", type: "button", onclick: () => openOrders() }, "Follow it in My orders"));
    }
    return h("li", { class: `msg ${entry.from}` }, entry.text);
  }

  function renderChat() {
    const greeting = { from: "shop", text: "Hi! I'm the shop's AI assistant. Ask me about our items, prices, offers or delivery, in any language. Tell me what you'd like and I can place the order for you." };
    const items = [greeting, ...state.chatLog].map(messageView);
    const questions = state.shop?.quick_questions || [];
    if (!state.chatLog.length && questions.length) {
      items.push(h("li", { class: "chat-suggestions" },
        questions.map((text) => h("button", { class: "chip", type: "button", onclick: () => sendChat(text) }, text))));
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
      for (const order of data.orders || []) {
        addMessage({ from: "order", order });
        rememberOrder(order);                                // chat orders show in My orders too
      }
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
    const focusable = [...container.querySelectorAll("button, input, textarea, select, a[href], summary")]
      .filter((el) => !el.disabled && el.offsetParent !== null);
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  }

  document.addEventListener("keydown", (event) => {
    const ordersOpen = !$("orders-sheet").hidden;
    const sheetOpen = !$("cart-sheet").hidden;
    const chatOpen = $("assistant").classList.contains("open");
    if (event.key === "Escape") {
      if (ordersOpen) closeOrders();
      else if (sheetOpen) closeCart();
      else if (chatOpen) closeChat();
    } else if (event.key === "Tab") {
      if (ordersOpen) trapFocus(event, $("orders-sheet"));
      else if (sheetOpen) trapFocus(event, $("cart-sheet"));
      else if (chatOpen) trapFocus(event, $("assistant"));
    }
  });

  // ---------------- wiring ----------------

  $("open-cart").addEventListener("click", openCart);
  $("cart-bar-open").addEventListener("click", openCart);
  $("close-cart").addEventListener("click", () => closeCart());
  $("open-orders").addEventListener("click", openOrders);
  $("close-orders").addEventListener("click", () => closeOrders());
  $("track-form").addEventListener("submit", trackOrder);
  $("backdrop").addEventListener("click", () => { if (!$("orders-sheet").hidden) closeOrders(); else closeCart(); });
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
  $("suggestions").addEventListener("click", (event) => {
    const chip = event.target.closest("[data-ask]");
    if (chip) { openChat(); sendChat(chip.dataset.ask); }
  });
  $("composer").addEventListener("submit", (event) => {
    event.preventDefault();
    const text = $("chat-input").value;
    $("chat-input").value = "";
    sendChat(text);
  });

  const refresh = () => { if (!document.hidden) { load(); loadMyOrders(); } };
  fillSavedDetails();
  renderChat();
  load();
  loadMyOrders();
  setInterval(tick, 1000);
  setInterval(() => { if (!document.hidden) load(); }, 20000);                          // owner's changes within 20 s
  setInterval(() => { if (!document.hidden && state.mine.length) loadMyOrders(); }, 15000);   // order status within 15 s
  document.addEventListener("visibilitychange", refresh);
})();
