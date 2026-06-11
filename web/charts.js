/* The six chart views (latency split into assistant + tool panels, so seven
   canvases) from a charts object. window.renderCharts(el, charts).
   Chart.js v4 UMD must be loaded first (window.Chart); degrades to a notice. */
(function (global) {
  "use strict";
  var instances = [];   // assumes one renderCharts mount per page
  var uid = 0;
  var TICK = "#9aa3b2", GRID = "rgba(255,255,255,0.08)";

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }
  function block(title, id) {
    return '<div class="chart-block"><div class="m-section-title">' + esc(title) +
      '</div><div class="chart-wrap"><canvas id="' + id + '"></canvas></div></div>';
  }
  function emptyBlock(title) {
    return '<div class="chart-block"><div class="m-section-title">' + esc(title) +
      '</div><p class="muted">No data.</p></div>';
  }
  function axes(stacked) {
    return {
      x: { stacked: !!stacked, ticks: { color: TICK }, grid: { color: GRID } },
      y: { stacked: !!stacked, beginAtZero: true, ticks: { color: TICK }, grid: { color: GRID } }
    };
  }
  function opts(stacked) {
    return { responsive: true, maintainAspectRatio: false, scales: axes(stacked),
             plugins: { legend: { labels: { color: TICK } } } };
  }
  function refLinePlugin(lines) {
    return {
      id: "reflines" + (++uid),
      afterDraw: function (chart) {
        var y = chart.scales.y, area = chart.chartArea, ctx = chart.ctx;
        if (!y || !area) return;
        lines.forEach(function (l) {
          if (l.value == null) return;
          var py = y.getPixelForValue(l.value);
          if (py < area.top || py > area.bottom) return;
          ctx.save();
          ctx.strokeStyle = l.color;
          ctx.setLineDash(l.dash);
          ctx.beginPath(); ctx.moveTo(area.left, py); ctx.lineTo(area.right, py); ctx.stroke();
          ctx.setLineDash([]);
          ctx.fillStyle = l.color;
          ctx.font = "10px sans-serif";
          ctx.fillText(l.label + " " + Math.round(l.value), area.left + 4, py - 3);
          ctx.restore();
        });
      }
    };
  }
  function mk(canvasId, cfg, plugins) {
    var c = document.getElementById(canvasId);
    if (!c) return;
    instances.push(new global.Chart(c, {
      type: cfg.type, data: cfg.data, options: cfg.options, plugins: plugins || []
    }));
  }

  function latencyChart(canvasId, rows, stats, withTarget) {
    var alpha = withTarget ? "0.8" : "0.5";
    var lines = [];
    if (stats) {
      lines.push({ value: stats.min, color: "#40E0D0", dash: [3, 3], label: "min" });
      lines.push({ value: stats.avg, color: "#22c55e", dash: [5, 5], label: "avg" });
      if (withTarget) lines.push({ value: 1200, color: "#FFD700", dash: [10, 5], label: "target" });
      lines.push({ value: stats.max, color: "#ef4444", dash: [3, 3], label: "max" });
    }
    mk(canvasId, {
      type: "bar",
      data: {
        labels: rows.map(function (r) { return r.label; }),
        datasets: [
          { label: "LLM", data: rows.map(function (r) { return r.llm; }),
            backgroundColor: "rgba(147,51,234," + alpha + ")", stack: "s" },
          { label: "Utterance", data: rows.map(function (r) { return r.utterance; }),
            backgroundColor: "rgba(251,191,36," + alpha + ")", stack: "s" },
          { label: "Audio", data: rows.map(function (r) { return r.audio; }),
            backgroundColor: "rgba(129,140,248," + alpha + ")", stack: "s" }
        ]
      },
      options: opts(true)
    }, [refLinePlugin(lines)]);
  }

  global.renderCharts = function (el, ch) {
    if (!el) return;
    instances.forEach(function (c) { try { c.destroy(); } catch (e) {} });
    instances = [];
    if (!global.Chart) {
      el.innerHTML = '<p class="muted">Charts unavailable (Chart.js failed to load).</p>';
      return;
    }
    if (!ch) {
      el.innerHTML = '<p class="muted">No chart data for this call.</p>';
      return;
    }
    var p = "ch" + (++uid) + "-";
    var rows = ch.latency_breakdown || [];
    var aRows = rows.filter(function (r) { return r.role === "assistant"; });
    var tRows = rows.filter(function (r) { return r.role === "tool"; });
    var stats = ch.latency_stats || {};
    var tps = ch.tps || [];
    var asr = ch.asr || [];
    var roleKeys = Object.keys(ch.roles || {});
    var sw = ch.swaig_by_command || [];

    var html = "";
    html += aRows.length ? block("Latency Breakdown — Assistant", p + "lat-a") : emptyBlock("Latency Breakdown — Assistant");
    html += tRows.length ? block("Latency Breakdown — Tool Calls", p + "lat-t") : emptyBlock("Latency Breakdown — Tool Calls");
    html += tps.length ? block("Tokens Per Second", p + "tps") : emptyBlock("Tokens Per Second");
    html += asr.length ? block("ASR Confidence per Utterance", p + "asr") : emptyBlock("ASR Confidence per Utterance");
    html += asr.length ? block("Speech Detection Timing", p + "sdt") : emptyBlock("Speech Detection Timing");
    html += roleKeys.length ? block("Message Role Breakdown", p + "roles") : emptyBlock("Message Role Breakdown");
    html += sw.length ? block("SWAIG Latency by Command", p + "swaig") : emptyBlock("SWAIG Latency by Command");
    el.innerHTML = html;

    if (aRows.length) latencyChart(p + "lat-a", aRows, stats.assistant, true);
    if (tRows.length) latencyChart(p + "lat-t", tRows, stats.tool, false);

    if (tps.length) mk(p + "tps", {
      type: "bar",
      data: {
        labels: tps.map(function (t) { return t.label; }),
        datasets: [{ label: "TPS",
          data: tps.map(function (t) { return t.tps; }),
          backgroundColor: tps.map(function (t) {
            if (t.is_tool) return t.tps === 0 ? "rgba(139,92,246,0.5)" : "rgba(245,158,11,0.4)";
            return "rgba(16,185,129,0.6)";
          }) }]
      },
      options: opts(false)
    });

    if (asr.length) mk(p + "asr", {
      type: "bar",
      data: {
        labels: asr.map(function (a) { return a.label; }),
        datasets: [{ label: "Confidence %",
          data: asr.map(function (a) { return a.confidence_pct; }),
          backgroundColor: asr.map(function (a) {
            var v = a.confidence_pct == null ? 0 : a.confidence_pct;
            return v >= 80 ? "rgba(16,185,129,0.7)" : v >= 50 ? "rgba(245,158,11,0.7)" : "rgba(239,68,68,0.7)";
          }) }]
      },
      options: opts(false)
    });

    if (asr.length) mk(p + "sdt", {
      type: "bar",
      data: {
        labels: asr.map(function (a) {
          return a.label + (a.barge ? " *" : "") + (a.merged ? " †" : "");
        }),
        datasets: [
          { label: "Speaking → Turn", stack: "s",
            data: asr.map(function (a) { return a.s2t; }),
            backgroundColor: asr.map(function (a) {
              return a.barge ? "rgba(239,68,68,0.5)" : "rgba(16,185,129,0.6)";
            }) },
          { label: "Turn → Final", stack: "s",
            data: asr.map(function (a) { return a.t2f; }),
            backgroundColor: asr.map(function (a) {
              return a.barge ? "rgba(239,68,68,0.3)" : "rgba(245,158,11,0.6)";
            }) }
        ]
      },
      options: opts(true)
    });

    if (roleKeys.length) mk(p + "roles", {
      type: "doughnut",
      data: {
        labels: roleKeys,
        datasets: [{
          data: roleKeys.map(function (k) { return ch.roles[k]; }),
          backgroundColor: roleKeys.map(function (k) {
            return { system: "#8b5cf6", "system-log": "#6b7280", assistant: "#818cf8",
                     user: "#22c55e", tool: "#FFD700" }[k] || "#9aa3b2";
          })
        }]
      },
      options: { responsive: true, maintainAspectRatio: false,
                 plugins: { legend: { labels: { color: TICK } } } }
    });

    if (sw.length) mk(p + "swaig", {
      type: "bar",
      data: {
        labels: sw.map(function (s) { return s.name; }),
        datasets: [
          { label: "Execution (round-trip)", data: sw.map(function (s) { return s.avg_execution_ms; }),
            backgroundColor: "rgba(245,158,11,0.6)", borderColor: "#FFD700", borderWidth: 1 },
          { label: "Function (remote only)", data: sw.map(function (s) { return s.avg_function_ms; }),
            backgroundColor: "rgba(239,68,68,0.5)", borderColor: "#ef4444", borderWidth: 1 }
        ]
      },
      options: opts(false)
    });
  };
})(window);
