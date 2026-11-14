const PACKAGE_FILES = [
  "__init__.py",
  "_doctor.py",
  "_model.py",
  "_render.py",
  "_report.py",
  "_trace.py",
  "_tutor.py",
];

const PYODIDE_URL = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/";
const LINKED_VIEWS = ["tree", "expanded", "dag"];
const STEP_CONTROLS = ["first", "prev", "next", "last", "slider"];

const state = {
  pyodide: null,
  runPayload: null,
  source: "",
  steps: [],
  index: 0,
  trace: null,
  view: "step",
  callId: null,
  subproblemId: null,
};

const el = (id) => document.getElementById(id);

function setStatus(text, isError = false) {
  const node = el("status");
  node.textContent = text;
  node.classList.toggle("error", Boolean(isError));
}

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

/* ---------------------------------------------------------------- boot */

async function boot() {
  try {
    setStatus("loading Python runtime…");
    state.pyodide = await loadPyodide({ indexURL: PYODIDE_URL });

    const fs = state.pyodide.FS;
    fs.mkdirTree("/rl/recursionlens");
    for (const name of PACKAGE_FILES) {
      const response = await fetch(`src/recursionlens/${name}`, { cache: "no-store" });
      if (!response.ok) throw new Error(`cannot load ${name}`);
      fs.writeFile(`/rl/recursionlens/${name}`, await response.text());
    }

    state.pyodide.runPython('import sys; sys.path.insert(0, "/rl")');
    const bridge = await (await fetch("assets/bridge.py", { cache: "no-store" })).text();
    state.pyodide.runPython(bridge);
    state.runPayload = state.pyodide.globals.get("run_payload");

    setStatus("ready");
    showBuild();
    await run();
  } catch (error) {
    setStatus(`failed to start: ${error}`, true);
  }
}

async function showBuild() {
  try {
    const response = await fetch("version.json", { cache: "no-store" });
    if (!response.ok) return;
    const info = await response.json();
    const tag = document.querySelector(".brand .tag");
    if (tag && info.commit) {
      tag.textContent = `web playground · ${String(info.commit).slice(0, 7)}`;
      tag.title = `deployed ${info.built || ""}`;
    }
  } catch (error) {
    /* the badge is optional */
  }
}

/* ---------------------------------------------------------------- run */

async function run() {
  if (!state.runPayload) return;
  const button = el("run");
  button.disabled = true;
  clearResults();
  setStatus("running…");

  try {
    const code = el("code").value;
    const call = el("call").value.trim();
    const raw = state.runPayload(code, call);
    const data = JSON.parse(raw);

    if (data.error) {
      setStatus(data.error, true);
      return;
    }

    state.source = code;
    state.steps = data.tutor.steps || [];
    state.index = 0;

    renderMetrics(data.metrics);
    el("panel-tree").innerHTML = data.views.tree;
    el("panel-expanded").innerHTML = data.views.expanded;
    el("panel-dag").innerHTML = data.views.dag;
    el("panel-compare").innerHTML = data.views.compare;
    el("jsonout").textContent =
      data.json || "// JSON omitted for this run because it is very large.";
    loadTrace(data.trace);
    renderDoctor(data.doctor || []);
    el("results").hidden = false;
    switchTab(state.view);

    const slider = el("slider");
    slider.max = Math.max(0, state.steps.length - 1);
    slider.value = 0;
    STEP_CONTROLS.forEach((id) => { el(id).disabled = !state.steps.length; });
    renderStep(0);

    const truncated = data.tutor.truncated ? " · recording truncated" : "";
    const error = data.run_error || data.tutor.error;
    if (error) {
      setStatus(`${error} Recorded trace available below.`, true);
    } else {
      setStatus(`Done · ${state.steps.length} steps · v${data.version}${truncated}`);
    }
  } catch (error) {
    clearResults();
    setStatus(String(error), true);
  } finally {
    button.disabled = false;
  }
}

function clearResults() {
  state.source = "";
  state.steps = [];
  state.trace = null;
  state.callId = null;
  state.subproblemId = null;
  el("results").hidden = true;
}

function markResultsStale() {
  if (el("results").hidden) return;
  clearResults();
  setStatus("Code or call changed. Run again to see the new trace.");
}

