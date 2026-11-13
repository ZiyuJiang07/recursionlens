const PACKAGE_FILES = [
  "__init__.py",
  "_model.py",
  "_render.py",
  "_report.py",
  "_trace.py",
  "_tutor.py",
];

const PYODIDE_URL = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/";

const EXAMPLES = {
  fib: `def fib(n):
    if n < 2:
        return n
    return fib(n - 1) + fib(n - 2)
`,
  fact: `def fact(n):
    if n <= 1:
        return 1
    return n * fact(n - 1)
`,
  sum: `def total(values):
    if not values:
        return 0
    return values[0] + total(values[1:])
`,
};

const state = {
  pyodide: null,
  runPayload: null,
  steps: [],
  index: 0,
  tutor: null,
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
      const response = await fetch(`src/recursionlens/${name}`);
      if (!response.ok) throw new Error(`cannot load ${name}`);
      fs.writeFile(`/rl/recursionlens/${name}`, await response.text());
    }

    state.pyodide.runPython('import sys; sys.path.insert(0, "/rl")');
    const bridge = await (await fetch("assets/bridge.py")).text();
    state.pyodide.runPython(bridge);
    state.runPayload = state.pyodide.globals.get("run_payload");

    setStatus("ready");
    await run();
  } catch (error) {
    setStatus(`failed to start: ${error}`, true);
  }
}

/* ---------------------------------------------------------------- run */

async function run() {
  if (!state.runPayload) return;
  const button = el("run");
  button.disabled = true;
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

    state.tutor = data.tutor;
    state.steps = data.tutor.steps || [];
    state.index = 0;

    renderMetrics(data.metrics);
    el("panel-tree").innerHTML = data.views.tree;
    el("panel-expanded").innerHTML = data.views.expanded;
    el("panel-dag").innerHTML = data.views.dag;
    el("panel-compare").innerHTML = data.views.compare;
    el("jsonout").textContent =
      data.json || "// JSON omitted for this run because it is very large.";

    const slider = el("slider");
    slider.max = Math.max(0, state.steps.length - 1);
    slider.value = 0;
    renderStep(0);

    const suffix = data.tutor.error ? ` · ${data.tutor.error}` : "";
    const truncated = data.tutor.truncated ? " · recording truncated" : "";
    setStatus(`done · ${state.steps.length} steps${suffix}${truncated}`);
  } catch (error) {
    setStatus(String(error), true);
  } finally {
    button.disabled = false;
  }
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
  const lines = el("code").value.split("\n");
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

/* ---------------------------------------------------------------- ui */

function switchTab(name) {
  document.querySelectorAll("#tabs button").forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === name);
  });
  ["step", "tree", "expanded", "dag", "compare", "json"].forEach((key) => {
    el(`panel-${key}`).hidden = key !== name;
  });
}

function wire() {
  el("run").addEventListener("click", run);
  el("call").addEventListener("keydown", (event) => {
    if (event.key === "Enter") run();
  });
  el("first").addEventListener("click", () => renderStep(0));
  el("prev").addEventListener("click", () => renderStep(state.index - 1));
  el("next").addEventListener("click", () => renderStep(state.index + 1));
  el("last").addEventListener("click", () => renderStep(state.steps.length - 1));
  el("slider").addEventListener("input", (event) => renderStep(Number(event.target.value)));

  document.querySelectorAll("#tabs button").forEach((button) => {
    button.addEventListener("click", () => switchTab(button.dataset.tab));
  });

  document.querySelectorAll(".chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      el("code").value = EXAMPLES[chip.dataset.code] || el("code").value;
      el("call").value = chip.dataset.call;
      run();
    });
  });

  document.addEventListener("keydown", (event) => {
    if (event.target.tagName === "TEXTAREA" || event.target.tagName === "INPUT") return;
    if (event.key === "ArrowRight") renderStep(state.index + 1);
    if (event.key === "ArrowLeft") renderStep(state.index - 1);
  });
}

wire();
boot();
