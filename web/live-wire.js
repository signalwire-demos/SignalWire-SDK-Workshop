/* Live Wire — real-time feed of browser/AI/SWAIG events for the browser-call
   section. window.renderLiveWire(el) mounts it; window.LiveWire.injectLocal(
   type, summary) adds browser-side (widget) events locally. */
(function (global) {
  "use strict";
  var listEl = null, seen = {}, count = 0, MAX_ROWS = 200;
  var es = null;
  var SOURCES = {
    browser: { icon: "🌐", cls: "lw-browser", label: "Browser" },
    ai: { icon: "🤖", cls: "lw-ai", label: "AI kernel" },
    swaig: { icon: "⚡", cls: "lw-swaig", label: "Server tool" }
  };
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }
  function fmtTime(ts) {
    var d = ts ? new Date(ts * 1000) : new Date();
    return d.toLocaleTimeString([], { hour12: false }) ;
  }
  function row(source, type, summary, ts) {
    if (!listEl) return;
    var s = SOURCES[source] || SOURCES.swaig;
    var empty = listEl.querySelector(".lw-empty");
    if (empty) empty.remove();
    var div = document.createElement("div");
    div.className = "lw-row " + s.cls;
    div.innerHTML = '<span class="lw-time">' + esc(fmtTime(ts)) + "</span>" +
      '<span class="lw-src">' + s.icon + " " + esc(s.label) + "</span>" +
      '<span class="lw-msg">' + esc(summary || type) + "</span>";
    listEl.appendChild(div);
    count++;
    while (count > MAX_ROWS && listEl.firstChild) {
      listEl.removeChild(listEl.firstChild);
      count--;
    }
    listEl.scrollTop = listEl.scrollHeight;
  }
  global.LiveWire = {
    injectLocal: function (type, summary) { row("browser", type, summary); }
  };
  global.renderLiveWire = function (el) {
    if (!el) return;
    /* Close any existing SSE connection and reset feed state before rebuilding. */
    if (es) { es.close(); es = null; }
    seen = {};
    count = 0;
    el.innerHTML = '<div class="lw-head">LIVE WIRE <span class="lw-sub">one call · three views</span></div>' +
      '<div class="lw-list"><p class="muted lw-empty">Place a call — this panel lights up with everything the SDK sees.</p></div>';
    listEl = el.querySelector(".lw-list");
    if (!global.EventSource) {
      listEl.innerHTML = '<p class="muted">Live events unavailable in this browser.</p>';
      return;
    }
    es = new EventSource("/api/live-events");
    es.addEventListener("live", function (ev) {
      var evs = [];
      try { evs = JSON.parse(ev.data) || []; } catch (e) { return; }
      evs.forEach(function (e) {
        if (!e || seen[e.seq]) return;
        seen[e.seq] = 1;
        row(e.source, e.type, e.summary, e.ts);
      });
    });
  };
})(window);