const METRIC_LABELS = [
  ["total_calls", "Observed calls"],
  ["executed_calls", "Executed bodies"],
  ["cached_calls", "Cache hits"],
  ["unique_subproblems", "Unique subproblems"],
  ["repeated_calls", "Repeated calls"],
  ["max_depth", "Maximum depth"],
];

function renderMetrics(metrics) {
  const host = el("metrics");
  host.innerHTML = METRIC_LABELS.map(([key, label]) => {
    const value = metrics && metrics[key] !== undefined ? metrics[key] : "–";
    return `<div class="metric"><div class="k">${label}</div><div class="v">${value}</div></div>`;
  }).join("");
}

/* -------------------------------------------------------------- player */

function frameLabel(frame) {
  const values = Object.entries(frame.variables || {})
    .filter(([name]) => !name.startsWith("_"))
    .map(([, value]) => value)
    .slice(0, 2);
  const text = values.length
    ? `${frame.function}(${values.join(", ")})`
    : `${frame.function}()`;
  return text.length <= 22 ? text : `${text.slice(0, 19)}…`;
}

function buildTree(steps, upto) {
  const nodes = [];
  const stack = [];
  let pendingPop = false;

  for (let i = 0; i <= upto && i < steps.length; i += 1) {
    const step = steps[i];
    if (pendingPop) {
      if (stack.length) stack.pop();
      pendingPop = false;
    }

    if (step.event === "call" && step.frames.length) {
      const frame = step.frames[step.frames.length - 1];
      const node = {
        id: nodes.length,
        parent: stack.length ? stack[stack.length - 1] : null,
        label: frameLabel(frame),
        line: step.line,
        status: "running",
        value: null,
        children: [],
      };
      if (node.parent !== null) nodes[node.parent].children.push(node.id);
      nodes.push(node);
      stack.push(node.id);
    } else if (step.event === "return" || step.event === "exception") {
      if (stack.length) {
        const node = nodes[stack[stack.length - 1]];
        node.status = step.event === "return" ? "returned" : "error";
        node.value = step.value;
        node.line = step.line;
        pendingPop = true;
      }
    } else if (step.event === "line" && stack.length) {
      nodes[stack[stack.length - 1]].line = step.line;
    }
  }

  return { nodes, running: stack };
}

const COLORS = {
  running: { fill: "#ffffff", stroke: "#c3d4e6", ink: "#185fa5" },
  current: { fill: "#fdf1ec", stroke: "#d85a30", ink: "#993c1d" },
  returning: { fill: "#eaf6f0", stroke: "#d85a30", ink: "#0b5c48" },
  returned: { fill: "#eaf6f0", stroke: "#a9cdbf", ink: "#0b5c48" },
  error: { fill: "#fdecec", stroke: "#e3a6a6", ink: "#a32d2d" },
  errorCurrent: { fill: "#fdecec", stroke: "#a32d2d", ink: "#a32d2d" },
};

function styleFor(node, current) {
  if (node.id === current) {
    if (node.status === "error") return COLORS.errorCurrent;
    if (node.status === "returned") return COLORS.returning;
    return COLORS.current;
  }
  if (node.status === "error") return COLORS.error;
  if (node.status === "returned") return COLORS.returned;
  return COLORS.running;
}

