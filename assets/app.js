const PACKAGE_FILES = [
  "__init__.py",
  "_complexity.py",
  "_doctor.py",
  "_model.py",
  "_render.py",
  "_report.py",
  "_trace.py",
  "_tutor.py",
];

const PYODIDE_URL = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/";
const LINKED_VIEWS = ["tree", "expanded", "dag"];
const PLAYBACK_INTERVAL_MS = 350;
const STEP_CONTROLS = ["first", "prev", "next", "last", "slider"];

const state = {
  pyodide: null,
  runPayload: null,
  growthPayload: null,
  suggestGrowthCall: null,
  growthInputCall: null,
  growthSuggestion: "",
  growthResult: null,
  source: "",
  steps: [],
  index: 0,
  playbackTimer: null,
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
    state.growthPayload = state.pyodide.globals.get("growth_payload");
    state.suggestGrowthCall = state.pyodide.globals.get("suggest_growth_call");

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

async function run(prediction = null) {
  if (!state.runPayload) return;
  const button = el("run");
  button.disabled = true;
  el("predict").disabled = true;
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
    el("download-json").disabled = !data.json;
    loadTrace(data.trace);
    renderDoctor(data.doctor || []);
    document.querySelectorAll("#tabs button").forEach((tab) => { tab.disabled = false; });
    el("metrics").hidden = false;
    el("results").hidden = false;
    if (prediction === null) {
      switchTab(state.view);
    } else {
      const feedback = renderPrediction(prediction, data.comparison);
      switchTab("compare");
      feedback.focus();
    }

    const slider = el("slider");
    slider.max = Math.max(0, state.steps.length - 1);
    slider.value = 0;
    STEP_CONTROLS.forEach((id) => { el(id).disabled = !state.steps.length; });
    el("play").disabled = state.steps.length < 2;
    const requestedStep = Number(
      new URLSearchParams(window.location.search).get("step"),
    );
    renderStep(Number.isInteger(requestedStep) && requestedStep > 0 ? requestedStep : 0);

    const truncated = data.tutor.truncated ? " · recording truncated" : "";
    const error = data.run_error || data.tutor.error;
    if (error) {
      const hint = data.doctor?.some((finding) => finding.kind === "failed_call")
        ? "Open Recursion Doctor to follow the recorded error."
        : "Recorded trace available below.";
      setStatus(`${error} ${hint}`, true);
    } else {
      setStatus(`Done · ${state.steps.length} steps · v${data.version}${truncated}`);
    }
  } catch (error) {
    clearResults();
    setStatus(String(error), true);
  } finally {
    button.disabled = false;
    el("predict").disabled = false;
    el("growth-open").disabled = false;
  }
}

function clearResults() {
  stopPlayback();
  clearGrowth();
  state.source = "";
  state.steps = [];
  state.trace = null;
  state.callId = null;
  state.subproblemId = null;
  el("download-json").disabled = true;
  el("jsonout").textContent = "";
  el("metrics").replaceChildren();
  el("metrics").hidden = true;
  for (const view of ["tree", "expanded", "dag", "compare", "doctor"]) {
    el(`panel-${view}`).replaceChildren();
  }
  STEP_CONTROLS.forEach((id) => { el(id).disabled = true; });
  el("play").disabled = true;
  renderStep(0);
  el("stepout").textContent = "";
  el("stepout").hidden = true;
  document.querySelectorAll("#tabs button").forEach((tab) => {
    tab.disabled = tab.dataset.tab !== "growth";
  });
  el("results").hidden = state.view !== "growth";
  renderSelection();
}

function markResultsStale() {
  if (el("results").hidden) return;
  clearResults();
  if (state.view === "growth") showGrowth();
  setStatus(state.view === "growth"
    ? "Code or call changed. Measure growth again."
    : "Code or call changed. Run again to see the new trace.");
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
  const labels = metrics?.truncated
    ? [...METRIC_LABELS, ["recorded_calls", "Recorded calls"]]
    : METRIC_LABELS;
  host.innerHTML = labels.map(([key, label]) => {
    const value = metrics && metrics[key] !== undefined ? metrics[key] : "–";
    return `<div class="metric"><div class="k">${label}</div><div class="v">${value}</div></div>`;
  }).join("");
}

