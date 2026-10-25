"""The stylesheet only uses tokens it defines and styles every interaction state."""

import re
from pathlib import Path

import pytest

APP_CSS = Path(__file__).resolve().parents[1] / "app" / "web" / "static" / "app.css"


def _css():
    return APP_CSS.read_text(encoding="utf-8")


def _rule(css, selector):
    start = css.index(selector + " {")
    end = css.index("}", start)
    return css[start:end]


def test_every_custom_property_is_defined():
    css = _css()
    defined = set(re.findall(r"(--[a-z0-9-]+)\s*:", css))
    used = set(re.findall(r"var\(\s*(--[a-z0-9-]+)", css))
    undefined = sorted(used - defined)
    assert not undefined, f"app.css uses undefined custom properties: {undefined}"


def test_threshold_track_uses_the_app_background_token():
    assert "background: var(--bg-app);" in _rule(_css(), ".threshold-track")
    assert "var(--bg-base)" not in _css()


def test_rows_and_controls_have_hover_states():
    css = _css()
    assert "[data-row]:hover" in css
    assert "tbody tr:hover" in css
    assert "a.text-button:hover" in css
    assert ".top nav a:hover" in css
    assert "button:hover" in css
    assert "background: var(--bg-row-hover);" in css


def test_pressed_controls_change_a_one_pixel_inset_border():
    css = _css()
    assert "inset 0 0 0 1px" in css
    assert re.search(r"(?<!text-)transform\s*:", css) is None
    assert "scale(" not in css


def test_focus_visible_keeps_the_two_pixel_ring_on_rows_and_controls():
    css = _css()
    assert "[data-row]:focus-visible" in css
    assert "a:focus-visible" in css
    assert "button:focus-visible" in css
    focus_visible = css.split(":focus-visible", 1)[1].split("}", 1)[0]
    assert "outline: 2px solid var(--focus);" in focus_visible
    assert "outline-offset: 1px;" in focus_visible


def test_disabled_controls_are_inert_without_opacity():
    css = _css()
    assert "button:disabled" in css
    assert '[aria-disabled="true"]' in css
    assert "color: var(--text-3);" in css
    assert "border-style: dashed;" in css
    assert "cursor: not-allowed;" in css
    assert "opacity" not in css
    disabled_rule = css[css.index("button:disabled") :]
    assert "cursor: pointer" not in disabled_rule.split("}", 1)[0]
    assert css.index("button:disabled") > css.index("cursor: pointer")


def test_only_one_dialog_rule_block():
    assert _css().count("\ndialog {") == 1
