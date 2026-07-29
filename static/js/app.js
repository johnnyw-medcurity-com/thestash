(() => {
  "use strict";

  const APP = document.getElementById("app");

  const state = {
    token: localStorage.getItem("token") || null,
    user: JSON.parse(localStorage.getItem("user") || "null"),
    clients: [],
    categories: { covered: [], needs_review: "" },
  };

  // ---------------- API helper ----------------

  async function api(path, { method = "GET", json, form } = {}) {
    const headers = {};
    if (state.token) headers["Authorization"] = "Bearer " + state.token;
    const opts = { method, headers };
    if (json !== undefined) {
      headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(json);
    } else if (form !== undefined) {
      opts.body = form; // FormData, browser sets content-type
    }
    const res = await fetch(path, opts);
    if (res.status === 401) {
      logout();
      throw new Error("Session expired. Please log in again.");
    }
    const contentType = res.headers.get("content-type") || "";
    if (!res.ok) {
      let message = "Request failed";
      if (contentType.includes("application/json")) {
        const data = await res.json().catch(() => ({}));
        message = data.error || message;
      }
      throw new Error(message);
    }
    if (contentType.includes("application/json")) return res.json();
    return res;
  }

  function logout() {
    state.token = null;
    state.user = null;
    localStorage.removeItem("token");
    localStorage.removeItem("user");
    navigate("#/login");
  }

  function saveSession(token, user) {
    state.token = token;
    state.user = user;
    localStorage.setItem("token", token);
    localStorage.setItem("user", JSON.stringify(user));
  }

  // ---------------- Router ----------------

  function navigate(hash) {
    if (location.hash === hash) render();
    else location.hash = hash;
  }

  window.addEventListener("hashchange", render);
  window.addEventListener("DOMContentLoaded", render);

  function currentRoute() {
    const hash = location.hash || "#/dashboard";
    const parts = hash.replace(/^#\//, "").split("/");
    return parts;
  }

  async function render() {
    if (!state.token) {
      const parts = currentRoute();
      if (parts[0] === "register") return renderAuth("register");
      return renderAuth("login");
    }

    const parts = currentRoute();
    try {
      if (parts[0] === "trips" && parts[1] === "new") {
        await renderNewTrip();
      } else if (parts[0] === "trips" && parts[1]) {
        await renderTripDetail(parseInt(parts[1], 10));
      } else {
        await renderDashboard();
      }
    } catch (err) {
      renderFatalError(err);
    }
  }

  function renderFatalError(err) {
    APP.innerHTML = `
      <div class="topbar"><div class="brand">Travel Expenses</div></div>
      <div class="screen">
        <div class="error-msg">${escapeHtml(err.message || "Something went wrong")}</div>
        <button class="btn btn-outline" style="margin-top:12px" onclick="location.hash='#/dashboard'; location.reload()">Back to dashboard</button>
      </div>`;
  }

  // ---------------- Helpers ----------------

  function escapeHtml(str) {
    return String(str ?? "").replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  }

  function fmtMoney(n) {
    return "$" + (Number(n) || 0).toFixed(2);
  }

  function fmtDate(d) {
    if (!d) return "";
    const [y, m, day] = d.split("-");
    const dt = new Date(Number(y), Number(m) - 1, Number(day));
    return dt.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
  }

  function todayISO() {
    return new Date().toISOString().slice(0, 10);
  }

  async function ensureLookups() {
    if (state.clients.length === 0) {
      state.clients = await api("/api/clients");
    }
    if (state.categories.covered.length === 0) {
      state.categories = await api("/api/categories");
    }
  }

  function topbar({ title, back, right }) {
    return `
      <div class="topbar">
        <div class="brand">
          ${back ? `<button class="back-btn" data-nav="${back}" aria-label="Back">&#8592;</button>` : ""}
          <span>${escapeHtml(title)}</span>
        </div>
        ${right || ""}
      </div>`;
  }

  function bindNavButtons(root) {
    root.querySelectorAll("[data-nav]").forEach((el) => {
      el.addEventListener("click", () => navigate(el.getAttribute("data-nav")));
    });
  }

  // ---------------- Auth views ----------------

  function renderAuth(mode) {
    const isLogin = mode === "login";
    APP.innerHTML = `
      <div class="center-screen">
        <div style="width:100%; max-width:380px;">
          <div style="text-align:center; margin-bottom:22px;">
            <div style="font-size:28px;">🧳</div>
            <h1>Travel Expenses</h1>
            <p class="muted">Log trip costs, tie them to a client, and report them fast.</p>
          </div>
          <div class="card">
            <h2>${isLogin ? "Log in" : "Create your account"}</h2>
            <div id="auth-error"></div>
            <form id="auth-form">
              ${isLogin ? "" : `
              <label>Full name
                <input type="text" name="name" autocomplete="name" required>
              </label>`}
              <label>Email
                <input type="email" name="email" autocomplete="email" required>
              </label>
              <label>Password
                <input type="password" name="password" autocomplete="${isLogin ? "current-password" : "new-password"}" minlength="6" required>
              </label>
              <button class="btn btn-primary" type="submit">${isLogin ? "Log in" : "Sign up"}</button>
            </form>
            <div class="divider"></div>
            <button class="link-toggle" data-nav="${isLogin ? "#/register" : "#/login"}">
              ${isLogin ? `Need an account? <b>Sign up</b>` : `Already have an account? <b>Log in</b>`}
            </button>
          </div>
        </div>
      </div>`;

    bindNavButtons(APP);

    APP.querySelector("#auth-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      const payload = Object.fromEntries(fd.entries());
      const errorBox = APP.querySelector("#auth-error");
      errorBox.innerHTML = "";
      try {
        const data = await api(isLogin ? "/api/login" : "/api/register", { method: "POST", json: payload });
        saveSession(data.token, data.user);
        navigate("#/dashboard");
      } catch (err) {
        errorBox.innerHTML = `<div class="error-msg">${escapeHtml(err.message)}</div>`;
      }
    });
  }

  // ---------------- Dashboard ----------------

  async function renderDashboard() {
    APP.innerHTML = `
      ${topbar({
        title: "My Trips",
        right: `<button class="link-btn" data-action="logout">Log out</button>`,
      })}
      <div class="screen" id="dash-content">
        <div class="spinner"></div>
      </div>
      <div class="fab">
        <button class="btn btn-primary" data-nav="#/trips/new">+ New Trip</button>
      </div>`;

    bindNavButtons(APP);
    APP.querySelector('[data-action="logout"]').addEventListener("click", logout);

    const trips = await api("/api/trips");
    const content = APP.querySelector("#dash-content");

    if (trips.length === 0) {
      content.innerHTML = `
        <div class="card empty-state">
          <p><strong>No trips yet.</strong></p>
          <p class="muted">Start a trip to log flights, lodging, meals, and other costs tied to a client.</p>
        </div>`;
      return;
    }

    content.innerHTML = trips.map((t) => `
      <button class="trip-card" data-nav="#/trips/${t.id}">
        <div class="row1">
          <span class="client-name">${escapeHtml(t.client_name)}</span>
          <span class="amount">${fmtMoney(t.total)}</span>
        </div>
        <div class="dates">${escapeHtml(t.purpose || "Business trip")} &middot; ${fmtDate(t.start_date)} – ${fmtDate(t.end_date)}</div>
        <span class="status-badge status-${t.status}">${escapeHtml(t.status)}</span>
      </button>
    `).join("");
    bindNavButtons(content);
  }

  // ---------------- New Trip ----------------

  async function renderNewTrip() {
    await ensureLookups();

    APP.innerHTML = `
      ${topbar({ title: "New Trip", back: "#/dashboard" })}
      <div class="screen">
        <div class="card">
          <div id="trip-error"></div>
          <form id="new-trip-form">
            <label>Client
              <input list="client-list" name="client_name" placeholder="Type or select a client" required>
              <datalist id="client-list">
                ${state.clients.map((c) => `<option value="${escapeHtml(c.name)}">`).join("")}
              </datalist>
            </label>
            <label>Trip purpose
              <input type="text" name="purpose" placeholder="e.g. HIPAA risk assessment on-site visit">
            </label>
            <div class="inline-row">
              <label>Start date
                <input type="date" name="start_date" value="${todayISO()}" required>
              </label>
              <label>End date
                <input type="date" name="end_date" value="${todayISO()}" required>
              </label>
            </div>
            <button class="btn btn-primary" type="submit">Create Trip</button>
          </form>
        </div>
      </div>`;

    bindNavButtons(APP);

    APP.querySelector("#new-trip-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      const payload = Object.fromEntries(fd.entries());
      const errorBox = APP.querySelector("#trip-error");
      errorBox.innerHTML = "";
      try {
        const client = await api("/api/clients", { method: "POST", json: { name: payload.client_name.trim() } });
        state.clients = [];
        const trip = await api("/api/trips", {
          method: "POST",
          json: {
            client_id: client.id,
            purpose: payload.purpose,
            start_date: payload.start_date,
            end_date: payload.end_date,
          },
        });
        navigate("#/trips/" + trip.id);
      } catch (err) {
        errorBox.innerHTML = `<div class="error-msg">${escapeHtml(err.message)}</div>`;
      }
    });
  }

  // ---------------- Trip Detail ----------------

  async function renderTripDetail(tripId) {
    await ensureLookups();
    APP.innerHTML = `
      ${topbar({ title: "Trip Details", back: "#/dashboard" })}
      <div class="screen" id="trip-content"><div class="spinner"></div></div>`;
    bindNavButtons(APP);

    const trip = await api(`/api/trips/${tripId}`);
    const content = APP.querySelector("#trip-content");
    content.innerHTML = tripDetailHtml(trip);
    bindTripDetailEvents(content, trip);
  }

  function tripDetailHtml(trip) {
    const expenses = trip.expenses || [];
    return `
      <div class="card">
        <div class="row1">
          <span class="client-name">${escapeHtml(trip.client_name)}</span>
          <span class="status-badge status-${trip.status}">${escapeHtml(trip.status)}</span>
        </div>
        <p class="muted" style="margin:4px 0 0">${escapeHtml(trip.purpose || "Business trip")}</p>
        <p class="muted" style="margin:2px 0 0">${fmtDate(trip.start_date)} – ${fmtDate(trip.end_date)}</p>
        <div class="divider"></div>
        <div class="total-bar"><span>Total</span><span>${fmtMoney(trip.total)}</span></div>
      </div>

      <details class="card" style="padding-bottom:6px;">
        <summary style="cursor:pointer; font-weight:600; font-size:14px;">What's covered?</summary>
        <div class="rules-table">
          <div class="rules-col covered">
            <h4>✓ Covered</h4>
            <ul>
              <li>Flights, lodging, rental car / mileage</li>
              <li>Reasonable meals directly related to travel</li>
              <li>Parking, tolls, airport transportation</li>
              <li>Other direct, necessary trip costs</li>
            </ul>
          </div>
          <div class="rules-col not-covered">
            <h4>✗ Not covered</h4>
            <ul>
              <li>Alcohol &mdash; never covered</li>
              <li>Personal shopping, sightseeing, entertainment</li>
              <li>Costs from mixing in personal travel</li>
              <li>Anything you're not sure you can justify</li>
            </ul>
          </div>
        </div>
        <p class="muted" style="margin-top:8px;">Not sure an item qualifies? Log it anyway and flag it for review below &mdash; don't guess.</p>
      </details>

      <div class="card">
        <div class="row1" style="margin-bottom:8px;">
          <h3 style="margin:0;">Expenses (${expenses.length})</h3>
          <button class="btn btn-primary btn-sm" data-action="add-expense">+ Add</button>
        </div>
        ${expenses.length === 0
          ? `<p class="muted">No expenses logged yet. Add one and photograph the receipt right away.</p>`
          : `<div id="expense-list">${expenses.map(expenseRowHtml).join("")}</div>`}
      </div>

      <div class="card">
        <h3>Report</h3>
        <p class="muted">Generate a PDF report for this trip, then send it to whoever needs to review or reimburse it.</p>
        <div class="inline-row">
          <button class="btn btn-outline" data-action="download-report">Download PDF</button>
          <button class="btn btn-secondary" data-action="send-report">Send Report</button>
        </div>
      </div>

      <div class="card" style="border-color:#fecaca;">
        <button class="btn btn-danger" data-action="delete-trip">Delete Trip</button>
      </div>
    `;
  }

  function expenseRowHtml(exp) {
    return `
      <div class="expense-row" data-expense-id="${exp.id}">
        ${exp.receipt_filename
          ? `<img class="receipt-thumb" src="/uploads/${encodeURIComponent(exp.receipt_filename)}?token=${encodeURIComponent(state.token)}" alt="Receipt">`
          : `<div class="receipt-thumb" style="display:flex;align-items:center;justify-content:center;color:#94a3b8;font-size:10px;">no<br>receipt</div>`}
        <div class="expense-main" style="flex:1;">
          <div class="cat">${escapeHtml(exp.category)}${exp.flagged ? `<span class="flag-badge">FLAGGED</span>` : ""}</div>
          <div class="vendor">${escapeHtml(exp.vendor || "")}</div>
          <div class="date">${fmtDate(exp.date)}${exp.notes ? " · " + escapeHtml(exp.notes) : ""}</div>
          <div class="expense-actions">
            <button data-action="edit-expense" data-id="${exp.id}">Edit</button>
            <button class="danger" data-action="delete-expense" data-id="${exp.id}">Delete</button>
          </div>
        </div>
        <div class="expense-amount">${fmtMoney(exp.amount)}</div>
      </div>`;
  }

  function categoryOptions(selected) {
    const opts = [...state.categories.covered, state.categories.needs_review];
    return opts.map((c) => `<option value="${escapeHtml(c)}" ${c === selected ? "selected" : ""}>${escapeHtml(c)}</option>`).join("");
  }

  function bindTripDetailEvents(root, trip) {
    root.querySelector('[data-action="add-expense"]').addEventListener("click", () => openExpenseModal(trip.id));
    root.querySelector('[data-action="download-report"]').addEventListener("click", () => downloadReport(trip));
    root.querySelector('[data-action="send-report"]').addEventListener("click", () => openSendReportModal(trip));
    root.querySelector('[data-action="delete-trip"]').addEventListener("click", () => deleteTrip(trip.id));

    root.querySelectorAll('[data-action="edit-expense"]').forEach((btn) => {
      btn.addEventListener("click", () => {
        const exp = (trip.expenses || []).find((e) => e.id === parseInt(btn.dataset.id, 10));
        openExpenseModal(trip.id, exp);
      });
    });
    root.querySelectorAll('[data-action="delete-expense"]').forEach((btn) => {
      btn.addEventListener("click", () => deleteExpense(btn.dataset.id, trip.id));
    });
  }

  async function deleteTrip(tripId) {
    if (!confirm("Delete this trip and all its expenses? This can't be undone.")) return;
    await api(`/api/trips/${tripId}`, { method: "DELETE" });
    navigate("#/dashboard");
  }

  async function deleteExpense(expenseId, tripId) {
    if (!confirm("Delete this expense?")) return;
    await api(`/api/expenses/${expenseId}`, { method: "DELETE" });
    renderTripDetail(tripId);
  }

  // ---------------- Expense modal ----------------

  function openModal(innerHtml) {
    const backdrop = document.createElement("div");
    backdrop.className = "modal-backdrop";
    backdrop.innerHTML = `<div class="modal">${innerHtml}</div>`;
    backdrop.addEventListener("click", (e) => {
      if (e.target === backdrop) backdrop.remove();
    });
    document.body.appendChild(backdrop);
    return backdrop;
  }

  function openExpenseModal(tripId, existing) {
    const isEdit = !!existing;
    const modal = openModal(`
      <div class="modal-header">
        <h2 style="margin:0;">${isEdit ? "Edit Expense" : "Add Expense"}</h2>
        <button class="modal-close" data-close>&times;</button>
      </div>
      <div id="expense-error"></div>
      <form id="expense-form">
        <label>Date
          <input type="date" name="date" value="${existing ? existing.date : todayISO()}" required>
        </label>
        <label>Category
          <select name="category" required>
            ${categoryOptions(existing ? existing.category : "")}
          </select>
        </label>
        <label>Vendor
          <input type="text" name="vendor" placeholder="e.g. Delta, Marriott, Uber" value="${existing ? escapeHtml(existing.vendor || "") : ""}">
        </label>
        <label>Amount (USD)
          <input type="number" name="amount" step="0.01" min="0.01" value="${existing ? existing.amount : ""}" required>
        </label>
        <label>Notes
          <textarea name="notes" placeholder="Any detail that helps whoever reviews this">${existing ? escapeHtml(existing.notes || "") : ""}</textarea>
        </label>
        <label class="checkbox-row">
          <input type="checkbox" name="flagged" ${existing && existing.flagged ? "checked" : ""}>
          <span>Flag for review &mdash; not sure this qualifies</span>
        </label>
        <label>Receipt photo
          <input type="file" name="receipt" accept="image/*,application/pdf" capture="environment">
        </label>
        ${existing && existing.receipt_filename ? `<p class="muted">A receipt is already attached. Choosing a new file replaces it.</p>` : ""}
        <button class="btn btn-primary" type="submit">${isEdit ? "Save Changes" : "Add Expense"}</button>
      </form>
    `);

    modal.querySelector("[data-close]").addEventListener("click", () => modal.remove());

    const form = modal.querySelector("#expense-form");
    const categorySelect = form.querySelector('select[name="category"]');
    categorySelect.addEventListener("change", () => {
      const flaggedBox = form.querySelector('input[name="flagged"]');
      if (categorySelect.value === state.categories.needs_review) {
        flaggedBox.checked = true;
      }
    });

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const errorBox = modal.querySelector("#expense-error");
      errorBox.innerHTML = "";
      const fd = new FormData(form);
      if (!form.querySelector('input[name="flagged"]').checked) fd.delete("flagged");
      else fd.set("flagged", "1");
      const fileInput = form.querySelector('input[name="receipt"]');
      if (!fileInput.files.length) fd.delete("receipt");

      try {
        if (isEdit) {
          await api(`/api/expenses/${existing.id}`, { method: "PATCH", form: fd });
        } else {
          await api(`/api/trips/${tripId}/expenses`, { method: "POST", form: fd });
        }
        modal.remove();
        renderTripDetail(tripId);
      } catch (err) {
        errorBox.innerHTML = `<div class="error-msg">${escapeHtml(err.message)}</div>`;
      }
    });
  }

  // ---------------- Report ----------------

  async function downloadReport(trip) {
    const res = await api(`/api/trips/${trip.id}/report`);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const filename = `expense-report-${(trip.client_name || "trip").replace(/[^a-z0-9]+/gi, "-")}-${trip.start_date}.pdf`;
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
    return filename;
  }

  function openSendReportModal(trip) {
    const modal = openModal(`
      <div class="modal-header">
        <h2 style="margin:0;">Send Report</h2>
        <button class="modal-close" data-close>&times;</button>
      </div>
      <p class="muted">This downloads the PDF, then opens an email draft in your mail app. Attach the downloaded file before you hit send.</p>
      <div id="report-error"></div>
      <form id="report-form">
        <label>Recipient name
          <input type="text" name="recipient_name" placeholder="e.g. Finance / your manager">
        </label>
        <label>Recipient email
          <input type="email" name="recipient_email" required>
        </label>
        <label>Message
          <textarea name="message">Hi,

Attached is my expense report for the ${escapeHtml(trip.client_name)} trip (${fmtDate(trip.start_date)} – ${fmtDate(trip.end_date)}), total ${fmtMoney(trip.total)}.

Thanks!</textarea>
        </label>
        <button class="btn btn-primary" type="submit">Download PDF &amp; Open Email</button>
      </form>
    `);

    modal.querySelector("[data-close]").addEventListener("click", () => modal.remove());

    modal.querySelector("#report-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const errorBox = modal.querySelector("#report-error");
      errorBox.innerHTML = "";
      const fd = new FormData(e.target);
      const payload = Object.fromEntries(fd.entries());

      try {
        const filename = await downloadReport(trip);
        await api(`/api/trips/${trip.id}/report/log`, {
          method: "POST",
          json: { recipient_email: payload.recipient_email, recipient_name: payload.recipient_name },
        });
        const subject = `Expense Report: ${trip.client_name} (${trip.start_date} to ${trip.end_date})`;
        const body = payload.message + `\n\n(Remember to attach ${filename} — it just downloaded to your device.)`;
        const mailto = `mailto:${encodeURIComponent(payload.recipient_email)}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
        modal.remove();
        window.location.href = mailto;
        renderTripDetail(trip.id);
      } catch (err) {
        errorBox.innerHTML = `<div class="error-msg">${escapeHtml(err.message)}</div>`;
      }
    });
  }

  render();
})();