function renderPrediction(guess, comparison) {
  const card = element("section", undefined, "card prediction-result");
  card.tabIndex = -1;
  card.setAttribute("aria-labelledby", "prediction-result-title");
  const heading = element("h2", "Cache savings prediction");
  heading.id = "prediction-result-title";
  card.append(heading);

  const cachedLabel = comparison?.labels?.[1] || "cached";
  if (!comparison?.same_result) {
    card.append(element("p", "A prediction needs two successful runs with matching results."));
  } else {
    const before = comparison.left.executed_calls;
    const after = comparison.right.executed_calls;
    const saved = before - after;
    if (saved < 0) {
      card.append(element("p", `The ${cachedLabel} run executed more function bodies. Inspect the comparison below.`));
    } else {
      heading.textContent = guess === saved ? "Prediction correct" : "Prediction checked";
      card.append(element("p", `You guessed ${guess}. This run saved ${saved} function body executions (${before} → ${after}).`));
      card.append(element("p", `The ${cachedLabel} run had ${comparison.right.cached_calls} cache hits. A cache hit skips the function body and any recursive calls it would make.`, "trace-note"));
    }
  }
  el("panel-compare").prepend(card);
  return card;
}

function openPrediction() {
  const call = el("call").value.trim();
  if (!call) {
    setStatus("Enter a function call before making a prediction.", true);
    el("call").focus();
    return;
  }
  el("prediction-call").textContent = call;
  el("prediction-value").value = "";
  el("prediction-dialog").showModal();
}

/* ------------------------------------------------------- growth chart */

function drawGrowthChart(samples) {
  const canvas = el("growth-chart");
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  const context = canvas.getContext("2d");
  if (!width || !height || !context) return;

  const density = window.devicePixelRatio || 1;
  canvas.width = Math.round(width * density);
  canvas.height = Math.round(height * density);
  context.scale(density, density);

  const left = 52;
  const right = width - 16;
  const top = 32;
  const bottom = height - 40;
  const firstSize = samples[0].size;
  const lastSize = samples[samples.length - 1].size;
  const maximum = Math.max(...samples.flatMap((sample) => [sample.naive, sample.memoized]));
  const magnitude = Math.max(1, 10 ** Math.floor(Math.log10(maximum / 4)));
  const tick = Math.ceil(maximum / (4 * magnitude)) * magnitude;
  const ceiling = Math.ceil(maximum / tick) * tick;
  const xAt = (size) => left + (right - left) * (size - firstSize) / Math.max(1, lastSize - firstSize);
  const yAt = (count) => bottom - (bottom - top) * count / ceiling;

  const style = getComputedStyle(canvas);
  const color = (name) => style.getPropertyValue(name).trim();
  context.font = "12px system-ui, sans-serif";
  context.fillStyle = color("--muted");
  context.textBaseline = "middle";
  context.fillText("Function executions", left, 14);
  context.textAlign = "right";
  context.strokeStyle = color("--line");
  for (let count = 0; count <= ceiling; count += tick) {
    const y = yAt(count);
    context.fillText(count.toLocaleString("en-US"), left - 8, y);
    context.beginPath();
    context.moveTo(left, y);
    context.lineTo(right, y);
    context.stroke();
  }
  context.textAlign = "center";
  for (const sample of samples) {
    context.fillText(sample.size, xAt(sample.size), bottom + 13);
  }
  context.fillText("Input size (n)", (left + right) / 2, height - 8);

  const series = [
    { key: "naive", color: color("--coral"), dash: [] },
    { key: "memoized", color: color("--blue"), dash: [5, 4] },
  ];
  for (const line of series) {
    context.strokeStyle = line.color;
    context.fillStyle = line.color;
    context.lineWidth = 2.5;
    context.lineJoin = "round";
    context.setLineDash(line.dash);
    context.beginPath();
    context.moveTo(xAt(firstSize), yAt(samples[0][line.key]));
    for (const sample of samples.slice(1)) {
      context.lineTo(xAt(sample.size), yAt(sample[line.key]));
    }
    context.stroke();
    for (const sample of samples) {
      context.beginPath();
      context.arc(xAt(sample.size), yAt(sample[line.key]), 3, 0, 2 * Math.PI);
      context.fill();
    }
  }
}

function describeGrowthFit(fit) {
  if (!fit) return "Use at least three input sizes to estimate growth.";
  const quality = Number.isFinite(fit.r2) ? `R\u00b2 ${fit.r2.toFixed(2)}` : "";
  const warning = fit.warning ? ` ${fit.warning}` : "";
  return `Best measured fit ${fit.model} (${quality} over ${fit.samples.length} sizes).${warning}`;
}

function showGrowth() {
  const call = el("call").value.trim();
  const field = el("growth-call");
  if (state.growthInputCall !== call || field.value === state.growthSuggestion) {
    const suggestion = state.suggestGrowthCall?.(call, el("code").value) || "";
    field.value = suggestion;
    state.growthSuggestion = suggestion;
  }
  state.growthInputCall = call;
  if (state.growthResult) {
    drawGrowthChart(state.growthResult.samples);
  }
}