function renderTree(nodes, running) {
  if (!nodes.length) return "";
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const widths = new Map();
  nodes.forEach((node) => {
    widths.set(node.id, Math.max(54, Math.min(150, node.label.length * 6.1 + 18)));
  });

  const positions = new Map();
  let cursor = 0;
  const gap = 16;
  const level = 52;
  const height = 26;

  function place(id, depth) {
    const node = byId.get(id);
    const kids = node.children.filter((child) => byId.has(child));
    if (!kids.length) {
      const x = cursor + widths.get(id) / 2;
      cursor = x + widths.get(id) / 2 + gap;
      positions.set(id, { x, y: 22 + depth * level });
      return;
    }
    kids.forEach((kid) => place(kid, depth + 1));
    const first = positions.get(kids[0]).x;
    const lastX = positions.get(kids[kids.length - 1]).x;
    positions.set(id, { x: (first + lastX) / 2, y: 22 + depth * level });
  }

  const roots = nodes.filter((node) => node.parent === null || !byId.has(node.parent));
  roots.forEach((root) => place(root.id, 0));

  const content = Math.max(0, cursor - gap);
  const width = Math.max(380, content + 28);
  const shift = (width - content) / 2;
  const depthMax = Math.max(...[...positions.values()].map((p) => p.y));
  const svgHeight = depthMax + height + 22;
  const current = running.length ? running[running.length - 1] : null;

  const parts = [
    `<svg viewBox="0 0 ${width.toFixed(0)} ${svgHeight.toFixed(0)}" width="${width.toFixed(0)}" height="${svgHeight.toFixed(0)}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Call tree">`,
  ];

  nodes.forEach((node) => {
    const from = positions.get(node.id);
    node.children.forEach((childId) => {
      if (!byId.has(childId)) return;
      const to = positions.get(childId);
      const start = from.y + height / 2;
      const end = to.y - height / 2;
      const mid = (start + end) / 2;
      parts.push(
        `<path d="M${(from.x + shift).toFixed(1)},${start.toFixed(1)} C${(from.x + shift).toFixed(1)},${mid.toFixed(1)} ${(to.x + shift).toFixed(1)},${mid.toFixed(1)} ${(to.x + shift).toFixed(1)},${end.toFixed(1)}" fill="none" stroke="#cfccc3" stroke-width="1"/>`,
      );
    });
  });

  nodes.forEach((node) => {
    const point = positions.get(node.id);
    const palette = styleFor(node, current);
    const x = point.x + shift;
    const left = x - widths.get(node.id) / 2;
    const tip = `${node.label} · line ${node.line}${node.value ? ` · ${node.value}` : ""}`;
    parts.push(
      `<g><title>${escapeHtml(tip)}</title>` +
        `<rect x="${left.toFixed(1)}" y="${(point.y - height / 2).toFixed(1)}" width="${widths.get(node.id).toFixed(1)}" height="${height}" rx="7" fill="${palette.fill}" stroke="${palette.stroke}" stroke-width="1"/>` +
        `<text x="${x.toFixed(1)}" y="${(point.y + 3.9).toFixed(1)}" text-anchor="middle" font-family="ui-monospace,SFMono-Regular,Menlo,monospace" font-size="11" fill="${palette.ink}">${escapeHtml(node.label)}</text></g>`,
    );
  });

  parts.push("</svg>");
  return parts.join("");
}

function renderCode(step) {
  const lines = state.source.split("\n");
  const currentLine = step ? step.line : -1;
  el("stepcode").innerHTML = lines
    .map((text, i) => {
      const number = i + 1;
      const cls = number === currentLine ? "ln cur" : "ln";
      const body = escapeHtml(text) || "&nbsp;";
      return `<div class="${cls}"><span class="n">${number}</span><span class="t">${body}</span></div>`;
    })
    .join("");
}

function renderFrame(step) {
  const host = el("stepframe");
  if (!step || !step.frames.length) {
    host.innerHTML = "";
    return;
  }
  const frame = step.frames[step.frames.length - 1];
  const vars = Object.entries(frame.variables || {});
  const rows = vars.length
    ? vars
        .map(
          ([name, value]) =>
            `<span class="k">${escapeHtml(name)}</span><span class="v">${escapeHtml(value)}</span>`,
        )
        .join("")
    : '<span class="v">(no locals)</span>';
  host.innerHTML =
    `<div class="head">${escapeHtml(frame.function)}<span>current · line ${frame.line}</span></div>` +
    `<div class="vars">${rows}</div>`;
}

