const views = ["home", "review", "history", "items"];
let draft = null;
let scannedFile = null;
let saveImage = false;
let retryScan = false;

const $ = (selector) => document.querySelector(selector);
const money = (amount) => new Intl.NumberFormat(undefined, { style: "currency", currency: "USD" }).format(Number(amount || 0));
const dateLabel = (value) => new Date(`${value}T00:00:00`).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });

function showView(name) {
  views.forEach((view) => $(`#${view}-view`).classList.toggle("hidden", view !== name));
  document.querySelectorAll(".nav-link").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === name || (name === "review" && button.dataset.view === "home"));
  });
  $("#app-message").classList.add("hidden");
  if (name === "history") loadHistory();
  if (name === "items") loadItems();
}

function showMessage(message, type = "", retry = false) {
  const box = $("#app-message");
  box.className = `notice ${type}`;
  box.replaceChildren(document.createTextNode(message));
  if (retry) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = "Try again";
    button.addEventListener("click", runScan);
    box.append(button);
  }
}

async function request(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.detail || "Something went wrong. Please try again.");
    error.status = response.status;
    throw error;
  }
  return data;
}

function receiptCard(receipt) {
  const card = document.createElement("article");
  card.className = "receipt-card";
  const summary = document.createElement("div");
  const store = document.createElement("p");
  store.className = "receipt-store";
  store.textContent = receipt.store_name;
  const meta = document.createElement("p");
  meta.className = "receipt-meta";
  meta.textContent = `${dateLabel(receipt.purchase_date)} · ${receipt.items.length} ${receipt.items.length === 1 ? "item" : "items"}`;
  const total = document.createElement("span");
  total.className = "receipt-total";
  total.textContent = money(receipt.total_amount);
  summary.append(store, meta);
  card.append(summary, total);
  return card;
}

function renderReceipts(receipts, target) {
  target.replaceChildren();
  if (!receipts.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "No receipts yet. Scan your first grocery receipt to get started.";
    target.append(empty);
    return;
  }
  receipts.forEach((receipt) => target.append(receiptCard(receipt)));
}

async function loadHistory() {
  try {
    renderReceipts(await request("/api/receipts"), $("#history-receipts"));
  } catch (error) {
    showMessage(error.message, "error");
  }
}

async function loadRecent() {
  try {
    const receipts = await request("/api/receipts");
    renderReceipts(receipts.slice(0, 3), $("#recent-receipts"));
  } catch (error) {
    $("#recent-receipts").innerHTML = '<div class="empty-state">Your receipts will appear here.</div>';
  }
}

function fillReview(data) {
  draft = data;
  $("#store-name").value = data.store_name;
  $("#purchase-date").value = data.purchase_date;
  $("#receipt-total").value = Number(data.total_amount).toFixed(2);
  $("#date-warning").classList.toggle("hidden", !data.date_needs_confirmation);
  $("#date-warning").textContent = data.date_needs_confirmation
    ? "We couldn’t read the purchase date, so we used today. Please confirm or change it."
    : "";
  renderEditableItems();
  showView("review");
}

function renderEditableItems() {
  const container = $("#editable-items");
  container.replaceChildren();
  $("#item-count").textContent = `(${draft.items.length})`;
  draft.items.forEach((item, index) => {
    const row = document.createElement("div");
    row.className = "item-row";
    [
      ["name", item.name, "text"],
      ["quantity", item.quantity, "number"],
      ["unit_price", item.unit_price, "number"],
      ["total_price", item.total_price, "number"],
    ].forEach(([key, value, type]) => {
      const input = document.createElement("input");
      input.type = type;
      input.name = key;
      input.value = value;
      input.required = true;
      if (key !== "name") {
        input.min = key === "quantity" ? "0.001" : "0";
        input.step = key === "quantity" ? "0.001" : "0.01";
      }
      input.setAttribute("aria-label", key.replace("_", " "));
      row.append(input);
    });
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "delete-item";
    remove.setAttribute("aria-label", "Delete item");
    remove.textContent = "×";
    remove.addEventListener("click", () => {
      draft.items.splice(index, 1);
      renderEditableItems();
    });
    row.append(remove);
    container.append(row);
  });
}

async function runScan() {
  if (!scannedFile) return;
  const input = $("#receipt-file");
  showMessage("Reading your receipt…");
  input.disabled = true;
  try {
    const form = new FormData();
    form.append("file", scannedFile);
    const data = await request("/api/scan", { method: "POST", body: form });
    retryScan = false;
    fillReview(data);
  } catch (error) {
    retryScan = error.status === 429 || error.status >= 500;
    showMessage(error.message, "error", retryScan);
  } finally {
    input.disabled = false;
  }
}

async function loadItems() {
  const monthInput = $("#spending-month");
  if (!monthInput.value) monthInput.value = new Date().toISOString().slice(0, 7);
  try {
    const month = monthInput.value;
    const [items, spending] = await Promise.all([
      request(`/api/items?q=${encodeURIComponent($("#item-search").value)}`),
      request(`/api/spending?month=${encodeURIComponent(month)}`),
    ]);
    $("#monthly-total").textContent = money(spending.total);
    const list = $("#all-items");
    list.replaceChildren();
    if (!items.length) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.textContent = "No matching items yet.";
      list.append(empty);
      return;
    }
    items.forEach((item) => {
      const row = document.createElement("article");
      row.className = "purchased-item";
      const name = document.createElement("strong");
      name.textContent = item.name;
      const meta = document.createElement("span");
      meta.textContent = `${item.quantity} · ${item.store_name} · ${dateLabel(item.purchase_date)}`;
      const cost = document.createElement("span");
      cost.className = "item-cost";
      cost.textContent = money(item.total_price);
      row.append(name, meta, cost);
      list.append(row);
    });
  } catch (error) {
    showMessage(error.message, "error");
  }
}

document.querySelectorAll("[data-view]").forEach((button) => {
  button.addEventListener("click", () => showView(button.dataset.view));
});

$("#receipt-file").addEventListener("change", async (event) => {
  scannedFile = event.target.files[0] || null;
  saveImage = $("#save-image-setting").checked;
  if (scannedFile) await runScan();
});

$("#add-item").addEventListener("click", () => {
  draft.items.push({ name: "", quantity: 1, unit_price: 0, total_price: 0 });
  renderEditableItems();
  $("#editable-items .item-row:last-child input").focus();
});

$("#review-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const items = [...$("#editable-items").querySelectorAll(".item-row")].map((row) => {
    const values = [...row.querySelectorAll("input")];
    return {
      name: values[0].value.trim(),
      quantity: Number(values[1].value),
      unit_price: Number(values[2].value),
      total_price: Number(values[3].value),
    };
  });
  const payload = {
    store_name: $("#store-name").value.trim(),
    purchase_date: $("#purchase-date").value,
    total_amount: Number($("#receipt-total").value),
    items,
  };
  if (saveImage && scannedFile) {
    const bytes = new Uint8Array(await scannedFile.arrayBuffer());
    let binary = "";
    bytes.forEach((byte) => { binary += String.fromCharCode(byte); });
    payload.image_data = btoa(binary);
  }
  try {
    await request("/api/receipts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    showView("home");
    showMessage("Receipt saved. Nice work keeping track.", "");
    await loadRecent();
    scannedFile = null;
    $("#receipt-file").value = "";
  } catch (error) {
    showMessage(error.message, "error");
  }
});

$("#item-search").addEventListener("input", loadItems);
$("#spending-month").addEventListener("change", loadItems);
loadRecent();
