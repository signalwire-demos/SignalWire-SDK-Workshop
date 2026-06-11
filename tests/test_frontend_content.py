"""Static-content guards for the workshop wizard markup in web/index.html.

These do not start a server; they assert on the shipped HTML/JS source so the
wizard's user-facing copy and key behaviors can't silently regress.
"""
import re
from pathlib import Path

import pytest

INDEX = Path(__file__).resolve().parents[1] / "web" / "index.html"


@pytest.fixture(scope="module")
def html() -> str:
    return INDEX.read_text(encoding="utf-8")


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


def test_browser_call_uses_c2c_widget(html):
    assert "sw-click-to-call" in html
    assert "@signalwire/web-components" in html
    assert "/api/relay/config" in html          # token still minted server-side
    assert "sw-call-ended" in html              # feed + modal handoff wiring
    assert 'id="live-wire"' in html
    assert "/static/live-wire.js" in html
    assert "renderLiveWire" in html


def test_buddy_video_fully_removed(html):
    assert "buddy-video" not in html
    assert "BuddyVideo" not in html
    assert not (pathlib.Path(__file__).resolve().parent.parent / "web" / "buddy-video.js").exists()
    assert "cf-node" not in html                # click-to-reveal diagram gone


def test_presenter_script_banner_removed(html):
    # The 🎤 SAY presenter banner was removed (2026-06-11): no script data,
    # no render block, no CSS class — versions stay.
    version_count = len(re.findall(r'step:\s*"Version \d+"', html))
    assert version_count == 7
    assert "presenterScript" not in html
    assert "presenter-script" not in html
    assert "🎤" not in html


def test_doc_links_are_relative_paths(html):
    # Every STEPS_META docs url must be a relative path (prefixed by DOCS_BASE),
    # never a hardcoded developer.signalwire.com link.
    assert "developer.signalwire.com" not in html
    urls = re.findall(r'url:\s*"(/[^"]+)"', html)
    assert urls, "expected relative doc urls in STEPS_META"


def test_tour_and_hint_dots_removed(html):
    # The 4-callout coachmark tour + pink "?" hint dots were removed (2026-06-11).
    assert "tour.js" not in html
    assert "WorkshopTour" not in html
    assert "sdkworkshop.tourSeen" not in html
    assert "tour-replay" not in html
    assert "hint-dot" not in html
    assert not (pathlib.Path(__file__).resolve().parent.parent / "web" / "tour.js").exists()


def test_call_cta_uses_magenta_accent(html):
    # The call-Buddy banner uses the SAY banner's pink (rgba(247,42,114,…)),
    # not the old blue (rgba(10,132,255,…)).
    m = re.search(r"\.step-call-cta \{[^}]*\}", html)
    assert m, "step-call-cta CSS missing"
    css = m.group(0).replace(" ", "")
    assert "247,42,114" in css
    assert "10,132,255" not in css


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


ADMIN = pathlib.Path(__file__).resolve().parent.parent / "web" / "admin.html"
CHARTS_JS = pathlib.Path(__file__).resolve().parent.parent / "web" / "charts.js"
LIVE_WIRE_JS = pathlib.Path(__file__).resolve().parent.parent / "web" / "live-wire.js"


@pytest.fixture(scope="module")
def admin_html() -> str:
    return ADMIN.read_text(encoding="utf-8")


def test_charts_js_exists_and_exports_renderer():
    src = CHARTS_JS.read_text(encoding="utf-8")
    assert "renderCharts" in src
    assert "latency_breakdown" in src and "swaig_by_command" in src


def test_admin_has_charts_subtab_and_wiring(admin_html):
    assert 'data-sub="charts"' in admin_html
    assert 'id="sv-charts"' in admin_html
    assert "chart.umd.min.js" in admin_html
    assert "/static/charts.js" in admin_html
    assert "renderCharts" in admin_html


def test_index_modal_has_charts_section(html):
    assert 'id="postprompt-charts"' in html
    assert "chart.umd.min.js" in html
    assert "/static/charts.js" in html
    assert "renderCharts" in html


def test_admin_transcript_has_filters_and_badges(admin_html):
    assert 'id="tr-filters"' in admin_html       # filter bar
    assert 'data-trrole="user"' in admin_html    # role chips
    assert 'id="tr-search"' in admin_html        # search box
    assert 'id="tr-rating"' in admin_html        # rating dropdown
    assert "renderTranscriptList" in admin_html  # re-render on filter change
    assert "turn-badges" in admin_html           # badge row class


def test_admin_summary_has_postprompt_three_tabs(admin_html):
    for tab in ('data-pp="raw"', 'data-pp="substituted"', 'data-pp="parsed"'):
        assert tab in admin_html
    assert 'id="pp-tab-body"' in admin_html


JSON_TREE_JS = pathlib.Path(__file__).resolve().parent.parent / "web" / "json-tree.js"


