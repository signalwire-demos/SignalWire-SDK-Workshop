"""Static-content guards for the workshop wizard markup in web/index.html.

These do not start a server; they assert on the shipped HTML/JS source so the
wizard's user-facing copy and key behaviors can't silently regress.
"""
import re
from pathlib import Path

import pytest

INDEX = Path(__file__).resolve().parents[1] / "web" / "index.html"
BUDDY_VIDEO = Path(__file__).resolve().parents[1] / "web" / "buddy-video.js"


@pytest.fixture(scope="module")
def html() -> str:
    return INDEX.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def buddy_video_js() -> str:
    return BUDDY_VIDEO.read_text(encoding="utf-8")


def test_no_purchase_confirmation_dialog(html):
    # The "are you sure you want to purchase" confirm() is removed: the user
    # always wants the number, so buying is one click.
    assert "This adds a recurring charge" not in html
    assert "Purchase ${formatPhone(payload.phone_number)} on your SignalWire" not in html
    # Only restartWizard()'s confirm() should remain; no purchase confirm reintroduced.
    assert html.count("confirm(") == 1


def test_versions_not_levels(html):
    # All "Level"/"Lv." wording is replaced by spelled-out "Version N".
    assert "Lv." not in html
    assert "Level up your AI agent" not in html
    assert "level Buddy up" not in html
    # Spelled-out versions are present in STEPS_META.
    assert 'step: "Version 1"' in html
    assert 'step: "Version 2"' in html
    assert "Give Buddy a new capability" in html


def test_open_workshop_button_is_emphasized(html):
    # The primary "Open workshop" CTA carries an explicit large-size class so
    # it reads as the obvious next action.
    assert "btn-cta-lg" in html


def test_area_code_no_results_has_recovery(html):
    # The empty-results branch offers a one-click "show any available number"
    # fallback so an unavailable area code is never a dead end.
    assert 'id="wiz-search-any"' in html
    assert "Show any available US number" in html


def test_manual_point_button_removed_and_autopoint_present(html):
    # The manual per-step "Point my phone number here" button is gone...
    assert "Point my phone number here" not in html
    assert "data-aim-route" not in html
    # ...replaced by automatic re-pointing on version selection.
    assert "function autoPointNumber" in html
    assert "/api/setup/route" in html  # still the endpoint we call


def test_persistent_number_badge_and_call_prompts(html):
    # A persistent number badge is rendered in the sticky timeline header.
    assert "function renderPinnedHeader" in html
    assert "running-version-badge" in html
    # Each version carries a curated "call Buddy and ask him" prompt.
    assert "callPrompt:" in html
    assert "Ask Buddy to tell you a joke" in html
    assert "what the weather" in html
    # The per-step dial sub-line is conditional on whether the number is
    # currently pointed at that version, so both phrasings must be present.
    assert "Your number already dials this version." in html
    assert "Selecting this version points your number here." in html


def test_sdk_pinned_to_v4_and_single_call_client(html):
    # The CDN script is pinned to an explicit v4 version (not the floating tag).
    assert "cdn.signalwire.com/@signalwire/js" in html
    assert "@signalwire/js@4.0.0-rc.0" in html  # explicit v4 pin
    # The audio-only relay-client.js is no longer loaded.
    assert "/static/relay-client.js" not in html
    # There is a single browser-call button, not separate call + video buttons.
    assert 'id="relay-call-btn"' not in html
    assert 'id="buddy-call-btn"' in html


def test_call_fabric_diagram_present(html):
    # The "Bonus / two more pillars" framing is gone.
    assert "Bonus 1" not in html
    assert "Bonus 2" not in html
    assert "Two more pillars beyond the AI agent" not in html
    # The interactive pipeline diagram is present with its four nodes.
    assert 'class="cf-pipeline"' in html
    assert 'data-cf-node="browser"' in html
    assert 'data-cf-node="rest"' in html
    assert 'data-cf-node="edge"' in html
    assert 'data-cf-node="buddy"' in html
    assert "function revealCfNode" in html


def test_buddy_video_emits_all_pipeline_stages(buddy_video_js):
    # All four ordered pipeline stages must be emitted so the Call Fabric
    # diagram lights up browser -> rest -> edge -> buddy.
    assert 'emitStage("browser")' in buddy_video_js
    assert 'emitStage("rest")' in buddy_video_js
    # "edge" is emitted via the idempotent emitEdge() helper (on media.connected
    # and as a post-start() fallback), not a bare emitStage("edge") at auth time.
    assert 'emitStage("edge")' in buddy_video_js
    assert "function emitEdge" in buddy_video_js
    assert 'emitStage("buddy")' in buddy_video_js
    # The pipeline must be cleared on call failure AND on call end so a retry
    # never shows stale half-lit nodes (guards Fix A).
    assert "emitStage(null)" in buddy_video_js


