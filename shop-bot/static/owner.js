/* The owner desk: sign in, see orders, change items, prices, stock, offers and shop details. */
"use strict";

(() => {
  const { h, money, api, syncClock, ago, toast, plate } = Common;
  const $ = (id) => document.getElementById(id);

  const EMOJIS = ["🎂", "🍰", "🧁", "🍫", "🍪", "🥐", "🥖", "🍞", "🍩", "🍮", "🍍", "🍓", "🥤", "☕"];
  const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
  const SOURCES = { cart: "the shop website", chat: "the chat assistant", whatsapp: "WhatsApp",
                    instagram: "Instagram", terminal: "a terminal test" };
  const STATUS_NAMES = { new: "New", preparing: "Preparing", ready: "Ready", completed: "Completed", cancelled: "Cancelled" };

  const state = {
    orders: [], stats: null, products: [], view: "waiting",
    lastMaxId: null, freshIds: new Set(), openOffers: new Set(),
    sound: false, audio: null, pollTimer: null,
  };

  // ---------------- signing in ----------------

  async function start() {
    try {
      const me = await api("/api/owner/me");
      if (me.signed_in) showDesk();
      else showSignIn(me.password_set);
    } catch (error) {
      showSignIn(true, error.message);
    }
  }

  function showSignIn(passwordSet = true, message = "") {
    clearInterval(state.pollTimer);
    $("desk").hidden = true;
    $("sign-out").hidden = true;
    $("sign-in-view").hidden = false;
    $("no-password").hidden = passwordSet;
    $("sign-in-error").hidden = !message;
    $("sign-in-error").textContent = message;
    $("sign-in-form").elements.password.focus();
  }

  async function signIn(event) {
    event.preventDefault();
    const field = $("sign-in-form").elements.password;
    try {
      await api("/api/owner/login", { method: "POST", body: { password: field.value } });
      field.value = "";
      showDesk();
    } catch (error) {
      $("sign-in-error").textContent = error.message;
      $("sign-in-error").hidden = false;
      field.select();
    }
  }

  async function signOut() {
    try { await api("/api/owner/logout", { method: "POST" }); } catch { /* signed out anyway */ }
    showSignIn(true);
  }

  /* Every owner request goes through here: if the sign-in ran out, show the sign-in form. */
  async function ownerApi(path, options) {
    try {
      return await api(path, options);
    } catch (error) {
      if (error.status === 401) showSignIn(true, "Please sign in again.");
      throw error;
    }
  }

  function showDesk() {
    $("sign-in-view").hidden = true;
    $("desk").hidden = false;
    $("sign-out").hidden = false;
    loadOrders();
    loadSettings();
    clearInterval(state.pollTimer);
    state.pollTimer = setInterval(() => { if (!document.hidden) loadOrders(); }, 8000);
  }

  // ---------------- tabs ----------------

  const tabs = ["orders", "items", "shop"];

  function selectTab(name, focus = false) {
    for (const tab of tabs) {
      const button = $(`tab-${tab}`);
      const selected = tab === name;
      button.setAttribute("aria-selected", String(selected));
      button.tabIndex = selected ? 0 : -1;
      $(`panel-${tab}`).hidden = !selected;
      if (selected && focus) button.focus();
    }
    if (name === "items") loadItems();
    if (name === "shop") loadSettings();
  }

  // ---------------- orders ----------------

  async function loadOrders() {
    let data;
    try { data = await ownerApi("/api/owner/orders"); } catch { return; }
    syncClock(data.server_now);
    const maxId = Math.max(0, ...data.orders.map((o) => o.id));
    if (state.lastMaxId !== null && maxId > state.lastMaxId) {
      const fresh = data.orders.filter((o) => o.id > state.lastMaxId);
      for (const order of fresh) {
        state.freshIds.add(order.id);
        setTimeout(() => { state.freshIds.delete(order.id); renderOrders(); }, 120000);
      }
      toast(fresh.length === 1 ? `New order #${fresh[0].id} from ${fresh[0].customer_name}` : `${fresh.length} new orders`);
      chime();
    }
    state.lastMaxId = maxId;
    state.orders = data.orders;
    state.stats = data.stats;
    renderOrders();
  }

  function renderToday() {
    const s = state.stats;
    if (!s) return;
    const strong = (text) => h("strong", {}, text);
    const parts = ["Today: ", strong(`${s.today_orders} ${s.today_orders === 1 ? "order" : "orders"}`), ", ",
      strong(money(s.today_revenue)), " taken. ", strong(String(s.waiting)), " waiting."];
    if (s.low_stock) parts.push(" ", strong(String(s.low_stock)), ` ${s.low_stock === 1 ? "item is" : "items are"} running low.`);
    $("today-line").replaceChildren(...parts);
  }

  function renderOrders() {
    renderToday();
    const newCount = state.orders.filter((o) => o.status === "new").length;
    $("new-badge").hidden = newCount === 0;
    $("new-badge").textContent = newCount;
    document.title = newCount ? `(${newCount}) Owner desk` : "Owner desk";

    const view = $("orders-view");
    if (state.view === "waiting") {
      view.replaceChildren(h("div", { class: "board" }, ["new", "preparing", "ready"].map((status) => {
        const orders = state.orders.filter((o) => o.status === status).reverse();      // oldest first
        return h("section", { class: "lane", "aria-label": STATUS_NAMES[status] },
          h("h2", {}, STATUS_NAMES[status], h("span", {}, `${orders.length}`)),
          h("div", { class: "lane-list" }, orders.length ? orders.map(orderCard)
            : h("p", { class: "lane-empty" }, status === "new" ? "No new orders. New ones appear here by themselves." : "Nothing here right now.")));
      })));
    } else {
      const orders = state.orders.filter((o) => o.status === state.view).slice(0, 60);
      view.replaceChildren(h("div", { class: "order-list" }, orders.length ? orders.map(orderCard)
        : h("p", { class: "lane-empty" }, `No ${state.view} orders yet.`)));
    }
  }

  function phoneText(digits) {
    if (digits.length === 12 && digits.startsWith("91")) return `+91 ${digits.slice(2, 7)} ${digits.slice(7)}`;
    if (digits.length === 10) return `${digits.slice(0, 5)} ${digits.slice(5)}`;
    return digits;
  }

  function orderCard(o) {
    const actions = [];
    const nextStep = { new: ["preparing", "Start preparing"], preparing: ["ready", "Mark ready"],
      ready: ["completed", o.fulfilment === "delivery" ? "Mark delivered" : "Mark picked up"] }[o.status];
    if (nextStep) {
      actions.push(h("button", { class: "button button-small", type: "button",
        onclick: () => setStatus(o, nextStep[0]) }, nextStep[1]));
    }
    if (o.status !== "completed" && o.status !== "cancelled") {
      actions.push(h("button", { class: "button button-quiet button-small", type: "button",
        onclick: () => { if (confirm(`Cancel order #${o.id}? The items go back into stock.`)) setStatus(o, "cancelled"); } },
        "Cancel order"));
    }
    const delivery = o.fulfilment === "delivery"
      ? `Delivery to ${o.address}${o.delivery_fee ? ` (delivery fee ${money(o.delivery_fee)})` : " (free delivery)"}`
      : "Pickup at the shop";
    return h("article", { class: "order" + (state.freshIds.has(o.id) ? " fresh" : ""), "aria-label": `Order ${o.id}` },
      h("div", { class: "order-head" }, h("h3", {}, `#${o.id}`), h("span", { class: "tag" }, money(o.total))),
      h("p", { class: "who" }, h("strong", {}, o.customer_name),
        h("a", { href: `tel:${o.phone.length === 12 ? "+" : ""}${o.phone}` }, `Call ${phoneText(o.phone)}`)),
      h("ul", {}, o.items.map((line) => h("li", {}, `${line.quantity} × ${line.name}`))),
      h("p", {}, delivery),
      h("p", {}, `Wanted: ${o.wanted_at}`),
      o.notes ? h("p", { class: "note" }, `Note: ${o.notes}`) : null,
      h("p", { class: "meta" }, `Ordered ${ago(o.created_at)} through ${SOURCES[o.source] || o.source}`),
      actions.length ? h("div", { class: "actions" }, actions) : null);
  }

  async function setStatus(order, status) {
    try {
      const { order: updated } = await ownerApi(`/api/owner/orders/${order.id}/status`, { method: "POST", body: { status } });
      state.orders = state.orders.map((o) => (o.id === updated.id ? updated : o));
      state.freshIds.delete(order.id);
      renderOrders();
      toast(`Order #${order.id} is now ${STATUS_NAMES[status].toLowerCase()}`);
      loadOrders();
      if (status === "cancelled" && !$("panel-items").hidden) loadItems();
    } catch (error) {
      toast(error.message, true);
    }
  }

  /* A short two-note chime for new orders (browsers only allow sound after a click). */
  function toggleSound() {
    state.audio = state.audio || new (window.AudioContext || window.webkitAudioContext)();
    state.sound = !state.sound;
    $("sound-toggle").setAttribute("aria-pressed", String(state.sound));
    $("sound-toggle").textContent = state.sound ? "Turn off new-order sound" : "Turn on new-order sound";
    if (state.sound) { state.audio.resume(); chime(); }
  }

  function chime() {
    if (!state.sound || !state.audio) return;
    const start = state.audio.currentTime;
    [880, 1175].forEach((frequency, i) => {
      const tone = state.audio.createOscillator();
      const volume = state.audio.createGain();
      const at = start + i * 0.18;
      tone.frequency.value = frequency;
      volume.gain.setValueAtTime(0.0001, at);
      volume.gain.exponentialRampToValueAtTime(0.25, at + 0.02);
      volume.gain.exponentialRampToValueAtTime(0.0001, at + 0.28);
      tone.connect(volume).connect(state.audio.destination);
      tone.start(at);
      tone.stop(at + 0.3);
    });
  }

  // ---------------- items ----------------

  async function loadItems() {
    try {
      const data = await ownerApi("/api/owner/products");
      syncClock(data.server_now);
      state.products = data.products;
      renderItems();
    } catch (error) {
      if (error.status !== 401) toast(error.message, true);
    }
  }

  function renderItems() {
    const categories = [...new Set(state.products.map((p) => p.category))];
    $("category-list").replaceChildren(...categories.map((c) => h("option", { value: c })));
    $("items-list").replaceChildren(...(state.products.length ? state.products.map(itemRow)
      : [h("p", { class: "lane-empty" }, "No items yet. Add your first item to open the counter.")]));
  }

  function replaceRow(product) {
    state.products = state.products.map((p) => (p.id === product.id ? product : p));
    const old = document.querySelector(`.item-row[data-id="${product.id}"]`);
    const focusKey = document.activeElement?.dataset?.focus;
    if (old) old.replaceWith(itemRow(product));
    if (focusKey) document.querySelector(`[data-focus="${focusKey}"]`)?.focus();
  }

  async function save(product, changes, message = "Saved") {
    try {
      const { product: updated } = await ownerApi(`/api/owner/products/${product.id}`, { method: "PATCH", body: changes });
      replaceRow(updated);
      toast(message);
    } catch (error) {
      toast(error.message, true);
      replaceRow(product);                                     // put the old value back
    }
  }

  const commitOnEnter = (event) => { if (event.key === "Enter") event.target.blur(); };

  /* An emptied number box puts the old value back, instead of saving 0 by accident. */
  function saveNumber(product, key, input, message) {
    if (input.value.trim() === "") return replaceRow(product);
    save(product, { [key]: Number(input.value) }, message);
  }

  function itemRow(p) {
    const low = p.stock === 0 ? "Sold out" : p.stock <= 3 ? "Running low" : null;
    return h("article", { class: "item-row" + (p.visible ? "" : " hidden-item"), dataset: { id: p.id },
      "aria-label": p.name },
      plate(p),
      h("div", { class: "row-main" },
        h("div", { class: "row-line" },
          h("input", { class: "inline name", value: p.name, maxlength: 60, "aria-label": "Item name",
            dataset: { focus: `name-${p.id}` }, onkeydown: commitOnEnter,
            onchange: (e) => save(p, { name: e.target.value }) }),
          h("input", { class: "inline category", value: p.category, maxlength: 30, list: "category-list",
            "aria-label": `Category of ${p.name}`, dataset: { focus: `cat-${p.id}` }, onkeydown: commitOnEnter,
            onchange: (e) => save(p, { category: e.target.value }) })),
        h("input", { class: "inline desc", value: p.description, maxlength: 160, placeholder: "Add a short description",
          "aria-label": `Description of ${p.name}`, dataset: { focus: `desc-${p.id}` }, onkeydown: commitOnEnter,
          onchange: (e) => save(p, { description: e.target.value }) }),
        h("div", { class: "row-line" },
          h("label", { class: "money-field" }, "₹",
            h("input", { type: "number", min: 1, step: 1, value: p.price, "aria-label": `Price of ${p.name}`,
              dataset: { focus: `price-${p.id}` }, onkeydown: commitOnEnter,
              onchange: (e) => saveNumber(p, "price", e.target, "Price saved") })),
          h("div", { class: "stock-control" },
            h("span", { class: "label" }, "Stock"),
            h("div", { class: "stepper" },
              h("button", { type: "button", "aria-label": `One less ${p.name} in stock`, dataset: { focus: `minus-${p.id}` },
                disabled: p.stock <= 0, onclick: () => save(p, { stock: p.stock - 1 }, "Stock saved") }, "−"),
              h("input", { type: "number", min: 0, step: 1, value: p.stock, "aria-label": `Stock of ${p.name}`,
                dataset: { focus: `stock-${p.id}` }, onkeydown: commitOnEnter,
                onchange: (e) => saveNumber(p, "stock", e.target, "Stock saved") }),
              h("button", { type: "button", "aria-label": `One more ${p.name} in stock`, dataset: { focus: `plus-${p.id}` },
                onclick: () => save(p, { stock: p.stock + 1 }, "Stock saved") }, "+")),
            low ? h("span", { class: "stock-low" }, low) : null),
          h("label", { class: "switch" },
            h("input", { type: "checkbox", checked: p.visible, dataset: { focus: `show-${p.id}` },
              onchange: (e) => save(p, { visible: e.target.checked }, e.target.checked ? "Now showing in the shop" : "Hidden from the shop") }),
            p.visible ? "Showing in shop" : "Hidden from shop")),
        offerBox(p),
        h("div", { class: "row-tools" },
          p.offer_price === null && !state.openOffers.has(p.id)
            ? h("button", { class: "button button-quiet button-small", type: "button", dataset: { focus: `offer-${p.id}` },
                onclick: () => { state.openOffers.add(p.id); replaceRow(p); } }, "Start an offer")
            : null,
          h("label", { class: "button button-quiet button-small file-button" },
            p.image ? "Change photo" : "Add photo",
            h("input", { type: "file", accept: "image/*", "aria-label": `Photo for ${p.name}`,
              onchange: (e) => uploadPhoto(p, e.target.files[0]) })),
          p.image ? h("button", { class: "button button-quiet button-small", type: "button",
            onclick: () => removePhoto(p) }, "Remove photo") : null,
          h("button", { class: "button button-quiet button-small danger", type: "button",
            onclick: () => deleteItem(p) }, "Delete item"))));
  }

  function untilText(iso) {
    return new Date(iso).toLocaleString("en-IN", { weekday: "short", day: "numeric", month: "short",
      hour: "numeric", minute: "2-digit", timeZone: "Asia/Kolkata" });
  }

  function offerBox(p) {
    if (p.offer_price !== null) {
      return h("div", { class: "offer-box" },
        h("span", { class: "tag" }, h("s", {}, money(p.price)), money(p.offer_price)),
        h("span", {}, `Offer until ${untilText(p.offer_ends_at)}`),
        h("button", { class: "button button-quiet button-small", type: "button", dataset: { focus: `end-offer-${p.id}` },
          onclick: () => endOffer(p) }, "End offer"));
    }
    if (!state.openOffers.has(p.id)) return null;          // the "Start an offer" button sits with the other tools
    const presets = [["1h", "For 1 hour"], ["3h", "For 3 hours"], ["closing", "Until closing"],
                     ["midnight", "Until midnight"], ["custom", "Pick a time"]];
    const custom = h("label", { class: "field custom-time", hidden: true },
      h("span", {}, "Offer ends at"), h("input", { type: "datetime-local", name: "ends_at" }));
    const form = h("form", { class: "offer-form", "aria-label": `Offer for ${p.name}` },
      h("label", { class: "money-field" }, "Offer price ₹",
        h("input", { type: "number", name: "offer_price", min: 1, max: p.price - 1, step: 1, required: true,
          dataset: { focus: `offer-price-${p.id}` } })),
      h("div", { class: "presets", role: "group", "aria-label": "How long the offer runs" },
        presets.map(([value, label]) => h("label", {},
          h("input", { type: "radio", name: `preset-${p.id}`, value, checked: value === "closing",
            onchange: () => { custom.hidden = value !== "custom"; } }), label))),
      custom,
      h("div", { class: "form-actions" },
        h("button", { class: "button button-small", type: "submit" }, "Start offer"),
        h("button", { class: "button button-quiet button-small", type: "button",
          onclick: () => { state.openOffers.delete(p.id); replaceRow(p); } }, "Cancel")));
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const preset = form.querySelector(`input[name="preset-${p.id}"]:checked`).value;
      const offerPrice = Number(form.elements.offer_price.value);
      if (!Number.isInteger(offerPrice) || offerPrice < 1) {
        toast("Type the offer price in whole rupees.", true);
        return form.elements.offer_price.focus();
      }
      try {
        const { product } = await ownerApi(`/api/owner/products/${p.id}/offer`, { method: "PUT", body: {
          offer_price: offerPrice, preset, ends_at: form.elements.ends_at.value } });
        state.openOffers.delete(p.id);
        replaceRow(product);
        toast(`Offer started on ${p.name}`);
      } catch (error) {
        toast(error.message, true);
      }
    });
    setTimeout(() => form.elements.offer_price.focus(), 0);
    return h("div", { class: "offer-box" }, form);
  }

  async function endOffer(p) {
    try {
      const { product } = await ownerApi(`/api/owner/products/${p.id}/offer`, { method: "DELETE" });
      replaceRow(product);
      toast(`Offer ended on ${p.name}`);
    } catch (error) {
      toast(error.message, true);
    }
  }

  /* Shrink the photo in the browser first (max 900 px), so uploads stay small and quick. */
  async function photoData(file) {
    if (!file || !file.type.startsWith("image/")) throw new Error("Choose a photo (JPG, PNG or WEBP).");
    let bitmap;
    try { bitmap = await createImageBitmap(file); }
    catch { throw new Error("That photo type can't be opened here. Try a JPG or PNG."); }
    const scale = Math.min(1, 900 / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bitmap.width * scale);
    canvas.height = Math.round(bitmap.height * scale);
    canvas.getContext("2d").drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL("image/jpeg", 0.85);
  }

  async function uploadPhoto(p, file) {
    try {
      const image = await photoData(file);
      const { product } = await ownerApi(`/api/owner/products/${p.id}/photo`, { method: "PUT", body: { image } });
      replaceRow(product);
      toast("Photo saved");
    } catch (error) {
      toast(error.message, true);
    }
  }

  async function removePhoto(p) {
    try {
      const { product } = await ownerApi(`/api/owner/products/${p.id}/photo`, { method: "DELETE" });
      replaceRow(product);
      toast("Photo removed");
    } catch (error) {
      toast(error.message, true);
    }
  }

  async function deleteItem(p) {
    if (!confirm(`Delete ${p.name}? This can't be undone. Past orders keep its name.`)) return;
    try {
      await ownerApi(`/api/owner/products/${p.id}`, { method: "DELETE" });
      state.products = state.products.filter((x) => x.id !== p.id);
      renderItems();
      toast(`Deleted ${p.name}`);
    } catch (error) {
      toast(error.message, true);
    }
  }

  function setUpAddForm() {
    $("emoji-row").replaceChildren(...EMOJIS.map((emoji, i) => h("label", {},
      h("input", { type: "radio", name: "emoji", value: emoji, checked: i === 0, "aria-label": `Picture ${emoji}` }), emoji)));
    $("show-add-item").addEventListener("click", () => {
      $("add-item").hidden = false;
      $("add-item").elements.name.focus();
    });
    $("cancel-add").addEventListener("click", () => { $("add-item").hidden = true; $("add-item").reset(); });
    $("add-item").addEventListener("submit", async (event) => {
      event.preventDefault();
      const form = $("add-item");
      const value = (name) => form.elements[name].value.trim();
      const problem = (text) => { $("add-error").textContent = text; $("add-error").hidden = false; };
      if (!value("name") || !value("category")) return problem("Give the item a name and a category.");
      if (!(Number(value("price")) >= 1)) return problem("Give the item a price of at least ₹1.");
      try {
        const { product } = await ownerApi("/api/owner/products", { method: "POST", body: {
          name: value("name"), category: value("category"), description: value("description"),
          emoji: form.elements.emoji.value, price: Number(value("price")), stock: Number(value("stock") || 0) } });
        state.products = [...state.products, product];
        renderItems();
        form.reset();
        form.hidden = true;
        $("add-error").hidden = true;
        toast(`Added ${product.name} to the shop`);
        document.querySelector(`.item-row[data-id="${product.id}"]`)?.scrollIntoView({ block: "center" });
      } catch (error) {
        problem(error.message);
      }
    });
  }

  // ---------------- shop details ----------------

  async function loadSettings() {
    try {
      const { settings } = await ownerApi("/api/owner/settings");
      fillSettings(settings);
    } catch { /* shown elsewhere */ }
  }

  function fillSettings(s) {
    const form = $("shop-form");
    $("desk-shop-name").textContent = s.shop_name;
    for (const key of ["shop_name", "phone", "tagline", "address", "open_time", "close_time",
                       "delivery_fee", "free_delivery_above", "delivery_area", "assistant_notes"]) {
      if (form.elements[key] !== document.activeElement) form.elements[key].value = s[key];
    }
    $("day-row").replaceChildren(...DAYS.map((day) => h("label", {},
      h("input", { type: "checkbox", name: "closed_days", value: day, checked: s.closed_days.includes(day) }), day)));
  }

  async function saveSettings(event) {
    event.preventDefault();
    const form = $("shop-form");
    const value = (name) => form.elements[name].value.trim();
    const body = {
      shop_name: value("shop_name"), phone: value("phone"), tagline: value("tagline"), address: value("address"),
      open_time: value("open_time"), close_time: value("close_time"),
      closed_days: [...form.querySelectorAll('input[name="closed_days"]:checked')].map((box) => box.value),
      delivery_fee: Number(value("delivery_fee")), free_delivery_above: Number(value("free_delivery_above")),
      delivery_area: value("delivery_area"), assistant_notes: form.elements.assistant_notes.value.trim(),
    };
    try {
      const { settings } = await ownerApi("/api/owner/settings", { method: "PUT", body });
      fillSettings(settings);
      $("shop-error").hidden = true;
      toast("Shop details saved");
    } catch (error) {
      $("shop-error").textContent = error.message;
      $("shop-error").hidden = false;
    }
  }

  // ---------------- wiring ----------------

  $("sign-in-form").addEventListener("submit", signIn);
  $("sign-out").addEventListener("click", signOut);
  $("sound-toggle").addEventListener("click", toggleSound);
  $("shop-form").addEventListener("submit", saveSettings);
  for (const tab of tabs) $(`tab-${tab}`).addEventListener("click", () => selectTab(tab));
  document.querySelector(".tabs").addEventListener("keydown", (event) => {
    const current = tabs.findIndex((tab) => $(`tab-${tab}`).getAttribute("aria-selected") === "true");
    if (event.key === "ArrowRight") selectTab(tabs[(current + 1) % tabs.length], true);
    if (event.key === "ArrowLeft") selectTab(tabs[(current + tabs.length - 1) % tabs.length], true);
  });
  for (const button of document.querySelectorAll("[data-view]")) {
    button.addEventListener("click", () => {
      state.view = button.dataset.view;
      for (const other of document.querySelectorAll("[data-view]")) other.setAttribute("aria-pressed", String(other === button));
      renderOrders();
    });
  }
  document.addEventListener("visibilitychange", () => { if (!document.hidden && !$("desk").hidden) loadOrders(); });

  setUpAddForm();
  start();
})();
