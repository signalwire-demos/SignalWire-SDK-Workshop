/* Call recording playback. window.renderRecording(el, rec) where rec =
   {url, result, start}. WaveSurfer v7 (UMD, window.WaveSurfer) when available;
   degrades to a native <audio> element. */
(function (global) {
  "use strict";
  var ws = null;
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }
  function fmt(t) {
    t = Math.max(0, Math.floor(t || 0));
    return Math.floor(t / 60) + ":" + ("0" + (t % 60)).slice(-2);
  }
  function audioFallback(el, url) {
    el.innerHTML = '<audio controls src="' + esc(url) + '" style="width:100%;"></audio>' +
      '<p class="muted"><a href="' + esc(url) + '" download>Download recording</a></p>';
  }
  global.renderRecording = function (el, rec) {
    if (!el) return;
    if (ws) { try { ws.destroy(); } catch (e) {} ws = null; }
    var url = rec && rec.url;
    // url is payload-controlled (SWMLVars); only http(s) may reach href/src.
    if (url && !/^https?:\/\//i.test(String(url))) url = null;
    if (!url) {
      el.innerHTML = '<p class="muted">No recording. Recordings appear when the agent ' +
        "runs with record_call enabled (the final Complete Agent records calls).</p>";
      return;
    }
    if (!global.WaveSurfer) { audioFallback(el, url); return; }
    el.innerHTML =
      '<div class="rec-legend"><span class="rec-dot rec-user"></span>caller' +
      '<span class="rec-dot rec-asst"></span>assistant</div>' +
      '<div id="rec-wave"></div>' +
      '<div class="rec-controls">' +
        '<button id="rec-play" class="btn" type="button">▶ Play</button>' +
        '<span id="rec-speeds">' +
          [0.75, 1, 1.5, 2].map(function (s) {
            return '<button class="pp-tab' + (s === 1 ? " is-active" : "") +
              '" data-speed="' + s + '" type="button">' + s + "×</button>";
          }).join("") +
        "</span>" +
        '<span id="rec-time" class="muted">0:00 / 0:00</span>' +
        '<a class="muted" href="' + esc(url) + '" download>Download</a>' +
      "</div>";
    try {
      ws = global.WaveSurfer.create({
        container: el.querySelector("#rec-wave"),
        height: 96,
        url: url,
        splitChannels: [
          { waveColor: "rgba(16,185,129,0.5)", progressColor: "rgba(16,185,129,0.8)" },
          { waveColor: "rgba(59,130,246,0.5)", progressColor: "rgba(59,130,246,0.8)" }
        ]
      });
    } catch (e) { audioFallback(el, url); return; }
    var playBtn = el.querySelector("#rec-play");
    var timeEl = el.querySelector("#rec-time");
    playBtn.addEventListener("click", function () { ws.playPause(); });
    ws.on("play", function () { playBtn.textContent = "⏸ Pause"; });
    ws.on("pause", function () { playBtn.textContent = "▶ Play"; });
    ws.on("ready", function () {
      timeEl.textContent = "0:00 / " + fmt(ws.getDuration());
    });
    ws.on("timeupdate", function (t) {
      timeEl.textContent = fmt(t) + " / " + fmt(ws.getDuration());
    });
    ws.on("error", function () {
      try { ws.destroy(); } catch (e) {}
      ws = null;
      audioFallback(el, url);
    });
    Array.prototype.forEach.call(el.querySelectorAll("[data-speed]"), function (b) {
      b.addEventListener("click", function () {
        Array.prototype.forEach.call(el.querySelectorAll("[data-speed]"), function (x) {
          x.classList.toggle("is-active", x === b);
        });
        ws.setPlaybackRate(parseFloat(b.getAttribute("data-speed")));
      });
    });
  };
})(window);