function renderStep(index) {
  if (!state.steps.length) {
    renderCode(null);
    el("steptree").innerHTML = "";
    el("stepframe").innerHTML = "";
    el("stepinfo").textContent = "no steps recorded";
    return;
  }
  const clamped = Math.max(0, Math.min(index, state.steps.length - 1));
  state.index = clamped;
  const step = state.steps[clamped];

  el("slider").value = String(clamped);
  const tag = step.event === "line" ? "" : ` · ${step.event}`;
  const detail = step.event === "return" && step.value ? ` · ${step.value}` : "";
  el("stepinfo").textContent = `step ${clamped + 1} / ${state.steps.length} · line ${step.line}${tag}${detail}`;

  renderCode(step);
  const { nodes, running } = buildTree(state.steps, clamped);
  el("steptree").innerHTML = renderTree(nodes, running);
  renderFrame(step);

  const out = el("stepout");
  if (step.output && step.output.trim()) {
    out.hidden = false;
    out.textContent = step.output;
  } else {
    out.hidden = true;
    out.textContent = "";
  }
}

/* --------------------------------------------------------- linked trace */

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function actionButton(label, action, className = "trace-action") {
  const button = element("button", label, className);
  button.type = "button";
  button.addEventListener("click", action);
  return button;
}

function loadTrace(trace) {
  if (!trace) return;
  const calls = new Map();
  const subproblems = new Map(
    trace.dag.nodes.map((node) => [node.identity, { ...node, occurrences: [] }]),
  );

  function indexCalls(nodes, parentId) {
    for (const node of nodes) {
      calls.set(node.call_id, { ...node, parentId });
      subproblems.get(node.identity)?.occurrences.push(node.call_id);
      indexCalls(node.children, node.call_id);
    }
  }

  indexCalls(trace.roots, null);
  state.trace = { calls, subproblems };
  wireTraceNodes();
}

function wireTraceNodes() {
  const { calls, subproblems } = state.trace;
  for (const summary of el("panel-tree").querySelectorAll("summary[data-call-id]")) {
    const id = Number(summary.dataset.callId);
    const call = calls.get(id);
    if (!call) continue;
    const inspect = actionButton("Inspect", (event) => {
      event.preventDefault();
      selectCall(id);
    }, "trace-action inspect-call");
    inspect.setAttribute("aria-label", `Inspect call #${id + 1}, ${call.signature}`);
    summary.append(inspect);
  }

  for (const view of ["expanded", "dag"]) {
    const panel = el(`panel-${view}`);
    const svg = panel.querySelector("svg");
    if (svg) svg.setAttribute("role", "group");
    for (const group of panel.querySelectorAll("g[data-subproblem-id]")) {
      const callId = Number(group.dataset.callId);
      const identity = group.dataset.subproblemId;
      const item = view === "expanded" ? calls.get(callId) : subproblems.get(identity);
      if (!item) continue;
      const select = view === "expanded" ? () => selectCall(callId) : () => selectSubproblem(identity);
      group.setAttribute("role", "button");
      group.setAttribute("tabindex", "0");
      group.setAttribute("aria-label", item.signature);
      group.addEventListener("click", select);
      group.addEventListener("keydown", (event) => {
        if (event.key !== "Enter" && event.key !== " ") return;
        event.preventDefault();
        select();
      });
    }
  }
}

function callPath(callId) {
  const path = [];
  let id = callId;
  while (id !== null) {
    const call = state.trace.calls.get(id);
    path.push(call);
    id = call.parentId;
  }
  return path.reverse();
}

function selectCall(id, openTree = false) {
  const call = state.trace?.calls.get(id);
  if (!call) return;
  state.callId = id;
  state.subproblemId = call.identity;
  if (openTree) {
    switchTab("tree");
    focusTraceSelection();
  } else {
    renderSelection();
  }
}

function selectSubproblem(identity, openDag = false) {
  if (!state.trace?.subproblems.has(identity)) return;
  if (state.trace.calls.get(state.callId)?.identity !== identity) state.callId = null;
  state.subproblemId = identity;
  if (openDag) {
    switchTab("dag");
    focusTraceSelection();
  } else {
    renderSelection();
  }
}

function focusTraceSelection() {
  const panel = el(`panel-${state.view}`);
  const selected = panel.querySelector(
    state.view === "dag" ? ".subproblem-match" : ".call-selected .inspect-call, g.call-selected",
  );
  const target = selected || el("inspector-heading");
  target.focus({ preventScroll: true });
  target.scrollIntoView({ block: "nearest", inline: "nearest" });
}

