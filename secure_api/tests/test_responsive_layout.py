"""The shell and the two long tables stay usable at narrower widths."""

from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "app" / "web"


def _rule(css, selector):
    start = css.index(selector + " {")
    end = css.index("}", start)
    return css[start:end]


def test_top_bar_and_filters_wrap():
    css = (WEB / "static" / "app.css").read_text(encoding="utf-8")
    top = _rule(css, ".top")
    assert "min-height: 36px" in top
    assert "height: auto" in top
    assert "flex-wrap: wrap" in top
    assert "flex: 0 0 36px" not in top
    assert "\n  height: 36px;" not in top

    filters = _rule(css, ".filter-bar")
    assert "min-height: 40px" in filters
    assert "height: auto" in filters
    assert "flex-wrap: wrap" in filters
    assert "overflow: visible" in filters
    assert "overflow: hidden" not in filters


def test_tracks_do_not_push_the_page_and_tables_scroll():
    css = (WEB / "static" / "app.css").read_text(encoding="utf-8")
    assert "min-width: 0" in _rule(css, ".overview-rail")
    assert "overflow-x: auto" not in _rule(css, "main")
    assert "min-width: 0" in _rule(css, ".lab-table")
    assert "min-width: 0" in _rule(css, ".lab-side")


def test_narrow_kpi_strip_is_capped():
    css = (WEB / "static" / "app.css").read_text(encoding="utf-8")
    narrow = css.split("@media (max-width: 800px)", 1)[1].split(
        "@media (max-width: 600px)", 1
    )[0]
    assert ".kpi-strip" in narrow
    assert "repeat(3" in narrow
    assert "height: auto" in narrow


def test_alert_and_audit_tables_declare_column_widths():
    alerts = (WEB / "templates" / "alert_rows.html").read_text(encoding="utf-8")
    audit = (WEB / "templates" / "audit_rows.html").read_text(encoding="utf-8")
    alerts_group = alerts.split("<colgroup>", 1)[1].split("</colgroup>", 1)[0]
    audit_group = audit.split("<colgroup>", 1)[1].split("</colgroup>", 1)[0]
    assert alerts_group.count("<col") == 8
    assert audit_group.count("<col") == 9
    assert "table-layout: fixed" in (WEB / "static" / "app.css").read_text(
        encoding="utf-8"
    )
