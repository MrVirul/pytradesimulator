(function (root) {
  "use strict";

  function pad(value, width) {
    var text = String(value);
    while (text.length < width) text = "0" + text;
    return text;
  }

  function formatAge(seconds) {
    var whole = Math.max(0, Math.floor(Number(seconds) || 0));
    if (whole < 60) return whole + "s";
    if (whole < 3600) return Math.floor(whole / 60) + ":" + pad(whole % 60, 2);
    return (
      Math.floor(whole / 3600) +
      ":" +
      pad(Math.floor((whole % 3600) / 60), 2) +
      ":" +
      pad(whole % 60, 2)
    );
  }

  function formatClock(date) {
    return pad(date.getUTCHours(), 2) + ":" + pad(date.getUTCMinutes(), 2) + ":" + pad(date.getUTCSeconds(), 2);
  }

  function pollLabel(status, retryAfter) {
    var code = Number(status);
    if (code === 204 || (code >= 200 && code < 300)) return { state: "ok", text: "OK" };
    if (code === 429) {
      var wait = Math.max(1, parseInt(retryAfter, 10) || 1);
      return { state: "retry", text: "RETRY " + wait + "s", retry: wait };
    }
    if (code === 403) return { state: "denied", text: "DENIED" };
    if (code >= 500) return { state: "down", text: "DOWN" };
    return null;
  }

  var scrolls = {};
  var retryLeft = 0;
  var retryTimer = null;
  var focusState = null;
  var announceState = "pending";
  var sessionMarks = {};

  function isPollTarget(target) {
    return !!(target && target.hasAttribute && target.hasAttribute("data-poll"));
  }

  function focusSnapshot(scope) {
    var ids = [];
    var rows = [];
    if (!scope || !scope.querySelectorAll) return { ids: ids, rows: rows };
    var nodes = scope.querySelectorAll("[id]");
    for (var i = 0; i < nodes.length; i++) ids.push(nodes[i].id);
    var rowNodes = scope.querySelectorAll("[data-row]");
    for (var r = 0; r < rowNodes.length; r++) {
      rows.push({ id: rowNodes[r].id, kind: rowNodes[r].getAttribute("data-row") });
    }
    return { ids: ids, rows: rows };
  }

  function focusPlan(state, after) {
    var none = { targetId: "", rowKind: "", rowIndex: -1, roving: true, restore: false, sameId: false, typing: false };
    if (!state) return none;
    var ids = (after && after.ids) || [];
    if (state.id && ids.indexOf(state.id) !== -1) {
      return {
        targetId: state.id,
        rowKind: state.rowKind || "",
        rowIndex: state.rowIndex,
        roving: true,
        restore: true,
        sameId: true,
        typing: !!state.typing,
      };
    }
    if (!state.rowKind) return none;
    var rows = [];
    var all = (after && after.rows) || [];
    for (var i = 0; i < all.length; i++) {
      if (all[i].kind === state.rowKind) rows.push(all[i]);
    }
    if (!rows.length) {
      return { targetId: "", rowKind: state.rowKind, rowIndex: -1, roving: true, restore: false, sameId: false, typing: false };
    }
    var index = state.rowIndex;
    if (index < 0 || index >= rows.length) index = rows.length - 1;
    return {
      targetId: rows[index].id,
      rowKind: state.rowKind,
      rowIndex: index,
      roving: true,
      restore: !!rows[index].id,
      sameId: false,
      typing: false,
    };
  }

  function rovingIndex(ids, focusedId) {
    if (!ids || !ids.length) return -1;
    for (var i = 0; i < ids.length; i++) {
      if (ids[i] === focusedId) return i;
    }
    return 0;
  }

  function captureFocus(target) {
    if (!isPollTarget(target) || !target.contains) return null;
    var active = document.activeElement;
    if (!active || active === document.body || !target.contains(active)) return null;
    var row = active.closest ? active.closest("[data-row]") : null;
    var tag = active.tagName ? active.tagName.toLowerCase() : "";
    var typing = tag === "input" || tag === "textarea" || tag === "select";
    var rowIndex = -1;
    if (row) {
      var group = row.parentNode ? row.parentNode.querySelectorAll("[data-row='" + row.getAttribute("data-row") + "']") : [];
      for (var i = 0; i < group.length; i++) {
        if (group[i] === row) rowIndex = i;
      }
    }
    var start = typing && typeof active.selectionStart === "number" ? active.selectionStart : null;
    var end = typing && typeof active.selectionEnd === "number" ? active.selectionEnd : null;
    return {
      id: active.id || "",
      rowKind: row ? row.getAttribute("data-row") : "",
      rowIndex: rowIndex,
      typing: typing,
      selectionStart: start,
      selectionEnd: end,
    };
  }

  function activeRowId(scope) {
    var active = document.activeElement;
    var row = active && active.closest ? active.closest("[data-row]") : null;
    if (row && scope && scope.contains(row)) return row.id;
    return "";
  }

  function applyRoving(scope, focusedId) {
    if (!scope || !scope.querySelectorAll) return;
    var groups = {};
    var rows = scope.querySelectorAll("[data-row]");
    for (var i = 0; i < rows.length; i++) {
      var kind = rows[i].getAttribute("data-row");
      if (!groups[kind]) groups[kind] = [];
      groups[kind].push(rows[i]);
    }
    Object.keys(groups).forEach(function (name) {
      var group = groups[name];
      var ids = group.map(function (row) { return row.id; });
      var keep = rovingIndex(ids, focusedId);
      for (var k = 0; k < group.length; k++) {
        group[k].setAttribute("tabindex", k === keep ? "0" : "-1");
      }
    });
  }

  function restoreFocus(state) {
    if (!state || !state.targetId) return;
    var scope = document.getElementById(state.targetId);
    if (!scope) return;
    var plan = focusPlan(state, focusSnapshot(scope));
    var target = plan.targetId ? document.getElementById(plan.targetId) : null;
    if (plan.restore && target && target.focus && document.activeElement !== target) {
      target.focus({ preventScroll: true });
    }
    if (plan.sameId && plan.typing && target && target === document.activeElement && state.selectionStart !== null && target.setSelectionRange) {
      try {
        target.setSelectionRange(state.selectionStart, state.selectionEnd);
      } catch (error) {
        /* Some input types do not expose a text selection. */
      }
    }
    applyRoving(scope, activeRowId(scope));
  }

  function serverOffset() {
    var raw = document.body && document.body.getAttribute("data-server-now");
    if (!raw) return 0;
    var parsed = Date.parse(raw);
    if (isNaN(parsed)) return 0;
    return parsed - Date.now();
  }

  function announce(text) {
    var node = document.getElementById("poll-announce");
    if (node) node.textContent = text;
  }

  function announcePlan(previous, next, retry) {
    if (!next || previous === next) return "";
    if (next === "retry") {
      var wait = Math.max(1, Number(retry) || 1);
      return "Rate limited. Retrying in " + wait + " seconds.";
    }
    if (next === "denied") return "Polling denied. Missing permission.";
    if (next === "down") return "Polling failed. Showing the last good data.";
    if (next === "paused") return "Polling paused.";
    if (next === "ok" && (previous === "retry" || previous === "down" || previous === "denied")) {
      return "Polling resumed.";
    }
    return "";
  }

  function setPoll(text, tone, state) {
    var cell = document.getElementById("poll-state");
    if (!cell) return;
    cell.textContent = text;
    cell.setAttribute("data-tone", tone);
    if (state) {
      var message = announcePlan(announceState, state, retryLeft);
      if (message) announce(message);
      announceState = state;
    }
  }

  function rememberScroll() {
    var nodes = document.querySelectorAll("[data-keep-scroll]");
    for (var i = 0; i < nodes.length; i++) {
      if (nodes[i].id) scrolls[nodes[i].id] = nodes[i].scrollTop;
    }
  }

  function restoreScroll() {
    var ids = Object.keys(scrolls);
    for (var i = 0; i < ids.length; i++) {
      var el = document.getElementById(ids[i]);
      if (el) el.scrollTop = scrolls[ids[i]];
    }
  }

  function sourceOf(event) {
    var detail = event.detail || {};
    if (detail.requestConfig && detail.requestConfig.elt) return detail.requestConfig.elt;
    if (detail.elt) return detail.elt;
    return null;
  }

  function isPoll(event) {
    var elt = sourceOf(event);
    return !!(elt && elt.hasAttribute && elt.hasAttribute("data-poll"));
  }

  function startBackoff(seconds) {
    retryLeft = seconds;
    document.body.setAttribute("data-backoff", String(retryLeft));
    setPoll("RETRY " + retryLeft + "s", "warn", "retry");
    if (retryTimer) clearInterval(retryTimer);
    retryTimer = setInterval(function () {
      retryLeft -= 1;
      if (retryLeft <= 0) {
        clearInterval(retryTimer);
        retryTimer = null;
        document.body.removeAttribute("data-backoff");
        setPoll("OK " + formatClock(new Date(Date.now() + serverOffset())), "ok", "ok");
        return;
      }
      document.body.setAttribute("data-backoff", String(retryLeft));
      setPoll("RETRY " + retryLeft + "s", "warn", "retry");
    }, 1000);
  }

  function applyStatus(status, retryAfter) {
    var label = pollLabel(status, retryAfter);
    if (!label) return;
    if (label.state === "retry") {
      startBackoff(label.retry);
      return;
    }
    if (label.state === "ok") {
      setPoll("OK " + formatClock(new Date(Date.now() + serverOffset())), "ok", "ok");
      return;
    }
    setPoll(label.text, label.state === "denied" ? "deny" : "down", label.state === "denied" ? "denied" : "down");
  }

  function onResponse(event) {
    if (!isPoll(event)) return;
    var xhr = event.detail && event.detail.xhr;
    if (!xhr) return;
    var retry = xhr.getResponseHeader ? xhr.getResponseHeader("Retry-After") : null;
    applyStatus(xhr.status, retry);
  }

  function noteServerNow() {
    var book = document.getElementById("market-book");
    var raw = book && book.getAttribute("data-server-now");
    if (raw && document.body) document.body.setAttribute("data-server-now", raw);
  }

  function tickClass(kind, before, after) {
    if (before === after) return null;
    if (kind === "qty" || kind === "status") return "tick-chg";
    var left = Number(before);
    var right = Number(after);
    if (isNaN(left) || isNaN(right) || left === right) return null;
    return right > left ? "tick-up" : "tick-down";
  }

  function snapshotKeys(root) {
    var map = {};
    if (!root || !root.querySelectorAll) return map;
    var nodes = root.querySelectorAll("[data-k]");
    for (var i = 0; i < nodes.length; i++) {
      map[nodes[i].getAttribute("data-k")] = nodes[i].getAttribute("data-v");
    }
    return map;
  }

  function maxRowId(root) {
    var max = null;
    if (!root || !root.querySelectorAll) return max;
    var nodes = root.querySelectorAll("[data-id]");
    for (var i = 0; i < nodes.length; i++) {
      var value = Number(nodes[i].getAttribute("data-id"));
      if (!isNaN(value) && (max === null || value > max)) max = value;
    }
    return max;
  }

  function flash(el, className) {
    el.classList.add(className);
    setTimeout(function () {
      el.classList.add("tick-fade");
      el.classList.remove(className);
      setTimeout(function () { el.classList.remove("tick-fade"); }, 300);
    }, 150);
  }

  function applyTicks(previous) {
    if (!previous) return;
    var reduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    var nodes = document.querySelectorAll("[data-k]");
    for (var i = 0; i < nodes.length; i++) {
      var key = nodes[i].getAttribute("data-k");
      if (!Object.prototype.hasOwnProperty.call(previous.keys, key)) continue;
      var className = tickClass(nodes[i].getAttribute("data-kind"), previous.keys[key], nodes[i].getAttribute("data-v"));
      if (!className) continue;
      if (reduced && className !== "tick-chg") {
        var mark = document.createElement("span");
        mark.className = "tick-mark";
        mark.textContent = className === "tick-up" ? " ▲" : " ▼";
        nodes[i].appendChild(mark);
        setTimeout(function (node) {
          if (node.parentNode) node.parentNode.removeChild(node);
        }, 3000, mark);
        continue;
      }
      if (!reduced) flash(nodes[i], className);
    }
    if (previous.targetId !== "market-book" && previous.targetId !== "alert-rows") return;
    var rows = document.querySelectorAll("#" + previous.targetId + " [data-id]");
    var fresh = newerCount(rows, previous.maxId);
    for (var r = 0; r < rows.length; r++) {
      if (!fresh.flags[r]) continue;
      if (reduced) rows[r].classList.add("row-new");
      else flash(rows[r], "row-new");
    }
    if (previous.targetId === "alert-rows") {
      var caption = document.getElementById("alerts-new");
      if (caption) caption.textContent = newCaption(fresh.count);
    }
  }

  function newerCount(rows, maxId) {
    var flags = [];
    var count = 0;
    for (var r = 0; r < rows.length; r++) {
      var id = Number(rows[r].getAttribute ? rows[r].getAttribute("data-id") : rows[r]);
      var newer = !isNaN(id) && (maxId === null || id > maxId);
      flags.push(newer);
      if (newer) count += 1;
    }
    return { flags: flags, count: count };
  }

  function newCaption(count) {
    return count > 0 ? count + " new" : "";
  }

  function tickAges() {
    noteServerNow();
    var nodes = document.querySelectorAll("[data-age-from]");
    var now = Date.now() + serverOffset();
    for (var i = 0; i < nodes.length; i++) {
      var from = Date.parse(nodes[i].getAttribute("data-age-from"));
      if (isNaN(from)) continue;
      nodes[i].textContent = formatAge(Math.floor((now - from) / 1000));
    }
  }

  function sessionLabel(left) {
    if (left > 120) return Math.floor(left / 60) + " min left";
    return Math.floor(left / 60) + ":" + pad(left % 60, 2) + " left";
  }

  function tickSession() {
    var node = document.getElementById("session-left");
    if (!node) return;
    var expires = Date.parse(node.getAttribute("data-expires") || "");
    if (isNaN(expires)) return;
    var left = Math.floor((expires - (Date.now() + serverOffset())) / 1000);
    if (left < 0) left = 0;
    node.textContent = sessionLabel(left);
    if (left <= 120) node.setAttribute("data-tone", "warn");
    else node.removeAttribute("data-tone");
    if (left <= 120 && !sessionMarks["2m"]) {
      announce("Session expires in 2 minutes.");
      sessionMarks["2m"] = true;
    }
    if (left <= 30 && !sessionMarks["30s"]) {
      announce("Session expires in 30 seconds.");
      sessionMarks["30s"] = true;
    }
    if (left <= 0 && !sessionMarks["expired"]) {
      announce("Session expired.");
      sessionMarks["expired"] = true;
    }
  }

  function handleKey(ctx) {
    if (ctx.ctrl || ctx.alt || ctx.meta) return { action: "none" };
    if (ctx.key === "Escape") {
      if (ctx.dialogOpen) return { action: "close-dialog" };
      if (ctx.typing && ctx.filter) return { action: "clear-filter" };
      return { action: "none" };
    }
    if (ctx.typing) return { action: "none" };
    if (ctx.dialogOpen) {
      if (ctx.dialogId === "confirm-run" && ctx.key === "Enter") return { action: "scenario-confirm" };
      return { action: "none" };
    }
    if (ctx.key === "?") return { action: "open-shortcuts" };
    if (ctx.key === "1" || ctx.key === "2" || ctx.key === "3" || ctx.key === "4" || ctx.key === "5") {
      var index = Number(ctx.key);
      if (index <= ctx.navCount) return { action: "go-nav", index: index };
      return { action: "none" };
    }
    if (ctx.key === "/") return { action: "focus-primary" };
    if (ctx.key === "p" && ctx.hasPause) return { action: "click", key: "pause" };
    if (ctx.key === "r" && ctx.hasRefresh) return { action: "click", key: "refresh" };
    if (ctx.key === "[" && ctx.hasPrev) return { action: "click", key: "prev" };
    if (ctx.key === "]" && ctx.hasNext) return { action: "click", key: "next" };
    if (ctx.key === "ArrowUp" || ctx.key === "ArrowDown") {
      var kind = ctx.rowKind || ctx.rowGroup;
      if (!kind) return { action: "none" };
      return { action: "move-row", kind: kind, delta: ctx.key === "ArrowDown" ? 1 : -1 };
    }
    if (ctx.key === "Enter" && ctx.rowKind === "scenario") return { action: "scenario-open" };
    if (ctx.key === "Enter" && ctx.rowKind) return { action: "row-open" };
    if (ctx.key === "c" && ctx.rowKind === "audit") return { action: "copy-request" };
    return { action: "none" };
  }

  function keyContext(event) {
    var active = document.activeElement;
    var tag = active && active.tagName ? active.tagName.toLowerCase() : "";
    var typing = tag === "input" || tag === "select" || tag === "textarea";
    var filter = false;
    if (active && active.closest) {
      filter = !!(active.closest("#alert-filters") || active.closest("#audit-filters") || (active.hasAttribute && active.hasAttribute("data-primary")));
    }
    var dialog = document.querySelector("dialog[open]");
    var row = active && active.closest ? active.closest("[data-row]") : null;
    var first = document.querySelector("[data-row]");
    return {
      key: event.key,
      ctrl: !!event.ctrlKey,
      alt: !!event.altKey,
      meta: !!event.metaKey,
      typing: typing,
      filter: filter,
      dialogOpen: !!dialog,
      dialogId: dialog ? dialog.id : "",
      navCount: document.querySelectorAll("[data-nav]").length,
      rowKind: row ? row.getAttribute("data-row") : "",
      rowGroup: first ? first.getAttribute("data-row") : "",
      hasPause: !!document.querySelector("[data-key='pause']"),
      hasRefresh: !!document.querySelector("[data-key='refresh']"),
      hasPrev: !!document.querySelector("[data-key='prev']"),
      hasNext: !!document.querySelector("[data-key='next']"),
    };
  }

  function moveRow(kind, delta) {
    var rows = document.querySelectorAll("[data-row='" + kind + "']");
    if (!rows.length) return;
    var focused = false;
    var index = 0;
    for (var i = 0; i < rows.length; i++) {
      if (rows[i] === document.activeElement || rows[i].contains(document.activeElement)) {
        index = i + delta;
        focused = true;
        break;
      }
    }
    if (!focused) index = delta < 0 ? rows.length - 1 : 0;
    if (index < 0) index = 0;
    if (index >= rows.length) index = rows.length - 1;
    for (var k = 0; k < rows.length; k++) rows[k].setAttribute("tabindex", k === index ? "0" : "-1");
    if (rows[index].focus) rows[index].focus();
  }

  function applyKey(decision, event) {
    if (!decision || decision.action === "none") return;
    if (decision.action === "open-shortcuts") {
      var sheet = document.getElementById("shortcuts");
      if (sheet && sheet.showModal && !sheet.open) sheet.showModal();
    } else if (decision.action === "close-dialog") {
      var open = document.querySelector("dialog[open]");
      if (open && open.close) open.close();
    } else if (decision.action === "clear-filter") {
      var field = document.activeElement;
      if (field) {
        field.value = "";
        if (field.blur) field.blur();
      }
    } else if (decision.action === "go-nav") {
      var link = document.querySelector("[data-nav='" + decision.index + "']");
      if (link) window.location.assign(link.getAttribute("href"));
    } else if (decision.action === "focus-primary") {
      var primary = document.querySelector("[data-primary]");
      if (primary && primary.focus) primary.focus();
    } else if (decision.action === "click") {
      var control = document.querySelector("[data-key='" + decision.key + "']");
      if (control && control.click) control.click();
    } else if (decision.action === "move-row") {
      moveRow(decision.kind, decision.delta);
    } else if (decision.action === "row-open") {
      var current = document.activeElement && document.activeElement.closest ? document.activeElement.closest("[data-row]") : null;
      var target = current && current.querySelector ? current.querySelector("a[href]") : null;
      if (target) window.location.assign(target.getAttribute("href"));
    } else if (decision.action === "scenario-open") {
      var scenarioRow = document.activeElement && document.activeElement.closest ? document.activeElement.closest("[data-row='scenario']") : null;
      var form = scenarioRow && scenarioRow.querySelector ? scenarioRow.querySelector("[data-run-form]") : null;
      var button = form && form.querySelector ? form.querySelector("button[type=submit]") : null;
      if (form && (!button || !button.disabled)) openRunDialog(form);
    } else if (decision.action === "scenario-confirm") {
      var confirm = document.getElementById("confirm-form");
      if (confirm && confirm.requestSubmit) confirm.requestSubmit();
    } else if (decision.action === "copy-request") {
      var auditRow = document.activeElement && document.activeElement.closest ? document.activeElement.closest("[data-row='audit']") : null;
      var copy = auditRow && auditRow.querySelector ? auditRow.querySelector("[data-copy]") : null;
      if (copy && copy.click) copy.click();
    } else {
      return;
    }
    if (event.preventDefault) event.preventDefault();
  }

  function showPaused() {
    if (!document.body || document.body.hasAttribute("data-backoff")) return;
    if (document.querySelector("[data-paused='1']")) setPoll("PAUSED", "warn", "paused");
  }

  var tickState = null;

  function orderLines(form) {
    var row = form.closest ? form.closest("tr") : null;
    var cell = row ? row.querySelector(".orders") : null;
    if (!cell) return "No order";
    var lines = cell.querySelectorAll(".mono");
    if (!lines.length) return "No order";
    var parts = [];
    for (var i = 0; i < lines.length; i++) parts.push(lines[i].textContent);
    return parts.join("\n");
  }

  function openRunDialog(form) {
    var dialog = document.getElementById("confirm-run");
    if (!dialog || !dialog.showModal) return false;
    var field = form.querySelector("[name=scenario]");
    var button = form.querySelector("button[type=submit]");
    var name = field ? field.value : "";
    var symbol = button ? (button.getAttribute("data-symbol") || "") : "";
    var nameNode = document.getElementById("confirm-name");
    var symbolNode = document.getElementById("confirm-symbol");
    var orderNode = document.getElementById("confirm-orders");
    var hidden = document.getElementById("confirm-scenario");
    if (nameNode) nameNode.textContent = name;
    if (symbolNode) symbolNode.textContent = symbol;
    if (orderNode) orderNode.textContent = orderLines(form);
    if (hidden) hidden.value = name;
    if (!dialog.open) dialog.showModal();
    return true;
  }

  function start() {
    if (!document.body) return;
    document.body.addEventListener("submit", function (event) {
      var form = event.target;
      if (!form || !form.hasAttribute) return;
      if (form.hasAttribute("data-run-form")) {
        if (openRunDialog(form)) event.preventDefault();
        return;
      }
      if (form.id !== "confirm-form") return;
      var submit = form.querySelector("button[type=submit]");
      if (!submit || submit.disabled) return;
      submit.disabled = true;
      submit.textContent = "Submitting…";
    });
    document.body.addEventListener("keydown", function (event) {
      applyKey(handleKey(keyContext(event)), event);
    });
    document.body.addEventListener("click", function (event) {
      var opener = event.target && event.target.closest ? event.target.closest("#shortcut-open") : null;
      if (opener) {
        var sheet = document.getElementById("shortcuts");
        if (sheet && sheet.showModal && !sheet.open) sheet.showModal();
        return;
      }
      var closer = event.target && event.target.closest ? event.target.closest("[data-close-dialog]") : null;
      if (closer) {
        var dialog = closer.closest("dialog");
        if (dialog && dialog.close) dialog.close();
        return;
      }
      var button = event.target && event.target.closest ? event.target.closest("[data-copy]") : null;
      if (!button) return;
      var value = button.getAttribute("data-copy") || "";
      if (!navigator.clipboard || !navigator.clipboard.writeText) return;
      navigator.clipboard.writeText(value).then(function () {
        button.textContent = "Copied";
      }, function () {});
    });
    document.body.addEventListener("htmx:beforeSwap", function (event) {
      rememberScroll();
      onResponse(event);
      var detail = event.detail || {};
      focusState = detail.shouldSwap ? captureFocus(detail.target) : null;
      if (detail.shouldSwap && detail.target) {
        tickState = {
          keys: snapshotKeys(detail.target),
          maxId: maxRowId(detail.target),
          targetId: detail.target.id || "",
          armed: true,
        };
      } else {
        tickState = null;
      }
    });
    document.body.addEventListener("htmx:afterSwap", function () {
      restoreScroll();
      restoreFocus(focusState);
      focusState = null;
    });
    document.body.addEventListener("htmx:afterSettle", function () {
      var pending = tickState;
      tickState = null;
      applyTicks(pending);
      // Out-of-band watch rows are swapped outside the polled target. Apply
      // the roving tabindex across the page so exactly one row per group has
      // tabindex="0" after every swap.
      applyRoving(document, activeRowId(document));
    });
    document.body.addEventListener("htmx:sendError", function (event) {
      if (isPoll(event)) setPoll("DOWN", "down", "down");
    });
    setInterval(function () {
      tickAges();
      tickSession();
      showPaused();
    }, 1000);
    showPaused();
  }

  root.pts = {
    formatAge: formatAge,
    formatClock: formatClock,
    pollLabel: pollLabel,
    tickClass: tickClass,
    newerCount: function (ids, maxId) {
      var rows = ids.map(function (id) {
        return { getAttribute: function () { return String(id); } };
      });
      return newerCount(rows, maxId).count;
    },
    newCaption: newCaption,
    handleKey: handleKey,
    focusPlan: focusPlan,
    rovingIndex: rovingIndex,
    sessionLabel: sessionLabel,
    announcePlan: announcePlan,
    start: start,
  };

  if (typeof document !== "undefined" && document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else if (typeof document !== "undefined") {
    start();
  }
})(typeof window !== "undefined" ? window : globalThis);
