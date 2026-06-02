/* Chicago Roadshow 2026 - Step 13 RELAY: in-browser click-to-call.
 *
 * Loaded after the @signalwire/js CDN bundle, which exposes a global
 * SignalWire. The landing page wires the Call and Hang up buttons to
 * RelayCall.start() / RelayCall.hangup(). Audio only: the agent answers and
 * you talk to it in the browser, no phone involved.
 *
 * Every step logs to the browser console with the [relay-client] prefix so
 * the user can see exactly where a call stalls or fails.
 */
(function () {
  var client = null;
  var call = null;
  var wasActive = false;  // true once a call actually connected, so we only
                          // celebrate (refs.onEnded) after a real conversation.

  function log() {
    var args = Array.prototype.slice.call(arguments);
    args.unshift("[relay-client]");
    console.log.apply(console, args);
  }
  function logErr() {
    var args = Array.prototype.slice.call(arguments);
    args.unshift("[relay-client]");
    console.error.apply(console, args);
  }
  function ts() { return performance.now(); }
  function ms(t0) { return ((performance.now() - t0) / 1000).toFixed(2) + "s"; }

  function setStatus(refs, text) {
    log("status:", text);
    if (refs.statusEl) refs.statusEl.textContent = text;
  }

  function showIdle(refs) {
    if (refs.callBtn) refs.callBtn.style.display = "";
    if (refs.hangupBtn) refs.hangupBtn.style.display = "none";
  }
  function showInCall(refs) {
    if (refs.callBtn) refs.callBtn.style.display = "none";
    if (refs.hangupBtn) refs.hangupBtn.style.display = "";
  }

  // Events we attach a logger to. The SDK fires a subset of these depending on
  // call type; registering all is harmless and gives the user full visibility.
  var CALL_EVENTS = [
    "state", "active", "ended", "error",
    "call.state", "call.joined", "call.left", "call.connect", "call.updated",
    "media.connected",
  ];

  var RelayCall = {
    async start(refs) {
      log("start() called");
      if (typeof SignalWire === "undefined" || !SignalWire.SignalWire) {
        logErr("SDK not loaded; typeof SignalWire =", typeof SignalWire);
        setStatus(refs, "SDK not loaded yet. Try again in a moment.");
        return;
      }
      log("SDK present:", {
        signalwire_factory: !!SignalWire.SignalWire,
        webrtc_helpers: !!SignalWire.WebRTC,
      });

      var t0 = ts();
      try {
        // WHY permissions first: browsers block media capture until granted.
        setStatus(refs, "Requesting microphone...");
        var permT = ts();
        await SignalWire.WebRTC.requestPermissions({ audio: true, video: false });
        log("mic permission granted in", ms(permT));

        // WHY fresh token per call: subscriber tokens are short-lived JWTs.
        setStatus(refs, "Fetching token from /api/relay/config...");
        var fetchT = ts();
        log("GET /api/relay/config");
        var resp = await fetch("/api/relay/config");
        log("config response: HTTP", resp.status, "in", ms(fetchT));
        if (!resp.ok) {
          var err = await resp.json().catch(function () { return {}; });
          logErr("config error body:", err);
          setStatus(refs, "Could not get a token: " + (err.error || resp.status));
          return;
        }
        var cfg = await resp.json();
        log("config:", {
          destination: cfg.destination,
          token_chars: cfg.token ? cfg.token.length : 0,
        });

        setStatus(refs, "Creating SignalWire client...");
        var clientT = ts();
        client = await SignalWire.SignalWire({ token: cfg.token });
        log("client created in", ms(clientT));

        setStatus(refs, "Dialing " + cfg.destination + "...");
        var dialT = ts();
        log("client.dial:", { to: cfg.destination, audio: true, video: false });
        call = await client.dial({
          to: cfg.destination,
          audio: true,
          video: false,
          rootElement: refs.rootEl,
        });
        log("dial() returned call session in", ms(dialT));

        // Wire every interesting event so the console shows the lifecycle.
        CALL_EVENTS.forEach(function (ev) {
          try {
            call.on(ev, function (payload) { log("event:", ev, payload); });
          } catch (e) {
            // Some event names may not be registered by the SDK; ignore.
          }
        });
        call.on("destroy", function () {
          log("event: destroy (call torn down)");
          setStatus(refs, "Call ended.");
          call = null;
          showIdle(refs);
          // WHY guard on wasActive: only fire the grand finale after a real
          // connected conversation, not after a failed/aborted dial attempt.
          if (wasActive && typeof refs.onEnded === "function") {
            try { refs.onEnded(); } catch (e) { logErr("onEnded handler threw:", e); }
          }
          wasActive = false;
        });

        setStatus(refs, "Starting media (WebRTC negotiation)...");
        var startT = ts();
        await call.start();
        wasActive = true;  // a real media session is up
        log("call.start() resolved in", ms(startT), "- total from click:", ms(t0));
        setStatus(refs, "In call with Buddy. Say hello!");
        showInCall(refs);
      } catch (e) {
        logErr("call failed after", ms(t0), e);
        setStatus(refs, "Call failed: " + (e && e.message ? e.message : e));
        showIdle(refs);
      }
    },

    async hangup() {
      log("hangup() called");
      try {
        if (call) {
          await call.hangup();
          log("hangup() resolved");
        } else {
          log("hangup() ignored (no active call)");
        }
      } catch (e) {
        logErr("hangup failed:", e);
      }
    },
  };

  window.RelayCall = RelayCall;
  console.log("[relay-client] module loaded");
})();
