/* The owner desk: sign in, see orders, change items, prices, stock, offers and shop details. */
"use strict";

(() => {
  const { h, money, api, syncClock, ago, toast, plate } = Common;
  const $ = (id) => document.getElementById(id);

  const EMOJIS = ["🎂", "🍰", "🧁", "🍫", "🍪", "🥐", "🥖", "🍞", "🍩", "🍮", "🍍", "🍓", "🥤", "☕",
                  "🍕", "🍔", "🍛", "🥗", "🍎", "🥦", "🥛", "🧃", "🍦", "🛍️", "👕", "👟", "💄", "🧴",
                  "💊", "📱", "🔌", "📚", "🌸", "🎁", "🧸", "🪔"];
  const SHOP_EMOJIS = ["🧁", "🎂", "🍕", "🍛", "🥦", "🍎", "☕", "🛍️", "👕", "💊", "📱", "🌸", "🎁", "🪔"];
  const DONE_TEXT = { new: "moved back to new", preparing: "confirmed", ready: "marked ready",
                      completed: "marked done", cancelled: "cancelled" };
  const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
  const SOURCES = { cart: "the shop website", chat: "the chat assistant", whatsapp: "WhatsApp",
                    instagram: "Instagram", terminal: "a terminal test" };
  const STATUS_NAMES = { new: "New", preparing: "Preparing", ready: "Ready", completed: "Completed", cancelled: "Cancelled" };

  const state = {
    orders: [], stats: null, products: [], view: "waiting",
    lastMaxId: null, freshIds: new Set(), openOffers: new Set(),
    sound: false, audio: null, pollTimer: null,
    lastStatus: null,                           // order id -> status at the last check (to spot customer cancels)
    search: "", searchResults: null, searchTimer: null,
    stock: null, stockKey: "", openHistory: new Set(), histories: {},
    report: null, period: "7d",
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

  const tabs = ["orders", "items", "stock", "report", "shop"];

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
    if (name === "stock") loadStock();
    if (name === "report") loadReport();
    if (name === "shop") loadSettings();
  }

  // ---------------- orders ----------------

  async function loadOrders() {
    let data;
    try { data = await ownerApi("/api/owner/orders"); } catch { return; }
    syncClock(data.server_now);
    const maxId = Math.max(0, ...data.orders.map((o) => o.id));
    const previousMax = state.lastMaxId;
    const before = state.lastStatus;
    const messages = [];
    if (previousMax !== null && maxId > previousMax) {
      const fresh = data.orders.filter((o) => o.id > previousMax && o.status !== "cancelled");
      for (const order of fresh) {
        state.freshIds.add(order.id);
        setTimeout(() => { state.freshIds.delete(order.id); renderOrders(); }, 120000);
      }
      if (fresh.length) messages.push(fresh.length === 1 ? `New order #${fresh[0].id} from ${fresh[0].customer_name}.` : `${fresh.length} new orders.`);
    }
    // A customer cancelled: an order that was waiting at the last check, or a new one that arrived already cancelled.
    const cancelledByCustomer = before === null ? [] : data.orders.filter((o) => o.status === "cancelled"
      && o.cancelled_by === "customer" && (before.has(o.id) ? before.get(o.id) !== "cancelled" : o.id > previousMax));
    if (cancelledByCustomer.length) {
      messages.push(cancelledByCustomer.length === 1
        ? `${cancelledByCustomer[0].customer_name} cancelled order #${cancelledByCustomer[0].id}. The items are back in stock.`
        : `${cancelledByCustomer.length} orders were cancelled by customers. The items are back in stock.`);
    }
    if (messages.length) {
      toast(messages.join(" "), cancelledByCustomer.length > 0);
      chime();
    }
    state.lastMaxId = maxId;
    state.lastStatus = new Map(data.orders.map((o) => [o.id, o.status]));
    state.orders = data.orders;
    state.stats = data.stats;
    renderOrders();
    if (state.search) runSearch(state.search);
    if (!$("panel-items").hidden) refreshItems();
    if (!$("panel-stock").hidden) loadStock(true);
  }

  function renderToday() {
    const s = state.stats;
    if (!s) return;
    const strong = (text) => h("strong", {}, text);
    const parts = ["Today: ", strong(`${s.today_orders} ${s.today_orders === 1 ? "order" : "orders"}`), " worth ",
      strong(money(s.today_revenue)), ". ", strong(String(s.waiting)), " waiting."];
    if (s.low_stock) parts.push(" ", strong(String(s.low_stock)), ` ${s.low_stock === 1 ? "item is" : "items are"} running low.`);
    $("today-line").replaceChildren(...parts);
    $("stock-badge").hidden = !s.low_stock;
    $("stock-badge").textContent = s.low_stock;
  }

  function renderOrders() {
    renderToday();
    const newCount = state.orders.filter((o) => o.status === "new").length;
    $("new-badge").hidden = newCount === 0;
    $("new-badge").textContent = newCount;
    document.title = newCount ? `(${newCount}) Owner desk` : "Owner desk";

    const view = $("orders-view");
    if (state.searchResults !== null) {
      const found = state.searchResults;
      view.replaceChildren(
        h("p", { class: "search-note" }, found.length
          ? `${found.length} ${found.length === 1 ? "order matches" : "orders match"} "${state.search}"${found.length === 100 ? " (showing the newest 100)" : ""}.`
          : `No orders match "${state.search}". Try part of the name, the last digits of the phone, or the order number.`),
        h("div", { class: "order-list" }, found.map((o) => orderCard(o, true))));
      return;
    }
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

  function orderCard(o, showStatus = false) {
    const actions = [];
    const nextStep = { new: ["preparing", "Confirm order"], preparing: ["ready", "Mark ready"],
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
    const cancelledBy = o.status !== "cancelled" ? null
      : o.cancelled_by === "customer" ? "Cancelled by the customer" : o.cancelled_by === "shop" ? "Cancelled by you" : "Cancelled";
    return h("article", { class: "order" + (state.freshIds.has(o.id) ? " fresh" : ""), "aria-label": `Order ${o.id}` },
      h("div", { class: "order-head" }, h("h3", {}, `#${o.id}`),
        showStatus ? h("span", { class: `pill pill-${o.status}` }, STATUS_NAMES[o.status]) : null,
        h("span", { class: "tag" }, money(o.total))),
      cancelledBy ? h("p", { class: "cancelled-by" }, cancelledBy) : null,
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
      if (state.searchResults) state.searchResults = state.searchResults.map((o) => (o.id === updated.id ? updated : o));
      state.freshIds.delete(order.id);
      if (state.lastStatus) state.lastStatus.set(updated.id, updated.status);
      renderOrders();
      toast(`Order #${order.id} ${DONE_TEXT[status]}`);
      loadOrders();
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
                disabled: p.stock <= 0, onclick: () => changeStock(p, -1) }, "−"),
              h("input", { type: "number", min: 0, step: 1, value: p.stock, "aria-label": `Stock of ${p.name}`,
                dataset: { focus: `stock-${p.id}` }, onkeydown: commitOnEnter,
                onchange: (e) => saveNumber(p, "stock", e.target, "Stock saved") }),
              h("button", { type: "button", "aria-label": `One more ${p.name} in stock`, dataset: { focus: `plus-${p.id}` },
                onclick: () => changeStock(p, 1) }, "+")),
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

  // ---------------- safe stock changes and quiet refresh (items tab) ----------------

  /* + and − add to the stock on the server, so a sale made meanwhile is never undone. */
  async function changeStock(p, change) {
    try {
      const { product } = await ownerApi(`/api/owner/products/${p.id}/stock`, { method: "POST", body: { change } });
      replaceRow(product);
      toast(`${product.name}: ${product.stock} in stock`);
    } catch (error) {
      toast(error.message, true);
    }
  }

  /* While the items tab is open, show sales as they happen, without disturbing an item being edited. */
  async function refreshItems() {
    let data;
    try { data = await ownerApi("/api/owner/products"); } catch { return; }
    syncClock(data.server_now);
    const sameItems = data.products.length === state.products.length
      && data.products.every((p, i) => p.id === state.products[i].id);
    if (!sameItems) {
      if ($("items-list").contains(document.activeElement) || state.openOffers.size) return;   // try next round
      state.products = data.products;
      renderItems();
      return;
    }
    for (const fresh of data.products) {
      const old = state.products.find((p) => p.id === fresh.id);
      if (JSON.stringify(old) === JSON.stringify(fresh) || state.openOffers.has(fresh.id)) continue;
      const row = document.querySelector(`.item-row[data-id="${fresh.id}"]`);
      if (row && row.contains(document.activeElement)) continue;                            // being edited
      replaceRow(fresh);
    }
  }

  // ---------------- stock tab ----------------

  const REASONS = { order: (m) => `Order #${m.order_id}`, cancel: (m) => `Order #${m.order_id} cancelled`,
                    owner: () => "Changed by you", added: () => "New item" };

  async function loadStock(quiet = false) {
    let data;
    try { data = await ownerApi("/api/owner/stock"); }
    catch (error) { if (!quiet && error.status !== 401) toast(error.message, true); return; }
    syncClock(data.server_now);
    state.stock = data;
    renderStock(quiet);
  }

  function renderStock(quiet = false) {
    const data = state.stock;
    if (!data) return;
    const list = $("stock-list");
    const key = JSON.stringify([data.items, data.moves, [...state.openHistory], state.histories]);
    if (quiet && (key === state.stockKey || list.contains(document.activeElement) && document.activeElement.tagName === "INPUT")) return;
    state.stockKey = key;
    const shown = data.items.filter((i) => i.visible);
    const out = shown.filter((i) => i.level === "sold_out").length;
    const low = shown.filter((i) => i.level === "low").length;
    $("stock-summary").textContent = out || low
      ? [out ? `${out} sold out` : "", low ? `${low} running low (${data.low_stock} or fewer left)` : ""].filter(Boolean).join(", ") + "."
      : "Everything in the shop has stock.";
    const focusKey = document.activeElement?.dataset?.focus;
    list.replaceChildren(...(data.items.length ? data.items.map(stockRow)
      : [h("p", { class: "lane-empty" }, "No items yet. Add items in the Items tab.")]));
    $("stock-moves").replaceChildren(...(data.moves.length ? data.moves.map((m) => moveLine(m, true))
      : [h("li", { class: "lane-empty" }, "No stock changes yet.")]));
    if (focusKey) document.querySelector(`[data-focus="${focusKey}"]`)?.focus();
  }

  function daysText(days) {
    if (days < 1) return "less than a day";
    const whole = Math.floor(days);
    return `${whole} ${whole === 1 ? "day" : "days"}`;
  }

  function stockRow(i) {
    const [levelText, levelClass] = { sold_out: ["Sold out", "level-out"], low: ["Running low", "level-low"],
                                      ok: ["In stock", "level-ok"] }[i.level];
    const pace = i.sold_7d ? `${i.sold_7d} sold in the last 7 days` : "none sold in the last 7 days";
    const open = state.openHistory.has(i.id);
    const addBox = h("form", { class: "add-stock", "aria-label": `Add stock to ${i.name}` },
      h("input", { type: "number", min: 1, max: 100000, step: 1, placeholder: "How many", "aria-label": `How many ${i.name} to add`,
        dataset: { focus: `s-add-${i.id}` } }),
      h("button", { class: "button button-small", type: "submit" }, "Add"));
    addBox.addEventListener("submit", (event) => {
      event.preventDefault();
      const amount = Number(addBox.elements[0].value);
      if (!Number.isInteger(amount) || amount < 1) {
        toast("Type how many to add, like 12.", true);
        return addBox.elements[0].focus();
      }
      stockChange(i, amount);
    });
    return h("article", { class: "stock-row" + (i.visible ? "" : " hidden-item"), dataset: { id: i.id }, "aria-label": i.name },
      plate(i),
      h("div", { class: "stock-main" },
        h("div", { class: "stock-title" },
          h("h3", {}, i.name),
          h("span", { class: `level ${levelClass}` }, levelText),
          i.visible ? null : h("span", { class: "muted" }, "Hidden from the shop")),
        h("p", { class: "stock-pace" }, h("strong", { class: "stock-number" }, String(i.stock)), " in stock · ", pace,
          i.days_left !== null ? ` · about ${daysText(i.days_left)} left at this pace` : ""),
        h("div", { class: "stock-tools" },
          h("div", { class: "quick-add", role: "group", "aria-label": `Change the stock of ${i.name}` },
            h("button", { class: "button button-quiet button-small", type: "button", disabled: i.stock <= 0,
              "aria-label": `One less ${i.name}`, dataset: { focus: `s-minus-${i.id}` }, onclick: () => stockChange(i, -1) }, "−1"),
            [1, 5, 10].map((n) => h("button", { class: "button button-quiet button-small", type: "button",
              "aria-label": `Add ${n} ${i.name}`, dataset: { focus: `s-plus${n}-${i.id}` }, onclick: () => stockChange(i, n) }, `+${n}`))),
          addBox,
          h("button", { class: "button button-quiet button-small", type: "button", "aria-expanded": String(open),
            dataset: { focus: `s-history-${i.id}` }, onclick: () => toggleHistory(i) }, open ? "Hide history" : "History")),
        open ? historyBox(i) : null));
  }

  function historyBox(i) {
    const moves = state.histories[i.id];
    if (!moves) return h("p", { class: "panel-help" }, "Loading history");
    return h("ol", { class: "moves history" }, moves.length ? moves.map((m) => moveLine(m, false))
      : h("li", { class: "lane-empty" }, "No stock changes yet."));
  }

  function moveLine(m, withName) {
    const reason = (REASONS[m.reason] || (() => m.reason))(m);
    return h("li", { class: "move" },
      h("span", { class: `delta ${m.delta > 0 ? "up" : "down"}` }, `${m.delta > 0 ? "+" : "−"}${Math.abs(m.delta)}`),
      h("span", { class: "move-what" }, withName ? h("strong", {}, m.product_name) : null, withName ? " · " : null, reason),
      h("span", { class: "move-after" }, `${m.stock_after} left`),
      h("time", { class: "move-when", datetime: m.happened_at }, ago(m.happened_at)));
  }

  async function toggleHistory(i) {
    if (state.openHistory.has(i.id)) {
      state.openHistory.delete(i.id);
      renderStock();
      return;
    }
    state.openHistory.add(i.id);
    renderStock();
    await loadHistory(i.id);
    renderStock();
  }

  async function loadHistory(id) {
    try {
      state.histories[id] = (await ownerApi(`/api/owner/products/${id}/stock-history`)).moves;
    } catch (error) {
      state.histories[id] = [];
      if (error.status !== 401) toast(error.message, true);
    }
  }

  async function stockChange(i, change) {
    try {
      const { product } = await ownerApi(`/api/owner/products/${i.id}/stock`, { method: "POST", body: { change } });
      toast(`${product.name}: ${product.stock} in stock`);
      if (state.openHistory.has(i.id)) await loadHistory(i.id);
      await loadStock();
    } catch (error) {
      toast(error.message, true);
    }
  }

  // ---------------- earnings tab ----------------

  const SOURCE_NAMES = { cart: "Website cart", chat: "Chat assistant", whatsapp: "WhatsApp", instagram: "Instagram",
                         terminal: "Terminal test" };
  const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

  async function loadReport() {
    const view = $("report-view");
    view.classList.add("refreshing");                         // keep the old numbers on screen while loading
    try {
      const { report } = await ownerApi(`/api/owner/report?period=${state.period}`);
      if (report.period !== state.period) return;             // the owner picked another period meanwhile
      state.report = report;
      renderReport();
    } catch (error) {
      if (error.status !== 401) toast(error.message, true);
    } finally {
      view.classList.remove("refreshing");
    }
  }

  function tile(label, value, note, hero = false) {
    return h("div", { class: "tile" + (hero ? " tile-hero" : "") },
      h("p", { class: "tile-label" }, label), h("p", { class: "tile-value" }, value), h("p", { class: "tile-note" }, note));
  }

  function renderReport() {
    const r = state.report;
    const s = r.summary;
    const parts = [
      h("p", { class: "report-note" }, `${r.label}, by the day each order was placed. Customers pay at pickup or delivery, `
        + "so only completed orders count as earned."),
      h("div", { class: "tiles" },
        tile("Earned", money(s.earned), `from ${plural(s.completed_orders, "completed order")}`, true),
        tile("Still to collect", money(s.waiting), `${plural(s.waiting_orders, "order")} not finished yet`),
        tile("All orders", money(s.value), `${plural(s.orders, "order")}, average ${money(s.average)}`),
        tile("Items sold", String(s.items_sold), `${s.pickup} pickup, ${s.delivery} delivery`),
        tile("Customers", String(s.customers), s.repeat_customers ? `${s.repeat_customers} ordered more than once`
          : "No repeat customers yet"),
        tile("Cancelled", String(s.cancelled_orders), s.cancelled_orders ? `${money(s.cancelled_value)} not earned` : "None")),
    ];
    if (!s.orders && !s.cancelled_orders) {
      parts.push(h("p", { class: "lane-empty" }, "No orders in this period yet."));
    } else {
      if (r.bars.length > 1 && s.orders) parts.push(barChart(r));
      parts.push(h("div", { class: "report-grid" }, topItems(r.top_items), customersBox(r.customers)));
      parts.push(sourcesBox(r.sources));
    }
    $("report-view").replaceChildren(...parts);
  }

  /* Clean axis steps: 0, 500, 1,000, 1,500... */
  function niceMax(value) {
    if (value <= 0) return 100;
    const power = 10 ** Math.floor(Math.log10(value));
    for (const step of [1, 2, 2.5, 5, 10]) if (step * power >= value) return step * power;
    return 10 * power;
  }

  function axisMoney(value, compact) {
    if (!compact) return money(value);
    return `₹${(value / 1000).toLocaleString("en-IN", { maximumFractionDigits: 1 })}K`;
  }

  function barChart(r) {
    const totals = r.bars.map((b) => b.earned + b.waiting);
    const top = niceMax(Math.max(...totals));
    const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => Math.round(top * f));
    const compact = top >= 10000;
    const PLOT = 180;
    const best = totals.indexOf(Math.max(...totals));
    const every = r.bars.length <= 8 ? 1 : r.bars.length <= 16 ? 2 : r.bars.length <= 24 ? 3 : 5;
    const short = (b) => (r.grouping === "month" ? b.short : r.bars.length <= 8 ? b.label.split(" ").slice(0, 2).join(" ") : b.short);
    const tip = h("div", { class: "chart-tip", "aria-hidden": "true", hidden: true });

    const columns = r.bars.map((b, i) => {
      const stack = h("div", { class: "stack" });
      for (const [key, value] of [["earned", b.earned], ["waiting", b.waiting]]) {
        if (!value) continue;                                  // a part at zero draws nothing
        const seg = h("div", { class: `seg seg-${key}` });
        seg.style.setProperty("--h", `${Math.max(2, (value / top) * PLOT)}px`);
        stack.append(seg);
      }
      const name = `${b.label}: ${money(b.earned)} earned, ${money(b.waiting)} still to collect, ${plural(b.orders, "order")}`;
      const col = h("div", { class: "col", tabindex: 0, role: "img", "aria-label": name }, stack);
      if (i === best && totals[i] > 0) {
        const label = h("span", { class: "cap-label" }, axisMoney(totals[i], compact));
        label.style.setProperty("--y", `${(totals[i] / top) * PLOT + 6}px`);
        col.append(label);
      }
      const show = () => {
        tip.replaceChildren(
          h("p", { class: "tip-title" }, b.label),
          h("p", {}, h("span", { class: "line-key key-earned" }), h("strong", {}, money(b.earned)), " earned"),
          h("p", {}, h("span", { class: "line-key key-waiting" }), h("strong", {}, money(b.waiting)), " still to collect"),
          h("p", { class: "tip-muted" }, plural(b.orders, "order")));
        const where = ((i + 0.5) / r.bars.length) * 100;
        tip.style.setProperty("--x", `${Math.min(85, Math.max(15, where))}%`);
        tip.hidden = false;
      };
      col.addEventListener("pointerenter", show);
      col.addEventListener("focus", show);
      col.addEventListener("pointerleave", () => { tip.hidden = true; });
      col.addEventListener("blur", () => { tip.hidden = true; });
      return col;
    });

    const plot = h("div", { class: "plot" },
      ticks.map((t) => { const line = h("span", { class: "grid-line" }); line.style.setProperty("--y", `${(t / top) * PLOT}px`); return line; }),
      h("div", { class: "columns" }, columns),
      tip);
    const yAxis = h("div", { class: "y-axis", "aria-hidden": "true" },
      ticks.map((t) => { const label = h("span", {}, axisMoney(t, compact)); label.style.setProperty("--y", `${(t / top) * PLOT}px`); return label; }));
    const xAxis = h("div", { class: "x-axis", "aria-hidden": "true" },
      r.bars.map((b, i) => h("span", {}, i % every === 0 ? short(b) : "")));
    const rows = r.bars.map((b) => h("tr", {}, h("th", { scope: "row" }, b.label), h("td", {}, String(b.orders)),
      h("td", {}, money(b.earned)), h("td", {}, money(b.waiting))));

    return h("section", { class: "chart-card", "aria-labelledby": "chart-title" },
      h("div", { class: "chart-head" },
        h("h3", { id: "chart-title" }, r.grouping === "month" ? "Orders by month" : "Orders by day"),
        h("ul", { class: "legend" },
          h("li", {}, h("span", { class: "swatch key-earned" }), "Earned"),
          h("li", {}, h("span", { class: "swatch key-waiting" }), "Still to collect"))),
      h("div", { class: "chart" }, yAxis, plot, h("span"), xAxis),
      h("details", { class: "table-view" },
        h("summary", {}, "Show these numbers as a table"),
        h("div", { class: "table-wrap" }, h("table", {},
          h("thead", {}, h("tr", {}, h("th", { scope: "col" }, r.grouping === "month" ? "Month" : "Day"),
            h("th", { scope: "col" }, "Orders"), h("th", { scope: "col" }, "Earned"), h("th", { scope: "col" }, "Still to collect"))),
          h("tbody", {}, rows)))));
  }

  function topItems(items) {
    const most = Math.max(1, ...items.map((i) => i.money));
    return h("section", { class: "report-card" },
      h("h3", {}, "Best-selling items"),
      items.length ? h("div", { class: "table-wrap" }, h("table", { class: "rank-table" },
        h("thead", {}, h("tr", {}, h("th", { scope: "col" }, "Item"), h("th", { scope: "col" }, "Sold"),
          h("th", { scope: "col" }, "Money"))),
        h("tbody", {}, items.map((item) => {
          const bar = h("span", { class: "data-bar" });
          bar.style.setProperty("--w", `${Math.max(2, (item.money / most) * 100)}%`);
          return h("tr", {},
            h("th", { scope: "row" }, h("span", { class: "item-name" }, `${item.emoji ? item.emoji + " " : ""}${item.name}`), bar),
            h("td", {}, String(item.quantity)),
            h("td", {}, money(item.money)));
        }))))
        : h("p", { class: "panel-help" }, "Nothing sold in this period."));
  }

  function customersBox(people) {
    return h("section", { class: "report-card" },
      h("h3", {}, "Best customers"),
      people.length ? h("div", { class: "table-wrap" }, h("table", { class: "rank-table" },
        h("thead", {}, h("tr", {}, h("th", { scope: "col" }, "Customer"), h("th", { scope: "col" }, "Orders"),
          h("th", { scope: "col" }, "Spent"))),
        h("tbody", {}, people.map((p) => h("tr", {},
          h("th", { scope: "row" }, h("span", { class: "item-name" }, p.name),
            h("a", { class: "small-link", href: `tel:${p.phone.length === 12 ? "+" : ""}${p.phone}` }, phoneText(p.phone)),
            h("span", { class: "muted" }, ` · last order ${ago(p.last_order)}`)),
          h("td", {}, String(p.orders)),
          h("td", {}, money(p.spent)))))))
        : h("p", { class: "panel-help" }, "No customers in this period."));
  }

  function sourcesBox(sources) {
    const entries = Object.entries(sources).sort((a, b) => b[1] - a[1]);
    if (!entries.length) return h("span");
    return h("p", { class: "report-note" }, "Orders came through: ",
      entries.map(([source, count], i) => [i ? ", " : "", h("strong", {}, SOURCE_NAMES[source] || source), ` ${count}`]).flat());
  }

  function choosePeriod(period) {
    state.period = period;
    for (const button of document.querySelectorAll("[data-period]")) {
      button.setAttribute("aria-pressed", String(button.dataset.period === period));
    }
    $("csv-link").href = `/api/owner/orders.csv?period=${period}`;
    loadReport();
  }

  // ---------------- finding an order ----------------

  function searchInput(event) {
    clearTimeout(state.searchTimer);
    const q = event.target.value.trim();
    state.search = q;
    if (!q) {
      state.searchResults = null;
      renderOrders();
      return;
    }
    state.searchTimer = setTimeout(() => runSearch(q), 300);
  }

  async function runSearch(q) {
    try {
      const { orders } = await ownerApi(`/api/owner/orders/search?q=${encodeURIComponent(q)}`);
      if (state.search !== q) return;                         // the owner kept typing
      state.searchResults = orders;
      renderOrders();
    } catch (error) {
      if (error.status !== 401) toast(error.message, true);
    }
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
    $("desk-emoji").textContent = s.shop_emoji;
    for (const key of ["shop_name", "phone", "tagline", "address", "open_time", "close_time",
                       "delivery_fee", "free_delivery_above", "delivery_area", "assistant_notes", "shop_emoji", "notes_hint"]) {
      if (form.elements[key] !== document.activeElement) form.elements[key].value = s[key];
    }
    form.querySelectorAll('input[name="quick_question"]').forEach((input, i) => {
      if (input !== document.activeElement) input.value = s.quick_questions[i] || "";
    });
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
      shop_emoji: value("shop_emoji"), notes_hint: value("notes_hint"),
      quick_questions: [...form.querySelectorAll('input[name="quick_question"]')].map((input) => input.value.trim()).filter(Boolean),
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

  function setUpShopIcons() {
    $("shop-emoji-row").replaceChildren(...SHOP_EMOJIS.map((emoji) => h("button", { class: "emoji-choice", type: "button",
      "aria-label": `Use ${emoji} as the shop icon`, onclick: () => { $("shop-form").elements.shop_emoji.value = emoji; } }, emoji)));
  }

  // ---------------- wiring ----------------

  $("sign-in-form").addEventListener("submit", signIn);
  $("sign-out").addEventListener("click", signOut);
  $("sound-toggle").addEventListener("click", toggleSound);
  $("shop-form").addEventListener("submit", saveSettings);
  $("order-search").addEventListener("input", searchInput);
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
  for (const button of document.querySelectorAll("[data-period]")) {
    button.addEventListener("click", () => choosePeriod(button.dataset.period));
  }
  document.addEventListener("visibilitychange", () => { if (!document.hidden && !$("desk").hidden) loadOrders(); });

  setUpAddForm();
  setUpShopIcons();
  start();
})();
