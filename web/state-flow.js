/* Reusable State-Flow tree renderer. Turns a state_flow object
   {transitions:[{from_step,to_step,trigger,...}], function_calls:[...], initial_step}
   into a Mermaid flowchart. Dependency: window.mermaid (loaded once by the host page). */
(function (global) {
  "use strict";

  function esc(s) { return String(s == null ? "" : s).replace(/"/g, "'").replace(/[\n\r]/g, " "); }

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

  global.renderStateFlow = function (el, sf) {
    if (!el) return;
    var trans = (sf && sf.transitions) || [];
    if (!trans.length) {
      el.innerHTML = '<p class="muted">Buddy ran as a single step — no state-machine transitions were captured for this call.</p>';
      return;
    }
    var code = buildMermaid(sf);
    el.innerHTML = '<div class="mermaid">' + code + '</div>';
    try {
      if (global.mermaid && global.mermaid.run) {
        global.mermaid.run({ nodes: [el.querySelector(".mermaid")] });
      } else {
        // Fallback: list transitions if Mermaid failed to load.
        el.innerHTML = '<ul class="sf-fallback">' + trans.map(function (t) {
          return "<li>" + esc(t.from_step) + " &rarr; " + esc(t.to_step) + " (" + esc(t.trigger) + ")</li>";
        }).join("") + "</ul>";
      }
    } catch (e) {
      el.innerHTML = '<pre class="raw">' + esc(code) + "</pre>";
    }
  };
})(window);
