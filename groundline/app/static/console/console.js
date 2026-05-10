const state = {
  status: null,
  providers: null,
  lastCompare: null,
  lastRun: null,
  lastValidation: null,
  lastSearch: null,
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

function prettyJson(value) {
  return escapeHtml(JSON.stringify(value ?? {}, null, 2));
}

function jsonBlock(value) {
  return `<pre class="json-block">${prettyJson(value)}</pre>`;
}

function openInspector(title, body) {
  $("#inspector-title").textContent = title;
  $("#inspector-body").innerHTML = body;
  $("#inspector").classList.add("open");
  $("#inspector").setAttribute("aria-hidden", "false");
}

function closeInspector() {
  $("#inspector").classList.remove("open");
  $("#inspector").setAttribute("aria-hidden", "true");
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
        render: (row) => (row.checks || []).map((check) => pill(check.code)).join(" "),
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
  state.lastSearch = result;
  $("#search-summary").textContent = `${result.contexts.length} contexts`;
  $("#search-results").innerHTML = renderContexts(result.contexts || []);
  if (result.trace) {
    openInspector("Search Trace", renderTrace(result));
  }
}

function renderContexts(contexts) {
  if (!contexts.length) return '<div class="empty">No contexts returned.</div>';
  return contexts
    .map((context, index) => {
      const source = context.source_uri || context.metadata?.source_uri || context.doc_id || "-";
      const score = context.scores?.final ?? context.scores?.rrf ?? context.scores?.bm25 ?? null;
      const scoreText = score == null ? "-" : Number(score).toFixed(4);
      return `
        <article class="context-item">
          <div class="context-meta">
            ${pill(`#${index + 1}`)}
            ${pill(`score ${scoreText}`)}
            ${pill(source)}
          </div>
          <div class="context-text">${escapeHtml(context.content_markdown || "")}</div>
        </article>
      `;
    })
    .join("");
}

function renderTrace(result) {
  const trace = result.trace || {};
  const retrieval = trace.retrieval || {};
  const fusion = trace.fusion || {};
  const context = trace.context || {};
  return `
    <div class="trace-grid">
      <div class="summary-cell"><span>BM25 hits</span><strong>${escapeHtml(retrieval.bm25_hits ?? "-")}</strong></div>
      <div class="summary-cell"><span>Fusion candidates</span><strong>${escapeHtml((fusion.candidates || []).length)}</strong></div>
      <div class="summary-cell"><span>Final contexts</span><strong>${escapeHtml(context.final_items ?? result.contexts.length)}</strong></div>
    </div>
    ${jsonBlock(trace)}
  `;
}

async function validateApp() {
  const report = await api("/app/validate", { method: "POST", body: JSON.stringify({}) });
  state.lastValidation = report;
  $("#run-output").innerHTML = renderValidation(report);
  openInspector("Validation Report", jsonBlock(report));
}

async function runApp() {
  const report = await api("/app/run", { method: "POST", body: JSON.stringify({}) });
  state.lastRun = report;
  $("#run-output").innerHTML = renderRun(report);
  openInspector("Run Report", renderRunDetail(report));
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
  const artifacts = report.artifacts || [];
  const evalMetrics = report.run?.eval?.metrics;
  const summary = `
    <div class="summary-strip">
      <div class="summary-cell"><span>Collection</span><strong>${escapeHtml(report.run?.collection || "-")}</strong></div>
      <div class="summary-cell"><span>Artifacts</span><strong>${escapeHtml(artifacts.length)}</strong></div>
      <div class="summary-cell"><span>Recall@K</span><strong>${escapeHtml(evalMetrics?.recall_at_k ?? "-")}</strong></div>
    </div>
  `;
  return summary + table(
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

function renderRunDetail(report) {
  const artifacts = report.artifacts || [];
  const metrics = report.run?.eval?.metrics || {};
  const artifactTable = table(
    [
      { key: "kind", label: "Kind" },
      { key: "path", label: "Path", render: (row) => `<code>${escapeHtml(row.path)}</code>` },
    ],
    artifacts,
    "No artifacts written.",
  );
  const metricTable = table(
    [
      { key: "name", label: "Metric" },
      { key: "value", label: "Value" },
    ],
    Object.entries(metrics).map(([name, value]) => ({ name, value })),
    "No eval metrics.",
  );
  return `
    <div class="section-title">Artifacts</div>
    ${artifactTable}
    <div class="section-title">Eval Metrics</div>
    ${metricTable}
    <div class="section-title">Manifest</div>
    ${jsonBlock(report.run?.manifest || {})}
  `;
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
  state.lastCompare = report;
  $("#compare-output").innerHTML = renderCompare(report);
  openInspector("Compare Report", renderCompareDetail(report));
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
  const metrics = table(
    [
      { key: "name", label: "Metric" },
      { key: "before", label: "Before", render: (row) => escapeHtml(row.before ?? "") },
      { key: "after", label: "After", render: (row) => escapeHtml(row.after ?? "") },
      { key: "delta", label: "Delta", render: (row) => pill(row.delta ?? 0) },
    ],
    report.metrics || [],
    "No metric changes.",
  );
  return `
    <div class="section-title">Summary</div>
    ${summary}
    <div class="section-title">Manifest Changes</div>
    ${changes}
    <div class="section-title">Source Changes</div>
    ${sources}
    <div class="section-title">Eval Metrics</div>
    ${metrics}
  `;
}

function renderCompareDetail(report) {
  return `
    <div class="trace-grid">
      <div class="summary-cell"><span>Differences</span><strong>${escapeHtml(report.has_differences ? "yes" : "no")}</strong></div>
      <div class="summary-cell"><span>Manifest changes</span><strong>${escapeHtml((report.changes || []).length)}</strong></div>
      <div class="summary-cell"><span>Source changes</span><strong>${escapeHtml((report.sources || []).filter((source) => source.status !== "unchanged").length)}</strong></div>
    </div>
    ${jsonBlock(report)}
  `;
}

async function loadProviders() {
  const providers = await api("/app/providers");
  state.providers = providers;
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
  if (action === "show-search-trace") {
    if (state.lastSearch?.trace) openInspector("Search Trace", renderTrace(state.lastSearch));
    else setNotice("Run a traced search before opening trace details.");
  }
  if (action === "validate-app") guarded(validateApp);
  if (action === "run-app") guarded(runApp);
  if (action === "show-run-detail") {
    if (state.lastRun) openInspector("Run Report", renderRunDetail(state.lastRun));
    else if (state.lastValidation) openInspector("Validation Report", jsonBlock(state.lastValidation));
    else setNotice("Run or validate the app before opening details.");
  }
  if (action === "run-compare") guarded(runCompare);
  if (action === "show-compare-report") {
    if (state.lastCompare) openInspector("Compare Report", renderCompareDetail(state.lastCompare));
    else setNotice("Run a compare before opening the report.");
  }
  if (action === "load-providers") guarded(loadProviders);
  if (action === "show-provider-detail") {
    if (state.providers) openInspector("Provider Readiness", jsonBlock(state.providers));
    else setNotice("Load providers before opening details.");
  }
  if (action === "close-inspector") closeInspector();
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeInspector();
});

guarded(loadHealth);
guarded(loadDashboard);
