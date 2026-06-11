/* Reusable State-Flow tree renderer. Turns a state_flow object
   {transitions:[{from_step,to_step,trigger,...}], function_calls:[...], initial_step}
   into a Mermaid flowchart. Dependency: window.mermaid (loaded once by the host page).
   Optional third argument `graph` ({initial_step, steps:[{name, functions, valid_steps}]})
   enables full-definition mode: all possible paths drawn dashed, actual transitions solid+numbered. */
(function (global) {
  "use strict";

  // Escapes for BOTH Mermaid label syntax (quotes, newlines) and the innerHTML
  // sinks this renderer writes into (entities) — step names are untrusted text.
  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "'").replace(/[\n\r]/g, " ");
  }

  function triggerLabel(t) {
    if (t === "ai_function") return "AI";
    if (t === "webhook_action") return "&#9889; forced";
    if (t === "gather_complete") return "gather";
    if (t === "auto_advance") return "auto";
    return "step";
  }

  function buildMermaid(sf) {
    var trans = (sf && sf.transitions) || [];
    var lines = ["graph TB"];
    var ids = {}, n = 0;
    function nodeId(step) {
      if (!(step in ids)) { ids[step] = "S" + (n++); lines.push('  ' + ids[step] + '["' + esc(step) + '"]'); }
      return ids[step];
    }
    if (sf && sf.initial_step) nodeId(sf.initial_step);
    trans.forEach(function (t) {
      var a = nodeId(t.from_step || sf.initial_step || "start");
      var b = nodeId(t.to_step || "?");
      lines.push("  " + a + " -->|" + triggerLabel(t.trigger) + "| " + b);
    });
    // style the entry node
    if (sf && sf.initial_step && ids[sf.initial_step]) {
      lines.push("  style " + ids[sf.initial_step] + " fill:#044EF4,color:#fff");
    }
    return lines.join("\n");
  }

  /* Full-definition render: every step + every valid_steps edge (dashed) with
     the call's actual transitions overlaid as solid numbered edges. */
  function buildFullMermaid(sf, graph) {
    var lines = ["graph TB"];
    lines.push("  classDef visited fill:#044EF4,stroke:#0340c5,color:#fff;");
    lines.push("  classDef unvisited fill:#171a26,stroke:#3a3f55,color:#8b93ad;");
    lines.push("  classDef entry fill:#601BE6,stroke:#4a16b8,color:#fff;");
    var ids = {}, n = 0, fnsByStep = {};
    (graph.steps || []).forEach(function (s) { fnsByStep[s.name] = s.functions || []; });
    function nodeId(step) {
      if (!(step in ids)) {
        ids[step] = "S" + (n++);
        var fns = fnsByStep[step];
        var label = esc(step) +
          (fns && fns.length ? "<br/>&#128295; " + fns.map(esc).join(", ") : "");
        lines.push('  ' + ids[step] + '["' + label + '"]');
      }
      return ids[step];
    }
    var trans = (sf && sf.transitions) || [];
    var visited = {}, taken = {};
    if (sf && sf.initial_step) visited[sf.initial_step] = true;
    trans.forEach(function (t, i) {
      var from = t.from_step || (sf && sf.initial_step), to = t.to_step;
      if (!from || !to) return;
      visited[from] = true; visited[to] = true;
      var k = from + " " + to;
      if (!taken[k]) taken[k] = { from: from, to: to, seqs: [], trigger: t.trigger };
      taken[k].seqs.push(i + 1);
    });
    (graph.steps || []).forEach(function (s) { nodeId(s.name); });
    // linkStyle indices follow edge-STATEMENT emission order (node lines don't
    // count): all dashed edges first, then taken edges. Keep that ordering.
    var edgeIdx = 0, takenIdx = [];
    (graph.steps || []).forEach(function (s) {
      (s.valid_steps || []).forEach(function (next) {
        if (taken[s.name + " " + next]) return; // drawn solid below
        lines.push("  " + nodeId(s.name) + " -.-> " + nodeId(next));
        edgeIdx++;
      });
    });
    Object.keys(taken).forEach(function (k) {
      var e = taken[k];
      lines.push('  ' + nodeId(e.from) + ' -->|"' + e.seqs.join(",") + ". " +
        triggerLabel(e.trigger) + '"| ' + nodeId(e.to));
      takenIdx.push(edgeIdx++);
    });
    takenIdx.forEach(function (i) {
      lines.push("  linkStyle " + i + " stroke:#F72A72,stroke-width:2.5px;");
    });
    var vis = [], dim = [];
    Object.keys(ids).forEach(function (step) {
      (visited[step] ? vis : dim).push(ids[step]);
    });
    if (dim.length) lines.push("  class " + dim.join(",") + " unvisited;");
    if (vis.length) lines.push("  class " + vis.join(",") + " visited;");
    var entry = (sf && sf.initial_step) || graph.initial_step;
    if (entry && ids[entry]) lines.push("  class " + ids[entry] + " entry;");
    return lines.join("\n");
  }

  global.renderStateFlow = function (el, sf, graph) {
    if (!el) return;
    var hasGraph = !!(graph && graph.steps && graph.steps.length);
    var trans = (sf && sf.transitions) || [];
    if (!hasGraph && !trans.length) {
      el.innerHTML = '<p class="muted">Buddy ran as a single step — no state-machine transitions were captured for this call.</p>';
      return;
    }
    var code = hasGraph ? buildFullMermaid(sf || {}, graph) : buildMermaid(sf);
    var legend = hasGraph
      ? '<div class="sf-legend">solid pink = path this call took (numbered) · dashed = possible route · dim = not visited</div>'
      : '';
    el.innerHTML = '<div class="mermaid">' + code + '</div>' + legend;
    try {
      if (global.mermaid && global.mermaid.run) {
        global.mermaid.run({ nodes: [el.querySelector(".mermaid")] });
      } else {
        el.innerHTML = '<ul class="sf-fallback">' + trans.map(function (t) {
          return "<li>" + esc(t.from_step) + " &rarr; " + esc(t.to_step) + " (" + esc(t.trigger) + ")</li>";
        }).join("") + "</ul>";
      }
    } catch (e) {
      el.innerHTML = '<pre class="raw">' + esc(code) + "</pre>";
    }
  };
})(window);