def test_set_cf_stage_updates_status_line(html):
    # setCfStage must keep the #cf-status line in sync with the lit pipeline
    # (guards Fix C: the status line is no longer permanently stale).
    assert "function setCfStage" in html
    assert 'getElementById("cf-status")' in html
    assert "Minting a secure token" in html
    assert "Connecting media over WebRTC" in html
    assert "Connected — talking to Buddy." in html


def test_buddy_video_uses_v4_client_api(buddy_video_js):
    # The call client must use the @signalwire/js v4 surface (verified live
    # against 4.0.0-rc.0). v4 has no SignalWire.WebRTC namespace and the factory
    # is a class requiring `new`; permissions use native getUserMedia.
    assert "new SignalWire.SignalWire(" in buddy_video_js
    assert "StaticCredentialProvider" in buddy_video_js
    assert "navigator.mediaDevices.getUserMedia" in buddy_video_js
    # v3-isms that 404/throw on v4 must be gone (only comments may mention them).
    assert "SignalWire.WebRTC.requestPermissions({" not in buddy_video_js
    assert "await SignalWire.SignalWire({ token" not in buddy_video_js
    # v4 dial takes the destination as a positional arg, not a {to:...} object.
    assert "client.dial(cfg.destination," in buddy_video_js


def test_every_version_has_presenter_script(html):
    # STEPS_META has 7 version objects; each must define presenterScript.
    version_count = len(re.findall(r'step:\s*"Version \d+"', html))
    presenter_count = len(re.findall(r'presenterScript:\s*"', html))
    assert version_count == 7
    assert presenter_count == 7


def test_doc_links_are_relative_paths(html):
    # Every STEPS_META docs url must be a relative path (prefixed by DOCS_BASE),
    # never a hardcoded developer.signalwire.com link.
    assert "developer.signalwire.com" not in html
    urls = re.findall(r'url:\s*"(/[^"]+)"', html)
    assert urls, "expected relative doc urls in STEPS_META"


def test_tour_is_wired_with_doc_callout_first(html):
    assert "tour.js" in html
    assert "RoadshowTour" in html
    assert "roadshow.tourSeen" in html  # localStorage gate
    # The explicit requested first callout copy:
    assert "click on the documentation to learn more" in html.lower()
    assert 'id="tour-replay"' in html  # replay button present


def test_postprompt_modal_present(html):
    assert 'id="postprompt-modal"' in html
    assert 'id="open-postprompt"' in html
    assert "/api/postprompt/final" in html
    # handoff into the browser-call section:
    assert 'id="postprompt-next"' in html


def test_postprompt_open_is_delegated(html):
    # #open-postprompt is rendered dynamically inside #app and recreated on every
    # workshop re-render, so a one-time getElementById().addEventListener at load
    # silently misses it. The open trigger MUST be bound via event delegation on a
    # static ancestor (document) so it survives re-renders.
    assert ('closest("#open-postprompt")' in html
            or "closest('#open-postprompt')" in html), \
        "post-prompt open must use document-level delegation, not a load-time direct binding"


def test_status_banners_present(html):
    assert 'id="api-ticker"' in html
    assert 'id="bottom-right-stack"' in html
    assert 'id="api-log"' in html


def test_state_flow_wired_in_modal(html):
    assert "state-flow.js" in html
    assert "mermaid" in html.lower()
    assert 'id="postprompt-stateflow"' in html


def test_postprompt_button_is_prominent(html):
    # The "See what Buddy captured" button is enlarged and ripples/pulses so
    # attendees notice the post-prompt reveal (instead of an auto-overlay).
    assert "pp-cta-pulse" in html  # the ripple/pulse keyframe
    assert "#open-postprompt {" in html  # dedicated enlarge rule


import pathlib
def test_admin_has_state_flow_subtab():
    admin = pathlib.Path("web/admin.html").read_text(encoding="utf-8")
    assert "state-flow.js" in admin
    assert 'data-sub="state-flow"' in admin
    assert 'id="sv-stateflow"' in admin


def test_dashboard_timeline_assets_referenced(html):
    assert "metrics.js" in html and "timeline.js" in html
    assert 'id="postprompt-dashboard"' in html
    assert 'id="postprompt-timeline"' in html


def test_admin_has_dashboard_timeline_subtabs():
    admin = pathlib.Path("web/admin.html").read_text(encoding="utf-8")
    assert "metrics.js" in admin and "timeline.js" in admin
    assert 'data-sub="dashboard"' in admin and 'id="sv-dashboard"' in admin
    assert 'data-sub="timeline"' in admin and 'id="sv-timeline"' in admin


def test_no_local_renderTimeline_shadows_global(html):
    # index.html must NOT declare a top-level `function renderTimeline` — it would
    # overwrite window.renderTimeline (the swimlane renderer from timeline.js) and
    # break the modal Timeline. The progress-UI function is renderStepTimeline.
    assert "function renderTimeline(" not in html
    assert "renderStepTimeline" in html
