# tests/test_postprompt_modal_ui.py
"""Content assertions for the post-prompt modal tab UI in web/index.html."""
import pathlib

HTML = pathlib.Path(__file__).resolve().parents[1].joinpath(
    "web", "index.html").read_text(encoding="utf-8")


def test_step_card_call_buddy_button_removed():
    # The blue final-step anchor is gone...
    assert "Call Buddy from your browser ↓" not in HTML
    assert 'href="#cf-section" class="btn-primary"' not in HTML


def test_modal_footer_next_button_survives():
    # ...but the modal-footer path to the browser-call section stays.
    assert "Next: call Buddy from your browser" in HTML


def test_modal_has_five_tabs_and_panes():
    for name in ("summary", "stateflow", "timeline", "dashboard", "charts"):
        assert f'data-pp-tab="{name}"' in HTML, f"missing tab {name}"
        assert f'data-pp-pane="{name}"' in HTML, f"missing pane {name}"


def test_panes_keep_existing_ids():
    # Render targets keep their ids so admin-shared renderers + wiring work.
    for pid in ("postprompt-body", "postprompt-stateflow", "postprompt-dashboard",
                "postprompt-timeline", "postprompt-charts"):
        assert f'id="{pid}"' in HTML, f"missing #{pid}"


def test_modal_lazy_renders_on_tab_activation():
    # Wiring contract: a renderPane/activateTab pair drives lazy rendering.
    assert "activateTab(" in HTML
    assert "renderPane(" in HTML
