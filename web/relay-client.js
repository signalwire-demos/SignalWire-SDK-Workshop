/* Chicago Roadshow 2026 - Step 13 RELAY: in-browser click-to-call.
 *
 * Loaded after the @signalwire/js CDN bundle, which exposes a global
 * SignalWire. The landing page wires the Call and Hang up buttons to
 * RelayCall.start() / RelayCall.hangup(). Audio only: the agent answers and
 * you talk to it in the browser, no phone involved.
 */
(function () {
  var client = null;
  var call = null;

  function setStatus(refs, text) {
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

  var RelayCall = {
    async start(refs) {
      if (typeof SignalWire === "undefined" || !SignalWire.SignalWire) {
        setStatus(refs, "SDK not loaded yet. Try again in a moment.");
        return;
      }
      try {
        // WHY permissions first: browsers block media capture until granted.
        setStatus(refs, "Requesting microphone...");
        await SignalWire.WebRTC.requestPermissions({ audio: true, video: false });

        // WHY fresh token per call: subscriber tokens are short-lived JWTs.
        setStatus(refs, "Getting a token...");
        var resp = await fetch("/api/relay/config");
        if (!resp.ok) {
          var err = await resp.json().catch(function () { return {}; });
          setStatus(refs, "Could not get a token: " + (err.error || resp.status));
          return;
        }
        var cfg = await resp.json();

        setStatus(refs, "Connecting...");
        client = await SignalWire.SignalWire({ token: cfg.token });
        call = await client.dial({
          to: cfg.destination,
          audio: true,
          video: false,
          rootElement: refs.rootEl,
        });

        // WHY destroy resets UI: covers remote hangup, errors, and our hangup.
        call.on("destroy", function () {
          setStatus(refs, "Call ended.");
          call = null;
          showIdle(refs);
        });

        await call.start(); // WHY await: media negotiates before we flip UI.
        setStatus(refs, "In call with Buddy. Say hello!");
        showInCall(refs);
      } catch (e) {
        console.error("[relay] call failed", e);
        setStatus(refs, "Call failed: " + (e && e.message ? e.message : e));
        showIdle(refs);
      }
    },

    async hangup() {
      try {
        if (call) await call.hangup();
      } catch (e) {
        console.error("[relay] hangup failed", e);
      }
    },
  };

  window.RelayCall = RelayCall;
})();
