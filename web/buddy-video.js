/* Chicago Roadshow 2026 — "Video call with Buddy" showcase widget.
 *
 * A large, centered modal that places a one-click in-browser VIDEO call to
 * Buddy (the complete AI agent, /step11, which renders a video avatar). Built
 * directly on the raw @signalwire/js browser SDK to show how much you can do
 * with it: live video both ways, a real-time call-state header + timer, mic
 * mute, camera on/off, microphone / camera / speaker device pickers, and a
 * DTMF keypad.
 *
 * Loaded after the @signalwire/js CDN bundle (global `SignalWire`) and reuses
 * the same /api/relay/config endpoint as the audio click-to-call (subscriber
 * token + dialable destination).
 *
 * Resilience: the @signalwire/js call-object surface differs slightly across
 * versions, so every optional capability (mute / device switch / DTMF) is
 * feature-detected and degrades gracefully — a control that the SDK build does
 * not expose is simply disabled rather than throwing.
 *
 * Everything logs with the [buddy-video] prefix for live debugging.
 */
(function () {
  var client = null;
  var call = null;
  var timerId = null;
  var startedAt = 0;
  var micMuted = false;
  var camOff = false;
  var wasActive = false;
  var els = {};        // cached DOM refs (resolved on open)
  var onEndedCb = null; // optional callback fired after a real call ends

  function log() {
    var a = Array.prototype.slice.call(arguments); a.unshift("[buddy-video]");
    console.log.apply(console, a);
  }
  function logErr() {
    var a = Array.prototype.slice.call(arguments); a.unshift("[buddy-video]");
    console.error.apply(console, a);
  }

  // Call the first method on `obj` that exists, from a list of candidates.
  // Returns the (possibly Promise) result, or undefined if none exist.
  function callFirst(obj, names, arg) {
    if (!obj) return undefined;
    for (var i = 0; i < names.length; i++) {
      if (typeof obj[names[i]] === "function") {
        try { return obj[names[i]](arg); }
        catch (e) { logErr(names[i] + " threw:", e); return undefined; }
      }
    }
    return undefined;
  }
  function hasAny(obj, names) {
    if (!obj) return false;
    for (var i = 0; i < names.length; i++) {
      if (typeof obj[names[i]] === "function") return true;
    }
    return false;
  }

  function setState(text, mode) {
    if (els.state) els.state.textContent = text;
    if (els.modal) els.modal.setAttribute("data-call-state", mode || "");
    log("state:", mode, "-", text);
  }

  function fmtElapsed(ms) {
    var s = Math.floor(ms / 1000);
    var m = Math.floor(s / 60);
    s = s % 60;
    return (m < 10 ? "0" : "") + m + ":" + (s < 10 ? "0" : "") + s;
  }
  function startTimer() {
    startedAt = performance.now();
    stopTimer();
    timerId = setInterval(function () {
      if (els.timer) els.timer.textContent = fmtElapsed(performance.now() - startedAt);
    }, 1000);
  }
  function stopTimer() {
    if (timerId) { clearInterval(timerId); timerId = null; }
  }

  /* ---- Device pickers --------------------------------------------------- */
  async function populateDevices() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) return;
    try {
      var devices = await navigator.mediaDevices.enumerateDevices();
      fillSelect(els.micSelect, devices, "audioinput", "Microphone");
      fillSelect(els.camSelect, devices, "videoinput", "Camera");
      fillSelect(els.spkSelect, devices, "audiooutput", "Speaker");
    } catch (e) { logErr("enumerateDevices failed:", e); }
  }
  function fillSelect(sel, devices, kind, label) {
    if (!sel) return;
    var list = devices.filter(function (d) { return d.kind === kind; });
    if (!list.length) { sel.parentElement.style.display = "none"; return; }
    sel.parentElement.style.display = "";
    sel.innerHTML = list.map(function (d, i) {
      return '<option value="' + d.deviceId + '">' +
        (d.label || (label + " " + (i + 1))) + "</option>";
    }).join("");
  }

  /* ---- DTMF keypad ------------------------------------------------------ */
  function buildKeypad() {
    if (!els.keypad || els.keypad.dataset.built) return;
    els.keypad.dataset.built = "1";
    var keys = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "*", "0", "#"];
    els.keypad.innerHTML = keys.map(function (k) {
      return '<button type="button" class="bv-key" data-digit="' + k + '">' + k + "</button>";
    }).join("");
    els.keypad.querySelectorAll(".bv-key").forEach(function (b) {
      b.addEventListener("click", function () { sendDigit(b.dataset.digit); });
    });
  }
  function sendDigit(d) {
    log("DTMF:", d);
    var r = callFirst(call, ["sendDigits", "sendDTMF", "dtmf"], d);
    if (r === undefined) setState("DTMF not supported by this SDK build", "active");
  }

  /* ---- Mute / camera toggles ------------------------------------------- */
  function toggleMic() {
    micMuted = !micMuted;
    callFirst(call, micMuted ? ["audioMute", "muteAudio"] : ["audioUnmute", "unmuteAudio"]);
    if (els.micBtn) {
      els.micBtn.classList.toggle("is-off", micMuted);
      els.micBtn.setAttribute("aria-pressed", String(micMuted));
      els.micBtn.querySelector(".bv-ctrl-label").textContent = micMuted ? "Unmute" : "Mute";
    }
  }
  function toggleCam() {
    camOff = !camOff;
    callFirst(call, camOff ? ["videoMute", "muteVideo"] : ["videoUnmute", "unmuteVideo"]);
    if (els.camBtn) {
      els.camBtn.classList.toggle("is-off", camOff);
      els.camBtn.setAttribute("aria-pressed", String(camOff));
      els.camBtn.querySelector(".bv-ctrl-label").textContent = camOff ? "Camera on" : "Camera off";
    }
    if (els.modal) els.modal.classList.toggle("bv-cam-off", camOff);
  }

  /* ---- Call lifecycle --------------------------------------------------- */
  var CALL_EVENTS = [
    "active", "answered", "ended", "destroy", "error",
    "call.state", "call.joined", "call.left", "call.updated", "media.connected",
  ];

  async function startCall() {
    if (typeof SignalWire === "undefined" || !SignalWire.SignalWire) {
      setState("SDK not loaded yet — try again in a moment.", "error");
      return;
    }
    micMuted = false; camOff = false; wasActive = false;
    try {
      setState("Requesting camera and microphone…", "connecting");
      // WHY video:true here (vs the audio-only click-to-call): this is the full
      // video showcase, so we ask for the camera too.
      await SignalWire.WebRTC.requestPermissions({ audio: true, video: true });

      await populateDevices();   // labels are available once permission is granted

      setState("Minting a fresh token…", "connecting");
      var resp = await fetch("/api/relay/config");
      if (!resp.ok) {
        var err = await resp.json().catch(function () { return {}; });
        setState("Could not get a token: " + (err.error || resp.status), "error");
        return;
      }
      var cfg = await resp.json();
      log("config:", { destination: cfg.destination, token_chars: cfg.token ? cfg.token.length : 0 });

      setState("Connecting to Buddy…", "connecting");
      client = await SignalWire.SignalWire({ token: cfg.token });

      call = await client.dial({
        to: cfg.destination,
        audio: true,
        video: true,
        rootElement: els.stage,   // SDK attaches the remote/avatar video here
        negotiateVideo: true,
      });

      CALL_EVENTS.forEach(function (ev) {
        try { call.on(ev, function (p) { log("event:", ev, p); }); } catch (e) { /* unknown event */ }
      });
      call.on("destroy", onCallEnded);
      call.on("ended", onCallEnded);

      setState("Negotiating media…", "connecting");
      await call.start();
      wasActive = true;
      attachSelfView();
      enableControls(true);
      buildKeypad();
      startTimer();
      setState("In a video call with Buddy", "active");
      if (els.modal) els.modal.classList.add("bv-connected");
    } catch (e) {
      logErr("video call failed:", e);
      setState("Call failed: " + (e && e.message ? e.message : e), "error");
      enableControls(false);
    }
  }

  // Best-effort local self-view: surface the SDK's local stream/track if the
  // build exposes one. No hard dependency — if absent, we just skip it.
  function attachSelfView() {
    if (!els.selfView || !call) return;
    try {
      var stream = call.localStream || call.localVideoStream ||
        (call.localVideoTrack && new MediaStream([call.localVideoTrack]));
      if (stream) {
        els.selfView.srcObject = stream;
        els.selfView.muted = true;
        els.selfView.play().catch(function () {});
        els.selfView.parentElement.style.display = "";
      }
    } catch (e) { log("self-view unavailable:", e && e.message); }
  }

  var ended = false;
  function onCallEnded() {
    if (ended) return;
    ended = true;
    log("call ended");
    stopTimer();
    enableControls(false);
    setState("Call ended.", "ended");
    var hadCall = wasActive;
    call = null;
    if (hadCall && typeof onEndedCb === "function") {
      try { onEndedCb(); } catch (e) { logErr("onEnded threw:", e); }
    }
  }

  function enableControls(on) {
    [els.micBtn, els.camBtn, els.keypad, els.micSelect, els.camSelect, els.spkSelect]
      .forEach(function (el) { if (el) el.toggleAttribute("disabled", !on); });
    // Hide capability controls the SDK build cannot back, so we never present a
    // dead button.
    if (els.micBtn) els.micBtn.style.display = hasAny(call, ["audioMute", "muteAudio"]) || !on ? "" : "none";
    if (els.camBtn) els.camBtn.style.display = hasAny(call, ["videoMute", "muteVideo"]) || !on ? "" : "none";
    if (els.dtmfWrap) els.dtmfWrap.style.display = hasAny(call, ["sendDigits", "sendDTMF", "dtmf"]) || !on ? "" : "none";
  }

  async function hangup() {
    log("hangup()");
    try { if (call) await callFirst(call, ["hangup", "leave"]); }
    catch (e) { logErr("hangup failed:", e); }
  }

  /* ---- Device-switch wiring -------------------------------------------- */
  function wireDeviceSwitch(sel, methods) {
    if (!sel) return;
    sel.addEventListener("change", function () {
      var r = callFirst(call, methods, { deviceId: sel.value });
      if (r && typeof r.then === "function") r.catch(function (e) { logErr("device switch failed:", e); });
    });
  }

  /* ---- Public open / close --------------------------------------------- */
  function resolveEls() {
    els = {
      modal: document.getElementById("buddy-video-modal"),
      stage: document.getElementById("bv-stage"),
      selfView: document.getElementById("bv-selfview"),
      state: document.getElementById("bv-state"),
      timer: document.getElementById("bv-timer"),
      micBtn: document.getElementById("bv-mic"),
      camBtn: document.getElementById("bv-cam"),
      hangupBtn: document.getElementById("bv-hangup"),
      closeBtn: document.getElementById("bv-close"),
      keypad: document.getElementById("bv-keypad"),
      dtmfWrap: document.getElementById("bv-dtmf"),
      micSelect: document.getElementById("bv-mic-select"),
      camSelect: document.getElementById("bv-cam-select"),
      spkSelect: document.getElementById("bv-spk-select"),
    };
  }

  var wired = false;
  function wireOnce() {
    if (wired) return; wired = true;
    if (els.micBtn) els.micBtn.addEventListener("click", toggleMic);
    if (els.camBtn) els.camBtn.addEventListener("click", toggleCam);
    if (els.hangupBtn) els.hangupBtn.addEventListener("click", function () { hangup(); });
    if (els.closeBtn) els.closeBtn.addEventListener("click", close);
    wireDeviceSwitch(els.micSelect, ["updateMicrophone", "setMicrophoneDevice", "setInputDevice"]);
    wireDeviceSwitch(els.camSelect, ["updateCamera", "setCameraDevice"]);
    wireDeviceSwitch(els.spkSelect, ["updateSpeaker", "setSpeakerDevice", "setOutputDevice"]);
    // Close on backdrop click / Escape.
    if (els.modal) {
      els.modal.addEventListener("click", function (e) {
        if (e.target === els.modal) close();
      });
    }
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && els.modal && !els.modal.hidden) close();
    });
  }

  function open(opts) {
    resolveEls();
    if (!els.modal) { logErr("modal markup not found"); return; }
    onEndedCb = opts && opts.onEnded ? opts.onEnded : null;
    wireOnce();
    ended = false;
    els.modal.hidden = false;
    els.modal.setAttribute("aria-hidden", "false");
    document.body.classList.add("bv-open");
    requestAnimationFrame(function () { els.modal.classList.add("is-open"); });
    enableControls(false);
    if (els.timer) els.timer.textContent = "00:00";
    startCall();
  }

  function close() {
    hangup();
    stopTimer();
    if (els.modal) {
      els.modal.classList.remove("is-open", "bv-connected", "bv-cam-off");
      els.modal.hidden = true;
      els.modal.setAttribute("aria-hidden", "true");
    }
    document.body.classList.remove("bv-open");
    if (els.selfView) { try { els.selfView.srcObject = null; } catch (e) {} }
    if (els.stage) els.stage.innerHTML = "";
    client = null;
  }

  window.BuddyVideo = { open: open, close: close };
  console.log("[buddy-video] module loaded");
})();
