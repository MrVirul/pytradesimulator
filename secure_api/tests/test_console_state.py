"""Poll labels stay in the page when a fragment is not swapped."""

import shutil
import subprocess
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "app" / "web" / "static" / "console.js"
HTMX = Path(__file__).resolve().parents[1] / "app" / "web" / "static" / "htmx.min.js"


def test_vendored_htmx_restores_focus_by_id():
    """Pin the HTMX 2.0.4 behaviour this milestone relies on.

    The swap routine captures ``document.activeElement`` and its selection,
    then looks the same ``id`` up after the swap and focuses it. A real browser
    check lives in ``test_layout_browser.py``; this catches a silent vendored
    upgrade when that browser test is skipped.
    """
    source = HTMX.read_text(encoding="utf-8")
    assert "document.activeElement" in source
    assert "getElementById" in source
    assert "setSelectionRange" in source
    assert ".focus(" in source


def test_poll_labels_and_age():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    program = r"""
const fs = require("fs");
const vm = require("vm");
const context = {
  console,
  setInterval,
  clearInterval,
  document: {
    readyState: "complete",
    body: null,
    addEventListener: function () {},
    querySelectorAll: function () { return []; },
    getElementById: function () { return null; }
  }
};
context.window = context;
context.globalThis = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[1], "utf8"), context);
if (context.pts.pollLabel(204, null).text !== "OK") process.exit(1);
if (context.pts.pollLabel(200, null).text !== "OK") process.exit(2);
const retry = context.pts.pollLabel(429, "9");
if (retry.text !== "RETRY 9s" || retry.retry !== 9) process.exit(3);
if (context.pts.pollLabel(403, null).text !== "DENIED") process.exit(4);
if (context.pts.pollLabel(503, null).text !== "DOWN") process.exit(5);
if (context.pts.formatAge(61) !== "1:01") process.exit(6);
if (context.pts.formatAge(3661) !== "1:01:01") process.exit(7);
if (context.pts.tickClass("price", "10", "11") !== "tick-up") process.exit(8);
if (context.pts.tickClass("price", "11", "10") !== "tick-down") process.exit(9);
if (context.pts.tickClass("qty", "4", "5") !== "tick-chg") process.exit(10);
if (context.pts.tickClass("status", "pending", "running") !== "tick-chg") process.exit(16);
if (context.pts.tickClass("price", "10", "10") !== null) process.exit(11);
if (context.pts.newerCount([8, 2], 7) !== 1) process.exit(12);
if (context.pts.newerCount([4], 4) !== 0) process.exit(13);
if (context.pts.newCaption(2) !== "2 new") process.exit(14);
if (context.pts.newCaption(0) !== "") process.exit(15);
function key(extra) {
  var ctx = {
    key: "", ctrl: false, alt: false, meta: false, typing: false, filter: false,
    dialogOpen: false, dialogId: "", navCount: 3, rowKind: "", rowGroup: "",
    hasPause: true, hasRefresh: true, hasPrev: true, hasNext: true
  };
  Object.keys(extra).forEach(function (name) { ctx[name] = extra[name]; });
  return context.pts.handleKey(ctx);
}
if (key({key: "?", typing: true}).action !== "none") process.exit(20);
if (key({key: "?"}).action !== "open-shortcuts") process.exit(21);
if (key({key: "1"}).action !== "go-nav" || key({key: "1"}).index !== 1) process.exit(22);
if (key({key: "6", navCount: 3}).action !== "none") process.exit(23);
if (key({key: "Escape", dialogOpen: true}).action !== "close-dialog") process.exit(24);
if (key({key: "Escape", typing: true, filter: true}).action !== "clear-filter") process.exit(25);
if (key({key: "p"}).action !== "click") process.exit(26);
if (key({key: "c", rowKind: "audit"}).action !== "copy-request") process.exit(27);
if (key({key: "Enter", rowKind: "scenario"}).action !== "scenario-open") process.exit(28);
if (key({key: "Enter", dialogOpen: true, dialogId: "confirm-run"}).action !== "scenario-confirm") process.exit(29);
if (key({key: "ArrowDown", rowGroup: "books"}).action !== "move-row") process.exit(30);
if (key({key: "/", ctrl: true}).action !== "none") process.exit(31);
if (key({key: "b"}).action !== "none") process.exit(32);
if (key({key: "[", hasPrev: false}).action !== "none") process.exit(33);

function plan(state, after) { return context.pts.focusPlan(state, after); }
const rows = [
  {id: "alert-1", kind: "alerts"},
  {id: "alert-3", kind: "alerts"},
  {id: "alert-4", kind: "alerts"}
];
const same = plan({id: "alert-3", rowKind: "alerts", rowIndex: 1, typing: false}, {ids: ["alert-1", "alert-3", "alert-4"], rows: rows});
if (same.targetId !== "alert-3" || !same.restore || !same.sameId) process.exit(40);
const gone = plan({id: "alert-2", rowKind: "alerts", rowIndex: 1, typing: false}, {ids: ["alert-1", "alert-3", "alert-4"], rows: rows});
if (gone.targetId !== "alert-3" || gone.rowIndex !== 1 || gone.sameId) process.exit(41);
const short = plan({id: "alert-9", rowKind: "alerts", rowIndex: 4, typing: false}, {ids: ["alert-1", "alert-3"], rows: rows.slice(0, 2)});
if (short.targetId !== "alert-3" || short.rowIndex !== 1) process.exit(42);
const empty = plan({id: "alert-9", rowKind: "alerts", rowIndex: 2, typing: false}, {ids: [], rows: []});
if (empty.restore || empty.targetId !== "") process.exit(43);
if (plan(null, {ids: ["alert-1"], rows: rows}).restore) process.exit(44);
const typing = plan({id: "symbol", rowKind: "", rowIndex: -1, typing: true}, {ids: ["symbol"], rows: []});
if (!typing.restore || !typing.typing || typing.targetId !== "symbol") process.exit(45);
if (context.pts.rovingIndex([], "x") !== -1) process.exit(46);
if (context.pts.rovingIndex(["a", "b"], "b") !== 1) process.exit(47);
if (context.pts.rovingIndex(["a", "b"], "x") !== 0) process.exit(48);
"""
    result = subprocess.run(
        [node, "-e", program, str(SCRIPT)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr or result.stdout