def test_json_tree_module_exists():
    src = JSON_TREE_JS.read_text(encoding="utf-8")
    assert "jsonTreeHtml" in src and "renderJsonTree" in src
    assert "<details" in src        # native collapse/expand


def test_admin_swaig_uses_json_trees(admin_html):
    assert "/static/json-tree.js" in admin_html
    assert "jsonTreeHtml" in admin_html
    assert "post_response" in admin_html      # raw swaig_log surfaced
    assert "swaig-actions" in admin_html      # action[] badges


GLOBAL_DATA_JS = pathlib.Path(__file__).resolve().parent.parent / "web" / "global-data.js"


def test_global_data_module_exists():
    src = GLOBAL_DATA_JS.read_text(encoding="utf-8")
    assert "renderGlobalData" in src and "jsonTreeHtml" in src


def test_admin_has_global_data_subtab(admin_html):
    assert 'data-sub="global-data"' in admin_html
    assert 'id="sv-globaldata"' in admin_html
    assert "/static/global-data.js" in admin_html
    assert "renderGlobalData" in admin_html


RECORDING_JS = pathlib.Path(__file__).resolve().parent.parent / "web" / "recording.js"


def test_recording_module_exists():
    src = RECORDING_JS.read_text(encoding="utf-8")
    assert "renderRecording" in src
    assert "WaveSurfer" in src
    assert "<audio" in src          # graceful fallback


def test_admin_has_recording_subtab(admin_html):
    assert 'data-sub="recording"' in admin_html
    assert 'id="sv-recording"' in admin_html
    assert "wavesurfer" in admin_html        # CDN tag
    assert "/static/recording.js" in admin_html
    assert "renderRecording" in admin_html


def test_no_event_branding_in_user_facing_surfaces():
    """The app is a city-agnostic SDK workshop: no Chicago/Roadshow/meetup
    strings may appear in served web assets. The GitHub repo slug is allowed
    until the repo itself is renamed."""
    import re
    web = pathlib.Path(__file__).resolve().parent.parent / "web"
    banned = re.compile(r"chicago|roadshow|meetup", re.IGNORECASE)
    allowed = "jongray00/Chicago-Roadshow-2026"
    offenders = []
    for f in sorted(web.glob("*.html")) + sorted(web.glob("*.js")):
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if banned.search(line) and allowed not in line:
                offenders.append(f"{f.name}:{n}: {line.strip()[:100]}")
    assert not offenders, "event branding leaked:\n" + "\n".join(offenders)


def test_live_wire_module():
    src = LIVE_WIRE_JS.read_text(encoding="utf-8")
    assert "renderLiveWire" in src
    assert "injectLocal" in src
    assert "/api/live-events" in src
    assert "EventSource" in src


def test_c2c_section_is_static_and_boot_once(html):
    # The #cf-section must be a single static element outside the renderWorkshop
    # template — so re-renders never destroy an active call widget.
    assert '_c2cBooted' in html, "_c2cBooted boot-once flag missing"
    # Exactly one id="cf-section" in the whole file.
    assert html.count('id="cf-section"') == 1, "cf-section must appear exactly once"
    # The static section must carry the hidden attribute in the markup.
    assert '<section class="cf-section" id="cf-section" hidden' in html, \
        "static cf-section must start hidden"
    # The section must NOT appear inside the renderWorkshop template string.
    # Find the renderWorkshop template (between the backtick after app.innerHTML
    # and the closing backtick) and assert cf-section is absent from it.
    import re
    # Locate the renderWorkshop function body
    rw_match = re.search(r'function renderWorkshop\(\)(.*?)^function \w', html,
                         re.DOTALL | re.MULTILINE)
    assert rw_match, "renderWorkshop function not found"
    rw_body = rw_match.group(1)
    assert 'id="cf-section"' not in rw_body, \
        "cf-section must NOT be inside the renderWorkshop template"


def test_live_wire_closes_previous_eventsource():
    src = LIVE_WIRE_JS.read_text(encoding="utf-8")
    assert "es.close()" in src, "renderLiveWire must close the previous EventSource on re-call"


def test_finale_is_static_below_call_section_and_retriggered(html):
    # The grand finale + workshop footer moved out of the re-rendered #app
    # (2026-06-11): static siblings ordered call-section -> finale -> footer,
    # revealed via the browser-call -> post-prompt-modal-close path.
    assert html.count('id="grand-finale"') == 1
    assert html.count('id="workshop-footer"') == 1
    main_end = html.index("</main>")
    assert html.index('id="grand-finale"') > main_end
    assert html.index('id="cf-section"') < html.index('id="grand-finale"')
    assert html.index('id="grand-finale"') < html.index('id="workshop-footer"')
    assert "_browserCallEnded" in html
    # showGrandFinale is invoked somewhere beyond its definition
    assert html.count("showGrandFinale(") >= 2