function clearGrowth() {
  state.growthResult = null;
  el("growth-output").hidden = true;
  el("growth-error").hidden = true;
}

function measureGrowth(event) {
  event.preventDefault();
  clearGrowth();
  const status = el("growth-error");
  const button = el("growth-run");
  if (!state.growthPayload) {
    status.textContent = "Wait for the Python runtime to load.";
    status.hidden = false;
    return;
  }

  button.disabled = true;
  setStatus("Measuring growth…");
  try {
    const template = el("growth-call").value.trim();
    const start = el("growth-start").valueAsNumber;
    const stop = el("growth-stop").valueAsNumber;
    const step = el("growth-step").valueAsNumber;
    const data = JSON.parse(state.growthPayload(el("code").value, template, start, stop, step));
    if (data.error) {
      throw new Error(data.failed_call ? `${data.failed_call} — ${data.error}` : data.error);
    }
    const samples = data.samples;
    const format = (count) => count.toLocaleString("en-US");
    const last = samples[samples.length - 1];
    el("growth-summary").textContent =
      `${last.call} took ${format(last.naive)} function body executions without memoization and ${format(last.memoized)} with it.`;
    state.growthResult = { samples, fit: data.fit, memoizedFit: data.memoized_fit };
    el("growth-fit").textContent = `Without memoization — ${describeGrowthFit(state.growthResult.fit)}`;
    el("growth-fit-cached").textContent = `With memoization — ${describeGrowthFit(state.growthResult.memoizedFit)}`;
    const rows = samples.map((sample) => {
      const row = element("tr");
      const name = element("th");
      name.scope = "row";
      name.append(element("code", sample.call));
      row.append(name, element("td", format(sample.naive)), element("td", format(sample.memoized)));
      return row;
    });
    el("growth-counts").replaceChildren(...rows);
    el("growth-output").hidden = false;
    drawGrowthChart(samples);
    setStatus(`Done · measured ${samples.length} growth input sizes`);
  } catch (error) {
    status.textContent = String(error.message ?? error);
    status.hidden = false;
    setStatus("Growth measurement failed. See the message below.", true);
  } finally {
    button.disabled = false;
  }
}

function downloadGrowthCsv() {
  if (!state.growthResult) return;
  const { samples } = state.growthResult;

  const rows = ["input_size,input_call,bodies_without_memoization,bodies_with_memoization,bodies_saved"];
  for (const sample of samples) {
    const call = `"${sample.call.replaceAll('"', '""')}"`;
    rows.push([
      sample.size,
      call,
      sample.naive,
      sample.memoized,
      sample.naive - sample.memoized,
    ].join(","));
  }
  downloadText("recursionlens-growth.csv", "text/csv", rows.join("\r\n") + "\r\n");
}