function renderSelection() {
  const inspector = el("trace-inspector");
  inspector.hidden = !state.trace || !LINKED_VIEWS.includes(state.view);
  if (inspector.hidden) return;

  const path = callPath(state.callId);
  const pathIds = new Set(path.map((call) => call.call_id));
  const body = el("inspector-body");
  const panel = el(`panel-${state.view}`);
  for (const node of panel.querySelectorAll("[data-subproblem-id]")) {
    const id = Number(node.dataset.callId);
    const match = node.dataset.subproblemId === state.subproblemId;
    const selected = id === state.callId;
    node.classList.toggle("subproblem-match", match);
    node.classList.toggle("call-on-path", pathIds.has(id));
    node.classList.toggle("call-selected", selected);

    if (node.matches("summary")) {
      node.querySelector(".inspect-call")?.setAttribute("aria-pressed", String(selected));
      if (pathIds.has(id)) node.parentElement.open = true;
    } else if (node.getAttribute("role") === "button") {
      node.setAttribute("aria-pressed", String(state.view === "dag" ? match : selected));
    }
  }
  for (const edge of panel.querySelectorAll("[data-parent-call-id][data-child-call-id]")) {
    const onPath = pathIds.has(Number(edge.dataset.parentCallId))
      && pathIds.has(Number(edge.dataset.childCallId));
    edge.classList.toggle("call-on-path", onPath);
  }

  body.replaceChildren();
  const subproblem = state.trace.subproblems.get(state.subproblemId);
  if (!subproblem) {
    body.append(element("p", state.view === "dag"
      ? "Select a node to find every recorded call to that subproblem."
      : state.view === "tree"
        ? "Choose Inspect next to a call to see its path from the root and find its subproblem."
        : "Select a call to highlight its path from the root and find its subproblem.", "trace-note"));
    return;
  }

  body.append(element("h3", "Subproblem"));
  body.append(element("code", subproblem.signature));
  const recorded = subproblem.occurrences.length;
  body.append(element("p", `${recorded} recorded ${recorded === 1 ? "call" : "calls"} · ${subproblem.executed} executed · ${subproblem.cached} cache hits`, "trace-note"));
  if (path.length) {
    const call = path.at(-1);
    body.append(element("h3", "Call path"));
    const chain = element("ol", undefined, "call-path");
    for (const entry of path) {
      const item = element("li");
      const selected = entry.call_id === state.callId;
      const label = `#${entry.call_id + 1} ${entry.signature}`;
      if (selected) {
        item.append(element("code", label));
        item.setAttribute("aria-current", "true");
      } else {
        item.append(actionButton(label, () => selectCall(entry.call_id, true)));
      }
      chain.append(item);
    }
    body.append(chain);
    if (call.error) body.append(element("p", call.error, "trace-note trace-error"));
    else if (call.result !== null) body.append(element("p", `Returned ${call.result}`, "trace-note"));
  }
  if (state.view === "dag") {
    const visible = panel.querySelector(".subproblem-match");
    if (!visible) body.append(element("p", "This node is outside the rendered graph. Its recorded calls are listed below.", "trace-note"));
    body.append(element("h3", "Recorded calls"));
    const list = element("ul", undefined, "occurrence-list");
    for (const id of subproblem.occurrences) {
      const call = state.trace.calls.get(id);
      const item = element("li");
      const button = actionButton(`Call #${id + 1} · depth ${call.depth}`, () => selectCall(id, true));
      button.setAttribute("aria-label", `Show call #${id + 1} in tree, ${call.signature}`);
      item.append(button);
      list.append(item);
    }
    body.append(list);
  }
  const actions = element("div", undefined, "trace-actions");
  if (state.view !== "dag") {
    actions.append(actionButton("Show in DAG", () => selectSubproblem(subproblem.identity, true)));
  }
  actions.append(actionButton("Clear selection", () => {
    state.callId = null;
    state.subproblemId = null;
    renderSelection();
    el("inspector-heading").focus();
  }));
  body.append(actions);
}

