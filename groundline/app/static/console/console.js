const state = {
  status: null,
  providers: null,
};

const titles = {
  dashboard: "Dashboard",
  documents: "Documents",
  search: "Search",
  runs: "Runs",
  compare: "Compare",
  providers: "Providers",
};

const $ = (selector) => document.querySelector(selector);

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`${response.status} ${response.statusText}: ${text}`);
  }
  return response.json();
}

function setNotice(message, tone = "warning") {
  const notice = $("#notice");
  notice.textContent = message;
  notice.hidden = !message;
  notice.dataset.tone = tone;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function pill(value) {
  const normalized = String(value ?? "unknown")
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "-");
  return `<span class="pill ${escapeHtml(normalized)}">${escapeHtml(value ?? "unknown")}</span>`;
}

function table(columns, rows, emptyText = "No data") {
  if (!rows || rows.length === 0) {
    return `<div class="empty">${escapeHtml(emptyText)}</div>`;
  }
  const head = columns.map((column) => `<th>${escapeHtml(column.label)}</th>`).join("");
  const body = rows
    .map((row) => {
      const cells = columns
        .map((column) => `<td>${column.render ? column.render(row) : escapeHtml(row[column.key])}</td>`)
        .join("");
      return `<tr>${cells}</tr>`;
    })
    .join("");
  return `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

function short(value, length = 12) {
  if (!value) return "";
  return String(value).slice(0, length);
}

function collectionName() {
  return state.status?.recipe?.collection || $("#search-collection").value || "demo";
}

async function loadHealth() {
  try {
    await api("/health");
    $("#api-dot").className = "status-dot ok";
    $("#api-status").textContent = "API online";
  } catch (error) {
    $("#api-dot").className = "status-dot bad";
    $("#api-status").textContent = "API offline";
    setNotice(error.message);
  }
}

async function loadDashboard() {
  setNotice("");
  const [status, providers] = await Promise.all([
    api("/app/status"),
    api("/app/providers"),
  ]);
  state.status = status;
  state.providers = providers;
  const collection = status.recipe?.collection || "-";
  $("#runtime-collection").textContent = collection;
  $("#runtime-profile").textContent = "default";
  $("#search-collection").value = collection;
  $("#kpi-app").textContent = status.latest_artifact ? "Initialized" : "No artifact";
  $("#kpi-providers").textContent = providers.ok ? "Ready" : "Needs review";
  $("#kpi-artifact").textContent = status.latest_artifact ? "Available" : "None";
  $("#kpi-run").textContent = status.latest_run?.operation || "None";
  $("#dashboard-providers").innerHTML = renderProviders(providers);
  $("#dashboard-status").innerHTML = renderStatus(status);
}

function renderStatus(status) {
  const fields = [
    ["App", status.recipe?.name],
    ["Collection", status.recipe?.collection],
    ["Docs path", status.recipe?.docs_path],
    ["Evalset", status.recipe?.evalset],
    ["Latest artifact", status.latest_artifact?.path || "None"],
    ["Recent runs", status.runs?.length || 0],
  ];
  return fields
    .map(([key, value]) => `<dt>${escapeHtml(key)}</dt><dd>${escapeHtml(value)}</dd>`)
    .join("");
}

function renderProviders(report) {
  return table(
    [
      { key: "name", label: "Name" },
      { key: "provider", label: "Provider" },
      { key: "status", label: "Status", render: (row) => pill(row.status) },
      { key: "model", label: "Model", render: (row) => escapeHtml(row.model || "-") },
      { key: "dimension", label: "Dim", render: (row) => escapeHtml(row.dimension || "-") },
      {
        key: "checks",
        label: "Checks",
        render: (row) => escapeHtml((row.checks || []).map((check) => check.code).join(", ")),
      },
    ],
    report.providers || [],
  );
}

async function loadDocuments() {
  const docs = await api("/app/docs", { method: "POST", body: JSON.stringify({}) });
  $("#documents-table").innerHTML = table(
    [
      { key: "status", label: "Status", render: (row) => pill(row.status) },
      { key: "source_uri", label: "Source" },
      { key: "source_type", label: "Type" },
      { key: "bytes", label: "Bytes" },
      { key: "content_hash", label: "Source Hash", render: (row) => `<code>${short(row.content_hash)}</code>` },
      { key: "indexed_hash", label: "Indexed Hash", render: (row) => `<code>${short(row.indexed_hash)}</code>` },
      { key: "reason", label: "Reason" },
    ],
    docs.items || [],
  );
}

async function runSearch() {
  const query = $("#search-query").value.trim();
  const collection = $("#search-collection").value.trim() || collectionName();
  const topK = Number($("#search-top-k").value || 6);
  const includeTrace = $("#search-trace").checked;
  if (!query) {
    setNotice("Query is required.");
    return;
  }
  const result = await api(`/collections/${encodeURIComponent(collection)}/query`, {
    method: "POST",
    body: JSON.stringify({
      query,
      top_k: topK,
      context_window: 1,
      include_trace: includeTrace,
    }),
  });
  $("#search-summary").textContent = `${result.contexts.length} contexts`;
  $("#search-results").innerHTML = renderContexts(result.contexts || []);
}

function renderContexts(contexts) {
  if (!contexts.length) return '<div class="empty">No contexts returned.</div>';
  return contexts
    .map((context, index) => {
      const source = context.source_uri || context.metadata?.source_uri || context.doc_id || "-";
      const score = context.score == null ? "-" : Number(context.score).toFixed(4);
      return `
        <article class="context-item">
          <div class="context-meta">
            ${pill(`#${index + 1}`)}
            ${pill(`score ${score}`)}
            ${pill(source)}
          </div>
          <div class="context-text">${escapeHtml(context.text || "")}</div>
        </article>
      `;
    })
    .join("");
}

async function validateApp() {
  const report = await api("/app/validate", { method: "POST", body: JSON.stringify({}) });
  $("#run-output").innerHTML = renderValidation(report);
}

async function runApp() {
  const report = await api("/app/run", { method: "POST", body: JSON.stringify({}) });
  $("#run-output").innerHTML = renderRun(report);
  await loadDashboard();
}

function renderValidation(report) {
  return table(
    [
      { key: "severity", label: "Severity", render: (row) => pill(row.severity) },
      { key: "code", label: "Code" },
      { key: "message", label: "Message" },
      { key: "path", label: "Path", render: (row) => escapeHtml(row.path || "") },
    ],
    report.issues || [],
    "No validation issues.",
  );
}

function renderRun(report) {
  const steps = report.run?.steps || [];
  return table(
    [
      { key: "name", label: "Step" },
      { key: "ok", label: "OK", render: (row) => pill(row.ok ? "ok" : "bad") },
      { key: "status", label: "Status", render: (row) => escapeHtml(row.status || "") },
      { key: "events", label: "Events" },
      { key: "run_id", label: "Run ID", render: (row) => `<code>${escapeHtml(row.run_id || "")}</code>` },
    ],
    steps,
  );
}

async function runCompare() {
  const base = $("#compare-base").value.trim();
  const target = $("#compare-target").value.trim();
  if (!base || !target) {
    setNotice("Both artifact paths are required.");
    return;
  }
  const report = await api("/app/compare", {
    method: "POST",
    body: JSON.stringify({ base_path: base, target_path: target }),
  });
  $("#compare-output").innerHTML = renderCompare(report);
}

function renderCompare(report) {
  const summary = table(
    [
      { key: "area", label: "Area" },
      { key: "changed", label: "Changed", render: (row) => pill(row.changed ? "changed" : "unchanged") },
    ],
    [
      { area: "Recipe", changed: report.recipe_changed },
      { area: "Sources", changed: report.sources_changed },
      { area: "Providers", changed: report.providers_changed },
      { area: "Steps", changed: report.steps_changed },
      { area: "Metrics", changed: report.metrics_changed },
    ],
  );
  const changes = table(
    [
      { key: "field", label: "Field" },
      { key: "before", label: "Before", render: (row) => `<code>${escapeHtml(JSON.stringify(row.before))}</code>` },
      { key: "after", label: "After", render: (row) => `<code>${escapeHtml(JSON.stringify(row.after))}</code>` },
    ],
    report.changes || [],
    "No manifest changes.",
  );
  const sources = table(
    [
      { key: "status", label: "Status", render: (row) => pill(row.status) },
      { key: "path", label: "Path" },
      { key: "before_hash", label: "Before", render: (row) => `<code>${short(row.before_hash)}</code>` },
      { key: "after_hash", label: "After", render: (row) => `<code>${short(row.after_hash)}</code>` },
    ],
    (report.sources || []).filter((source) => source.status !== "unchanged"),
    "No source changes.",
  );
  return `${summary}${changes}${sources}`;
}

async function loadProviders() {
  const providers = await api("/app/providers");
  $("#providers-table").innerHTML = renderProviders(providers);
}

function switchView(view) {
  document.querySelectorAll(".nav-item").forEach((item) => {
    item.classList.toggle("active", item.dataset.view === view);
  });
  document.querySelectorAll(".view").forEach((section) => {
    section.classList.toggle("active", section.id === `view-${view}`);
  });
  $("#page-title").textContent = titles[view] || "Console";
}

async function guarded(action) {
  try {
    setNotice("");
    await action();
  } catch (error) {
    setNotice(error.message);
  }
}

document.addEventListener("click", (event) => {
  const nav = event.target.closest("[data-view]");
  if (nav) {
    switchView(nav.dataset.view);
    if (nav.dataset.view === "documents") guarded(loadDocuments);
    if (nav.dataset.view === "providers") guarded(loadProviders);
    return;
  }
  const action = event.target.closest("[data-action]")?.dataset.action;
  if (action === "refresh-dashboard") guarded(loadDashboard);
  if (action === "load-docs") guarded(loadDocuments);
  if (action === "run-search") guarded(runSearch);
  if (action === "validate-app") guarded(validateApp);
  if (action === "run-app") guarded(runApp);
  if (action === "run-compare") guarded(runCompare);
  if (action === "load-providers") guarded(loadProviders);
});

guarded(loadHealth);
guarded(loadDashboard);