function wireGrowth() {
  el("growth-form").addEventListener("submit", measureGrowth);
  el("growth-form").addEventListener("input", clearGrowth);
  el("download-growth").addEventListener("click", downloadGrowthCsv);
  window.addEventListener("resize", () => {
    if (state.view === "growth" && state.growthResult) {
      drawGrowthChart(state.growthResult.samples);
    }
  });
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

function stopPlayback() {
  if (state.playbackTimer === null) return;
  window.clearInterval(state.playbackTimer);
  state.playbackTimer = null;
  el("play").textContent = "Play";
}

function seekStep(index) {
  stopPlayback();
  renderStep(index);
}

function togglePlayback() {
  if (state.playbackTimer !== null) {
    stopPlayback();
    return;
  }

  const last = state.steps.length - 1;
  if (last < 1) return;
  if (state.index === last) renderStep(0);
  el("play").textContent = "Pause";
  state.playbackTimer = window.setInterval(() => {
    renderStep(state.index + 1);
    if (state.index === last) stopPlayback();
  }, PLAYBACK_INTERVAL_MS);
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

function downloadText(filename, type, text) {
  const url = URL.createObjectURL(new Blob([text], { type: `${type};charset=utf-8` }));
  const link = element("a");
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
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
  if (el(`tab-${name}`).disabled) return;
  if (name !== "step") stopPlayback();
  state.view = name;
  document.querySelectorAll("#tabs button").forEach((button) => {
    const active = button.dataset.tab === name;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
    button.tabIndex = active ? 0 : -1;
    el(button.getAttribute("aria-controls")).hidden = !active;
  });
  renderSelection();
  if (name === "growth") showGrowth();
}

function populateExamples() {
  const select = el("example");
  const examples = window.RL_EXAMPLES || [];
  if (!select || !examples.length) return;

  const copy = el("copy-example");
  const linkStatus = el("example-link-status");
  const linkField = el("example-link");
  const examplesById = new Map(examples.map((item) => [item.id, item]));
  const groups = new Map();
  for (const item of examples) {
    if (!groups.has(item.lecture)) groups.set(item.lecture, []);
    groups.get(item.lecture).push(item);
  }

  select.innerHTML =
    '<option value="">Custom code…</option>' +
    [...groups]
      .map(
        ([lecture, items]) =>
          `<optgroup label="${escapeHtml(lecture)}">` +
          items
            .map(
              (item) =>
                `<option value="${item.id}">${escapeHtml(item.name)} · ${escapeHtml(item.call)}</option>`,
            )
            .join("") +
          "</optgroup>",
      )
      .join("");

  const selectExample = (item) => {
    select.value = item?.id ?? "";
    el("example-note").textContent = item?.note ?? "";
    copy.disabled = !item;
    linkStatus.textContent = "";
    linkField.value = "";
    linkField.hidden = true;

    if (item) {
      el("code").value = item.code;
      el("call").value = item.call;
      run();
    }
  };

  select.addEventListener("change", () => selectExample(examplesById.get(select.value)));
  const useCustomCode = () => {
    if (select.value) selectExample();
  };
  el("code").addEventListener("input", useCustomCode);
  el("call").addEventListener("input", useCustomCode);

  copy.addEventListener("click", async () => {
    const id = select.value;
    if (!id) return;
    const link = new URL(window.location.href);
    link.search = "";
    link.hash = "";
    link.searchParams.set("example", id);

    let copied = false;
    try {
      await navigator.clipboard.writeText(link.href);
      copied = true;
    } catch {
      // Keep the URL available for manual copying when the clipboard is unavailable.
    }

    if (select.value !== id) return;
    linkStatus.textContent = copied ? "Link copied." : "Copy the link below.";
    linkField.hidden = copied;
    linkField.value = copied ? "" : link.href;
    if (!copied) {
      linkField.focus();
      linkField.select();
    }
  });

  const requested = new URLSearchParams(window.location.search).get("example");
  const initial = examplesById.get(requested) ?? (requested && examples[Number(requested)]);
  if (initial) selectExample(initial);
}

function wire() {
  el("code").addEventListener("input", markResultsStale);
  el("call").addEventListener("input", markResultsStale);
  el("run").addEventListener("click", () => run());
  el("growth-open").addEventListener("click", () => {
    el("results").hidden = false;
    switchTab("growth");
    setStatus("Growth ready. Set a call template and input range.");
  });
  el("download-json").addEventListener("click", () => {
    downloadText("recursionlens-trace.json", "application/json", el("jsonout").textContent);
  });
  el("predict").addEventListener("click", openPrediction);
  el("prediction-cancel").addEventListener("click", () => el("prediction-dialog").close());
  el("prediction-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const guess = el("prediction-value").valueAsNumber;
    el("prediction-dialog").close();
    run(guess);
  });
  el("call").addEventListener("keydown", (event) => {
    if (event.key === "Enter") run();
  });
  el("first").addEventListener("click", () => seekStep(0));
  el("prev").addEventListener("click", () => seekStep(state.index - 1));
  el("play").addEventListener("click", togglePlayback);
  el("next").addEventListener("click", () => seekStep(state.index + 1));
  el("last").addEventListener("click", () => seekStep(state.steps.length - 1));
  el("slider").addEventListener("input", (event) => seekStep(Number(event.target.value)));

  const tabs = [...document.querySelectorAll("#tabs button")];
  tabs.forEach((button) => {
    button.addEventListener("click", () => switchTab(button.dataset.tab));
    button.addEventListener("keydown", (event) => {
      const enabled = tabs.filter((tab) => !tab.disabled);
      const index = enabled.indexOf(button);
      let next;
      if (event.key === "ArrowRight") next = (index + 1) % enabled.length;
      else if (event.key === "ArrowLeft") next = (index + enabled.length - 1) % enabled.length;
      else if (event.key === "Home") next = 0;
      else if (event.key === "End") next = enabled.length - 1;
      else return;
      event.preventDefault();
      switchTab(enabled[next].dataset.tab);
      enabled[next].focus();
    });
  });

  populateExamples();
  wireGrowth();

  document.addEventListener("keydown", (event) => {
    if (state.view !== "step" || !state.steps.length) return;
    if (event.defaultPrevented || event.target.closest("textarea, input, select, dialog, #tabs")) return;
    if (event.key === "ArrowRight") seekStep(state.index + 1);
    if (event.key === "ArrowLeft") seekStep(state.index - 1);
  });
}

wire();
boot();