function renderDoctor(findings) {
  const card = element("div", undefined, "card inner doctor");
  card.append(element("h2", "Recursion Doctor"));
  card.append(element("p", "Findings are based on calls recorded for this run.", "trace-note"));
  if (!findings.length) {
    card.append(element("p", "No repeated execution or recursive re-entry was found in the recorded calls."));
  }
  for (const finding of findings) {
    const article = element("article", undefined, "doctor-finding");
    article.append(element("h3", finding.title), element("p", finding.message));
    const actions = element("div", undefined, "trace-actions");
    for (const id of finding.call_ids) {
      const call = state.trace?.calls.get(id);
      if (!call) continue;
      const button = actionButton(`Show call #${id + 1}`, () => selectCall(id, true));
      button.setAttribute("aria-label", `Show call #${id + 1} in tree, ${call.signature}`);
      actions.append(button);
    }
    if (state.trace?.subproblems.has(finding.subproblem_id)) {
      actions.append(actionButton("Show in DAG", () => selectSubproblem(finding.subproblem_id, true)));
    }
    if (actions.childElementCount) article.append(actions);
    card.append(article);
  }
  el("panel-doctor").replaceChildren(card);
}

/* ---------------------------------------------------------------- ui */

function switchTab(name) {
  state.view = name;
  document.querySelectorAll("#tabs button").forEach((button) => {
    const active = button.dataset.tab === name;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
    button.tabIndex = active ? 0 : -1;
    el(button.getAttribute("aria-controls")).hidden = !active;
  });
  renderSelection();
}

function populateExamples() {
  const select = el("example");
  const examples = window.RL_EXAMPLES || [];
  if (!select || !examples.length) return;

  const groups = new Map();
  examples.forEach((item, index) => {
    if (!groups.has(item.lecture)) groups.set(item.lecture, []);
    groups.get(item.lecture).push({ ...item, index });
  });

  select.innerHTML =
    '<option value="">Custom code…</option>' +
    [...groups]
      .map(
        ([lecture, items]) =>
          `<optgroup label="${escapeHtml(lecture)}">` +
          items
            .map(
              (item) =>
                `<option value="${item.index}">${escapeHtml(item.name)} · ${escapeHtml(item.call)}</option>`,
            )
            .join("") +
          "</optgroup>",
      )
      .join("");

  const load = (index) => {
    const item = examples[index];
    if (!item) return;
    select.value = String(index);
    el("code").value = item.code;
    el("call").value = item.call;
    el("example-note").textContent = item.note || "";
    run();
  };

  select.addEventListener("change", () => {
    if (select.value !== "") load(Number(select.value));
  });

  const requested = new URLSearchParams(window.location.search).get("example");
  if (requested !== null) {
    const index = Number(requested);
    if (Number.isInteger(index) && examples[index]) {
      load(index);
      return;
    }
  }
}

function wire() {
  el("code").addEventListener("input", markResultsStale);
  el("call").addEventListener("input", markResultsStale);
  el("run").addEventListener("click", run);
  el("call").addEventListener("keydown", (event) => {
    if (event.key === "Enter") run();
  });
  el("first").addEventListener("click", () => renderStep(0));
  el("prev").addEventListener("click", () => renderStep(state.index - 1));
  el("next").addEventListener("click", () => renderStep(state.index + 1));
  el("last").addEventListener("click", () => renderStep(state.steps.length - 1));
  el("slider").addEventListener("input", (event) => renderStep(Number(event.target.value)));

  const tabs = [...document.querySelectorAll("#tabs button")];
  tabs.forEach((button, index) => {
    button.addEventListener("click", () => switchTab(button.dataset.tab));
    button.addEventListener("keydown", (event) => {
      let next;
      if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
      else if (event.key === "ArrowLeft") next = (index + tabs.length - 1) % tabs.length;
      else if (event.key === "Home") next = 0;
      else if (event.key === "End") next = tabs.length - 1;
      else return;
      event.preventDefault();
      switchTab(tabs[next].dataset.tab);
      tabs[next].focus();
    });
  });

  populateExamples();

  document.addEventListener("keydown", (event) => {
    if (state.view !== "step" || !state.steps.length) return;
    if (event.defaultPrevented || event.target.closest("textarea, input, select, #tabs")) return;
    if (event.key === "ArrowRight") renderStep(state.index + 1);
    if (event.key === "ArrowLeft") renderStep(state.index - 1);
  });
}

wire();
boot();
