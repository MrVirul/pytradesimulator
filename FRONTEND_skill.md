# UI Hardening Prompt (Milestone 10) for the pytradesim operator console

Standalone instructions for the implementation agent. Put this file at `docs/UI_HARDENING_PROMPT.md` and read it together with `docs/UI_MASTER_PROMPT.md`. Where the two disagree, the master prompt's HARD CONSTRAINTS win.

## ROLE

You are fixing correctness, layout, and accessibility bugs in the FastAPI + Jinja2 + HTMX 2.0.4 operator console under `secure_api/app/web/`. Milestone 9 is marked `done`, but its log says a graphical browser was never driven, and that is why these bugs shipped. This phase adds a safety net first, then fixes the bugs in small, tested steps. Do not add features. Do not redesign.

## HARD CONSTRAINTS (carried over, do not violate)

- Stack stays FastAPI + Jinja2 + HTMX 2.0.4 (vendored). No React, no build step, no CDN, no new runtime JS dependency.
- No localStorage, sessionStorage, or IndexedDB.
- Do not touch frozen legacy code: `pytradesim/server.py`, `market_data.py`, `market_client.py`, `client.py`, `pytradesim/modules/*`, `docker/`, `DockerFile`, `tests/`.
- Do not change any route's permission check, CSRF check, or rate-limit budget. Do not add endpoints or data fields. The data list in the master prompt is complete.
- Never describe a stale row as live. Age is measured from `received_at`. Do not hide staleness to make the UI calmer.
- Banned visuals still apply: no blur, gradients, glow, radius above 2px, emoji, low-contrast grey text. Hover, active, and disabled states must use existing tokens only (`--bg-row-hover`, `--text-3`, `--line`, and so on). Do not use `opacity` to fake a disabled state, because it breaks the contrast rule. Use `--text-3` plus a dashed border.
- Motion stays a 150ms background flash only.
- No order-entry, blotter, position, or P&L UI.
- Keep these test strings working: "Status stale", "Spread", "10.0", "no event time", "Paused", "Resume", absence of "every 3s" when paused, "Limit reached, retrying in 9 s", `hx-trigger="every 9s"`, "Missing permission", `<!DOCTYPE html>`. If a markup change truly needs a different assertion, change that test in the same commit and list it in the PROGRESS log.

## PROCESS

1. Open `docs/PROGRESS.md`. Add **Milestone 10 — UI hardening** with the tasks M10.0 to M10.7 below, all `todo`. Follow the file's existing format. If `.claude/skills/progress-tracking` exists locally, follow it. If it does not, copy the style of the M9 entries.
2. For each task: set it to `in-progress` before coding, work on branch `m10/<task-id>-<slug>`, start commit subjects with `[M10.x]`, and add a dated log line saying what changed and exactly how you checked it.
3. Work test-first. For every bug, write the failing test, see it fail, then fix it. Report the failing output in the log.
4. Run `pytest secure_api/tests` after every task. It must stay green. Tests that need `DATABASE_URL` are skipped without it; say in the log how many were skipped.
5. Be honest in the log. If you could not run a real browser, write that sentence. Do not claim a layout fix is verified if only HTML was parsed.

## M10.0 — Safety net (do this first)

Goal: the bugs below must be impossible to reintroduce silently.

**A. Structural HTML test (no browser needed).** Add `secure_api/tests/test_markup_structure.py`. Render every signed-in page and every fragment through the existing `TestClient` and monkeypatch pattern (see `tests/test_layout.py`). Parse with the standard library `html.parser` (do not add dependencies). Assert, for each rendered `<table>`:

- it has a `<caption>`, exactly one `<thead>`, and at least one `<th scope="col">` inside it;
- no `<th>` or `<tr>` is a direct child of `<table>` (only caption, colgroup, thead, tbody, tfoot);
- no tag name in the document contains stray text like `"ead"` after an attribute (a simple check: every attribute name must be a valid name from a known list, or start with `data-`, `aria-`, `hx-`).

Also assert all `id` values in a page are unique, and that every `aria-labelledby` target exists.

The existing "markup scan" test in M9.8 passed while `<th scope="col"ead>` was in 15 places. Look at it, find out why it did not catch this, and make it strict or replace it.

**B. Optional real-browser layout test.** Add `secure_api/tests/test_layout_browser.py` using Playwright for Python, marked so it is skipped when Playwright or a browser is not installed (`pytest.importorskip`). Put the dependency in a new `secure_api/requirements-dev.txt`, not in `requirements.txt`, and do not add it to the Docker image. At widths 1440, 1280, 1024, 900, 800, 600, and 400, for each page, assert:

- `document.documentElement.scrollWidth <= clientWidth` (no page-level horizontal scroll);
- `main` has no horizontal overflow except inside elements that are meant to scroll (`overflow-x: auto`);
- the `.top` bar has no child whose bounding box is outside the bar;
- every `.filter-bar` control is inside the viewport or inside a wrapped second row.

Serve pages from a fixture app with the same mocked contexts as the other tests. If you cannot install a browser in your environment, still commit the test file, mark it skipped, and write that clearly in the log. Do not delete it.

Exit: A passes and is wired into the normal pytest run. A is red against the current templates before M10.1 fixes them.

## M10.1 — Table headers (P0)

`<th scope="col"ead>` should be `<thead>`. There are 15 sites in these files: `base.html` (line 51), `market.html`, `overview_books.html`, `audit_rows.html`, `alert_rows.html`, `scenarios.html` (two), `alert_detail.html`, `login.html`, `book.html`, `security.html` (two), `home.html`, `alerts.html` (two). Do not trust this list. Run `grep -rn 'scope="col"ead' secure_api/app/web/templates` and fix every hit.

Each header must become `<thead><tr> ... </tr></thead>`, with the rows in a `<tbody>`. Check the HTMX fragments too: swapped `<tbody>` or `<table>` pieces must stay valid when swapped alone.

Also in this task: give empty header cells (actions or reset columns in `security.html` and `home.html`) a name with `<span class="sr-only">Actions</span>`. Add the `.sr-only` class to `app.css` if it is missing.

Then check that the `.alert-panel thead th` sticky styling now applies (the header must stay visible while the body scrolls). Fix the CSS only if it does not.

Exit: M10.0-A is green. Every table has a real header.

## M10.2 — Responsive shell and overflow (P0)

Goal: usable at 1024px and 900px. Nothing is unreachable, nothing is clipped.

- `.top` (app.css ~105): replace the fixed `height: 36px` and `flex: 0 0 36px` with `min-height: 36px; height: auto; flex-wrap: wrap`. Keep a single row at wide widths. At narrow widths the nav and user chip may wrap to a second row. The user chip must stay inside the bar.
- `.filter-bar` (app.css ~381): replace `height: 40px; overflow: hidden` with `min-height: 40px; height: auto; flex-wrap: wrap; overflow: visible`, and give controls `flex: 0 0 auto`. Keep the `:focus` ring visible (no clipping). Use a row gap from the spacing tokens.
- `.overview` and the scenario lab grid: both track children need `min-width: 0`. Add it to `.overview-rail` (`.books-panel` already has it). Add `overflow-x: auto` only to table wrappers, never to `main`.
- Security page at 800px and below: the audit filter must keep a usable height and the KPI strip must not take over the page. Make the KPI strip wrap into a grid with a capped height or fewer columns at narrow widths.
- Add a `<colgroup>` with explicit widths to the alerts (8 columns) and audit (9 columns) tables so Time is narrow, and Detail, Request id, and Reason get the space. Keep `table-layout: fixed`.

Exit: M10.0-B passes where a browser exists. Otherwise, write the CSS rules you changed and why in the log, and say the layout was not driven in a browser.

## M10.3 — Focus survives polling (P0)

Problem: polled regions use `hx-swap="outerHTML"`, so the focused row or button is destroyed every 3 to 10 seconds. `moveRow` in `console.js` then resets the roving index to the first row.

Decision: **do not pause polling while focus is inside.** Pausing would make the screen show old data while the shell says "live", which breaks the never-stale-as-live rule. Restore focus instead.

- Give every swapped focusable element a stable `id`: rows (`books-{symbol}`, `alert-{id}`, `audit-{request_id or index}`, `run-{id}`), the Copy buttons, and the Pause/Resume/Refresh links. HTMX 2 restores focus after a swap to an element with the same `id`; verify this in `htmx.min.js` behaviour by test, do not assume.
- In `console.js`, add `htmx:beforeSwap` and `htmx:afterSwap` handlers (scoped to `[data-poll]` regions). Before the swap, remember the focused element's `id` and, for rows, its index. After the swap, if the element is missing (a row left the list), focus the row at the same index, or the last row. Re-apply the roving `tabindex` so exactly one row has `tabindex="0"`: the focused one, or the first if nothing was focused.
- Never steal focus. If focus was outside the polled region before the swap, do nothing.
- Never move the cursor of a text input that is focused.

Tests: a `console.js` unit-style test in the style of `test_console_state.py` if it exists for JS logic; otherwise a markup test that every `[data-row]` and every control inside a `[data-poll]` region has an `id`. State in the log how the real behaviour was checked.

Exit: with keyboard focus on the third alert row, the next 10 s poll leaves focus on the same alert.

## M10.4 — Honest announcements and state (P1)

1. **`aria-live`.** `#poll-state` must not be live and rewritten on every poll. Keep the visible text, remove `aria-live` from it. Add one visually hidden `<span id="poll-announce" role="status" aria-live="polite" class="sr-only">` in `base.html`. In `console.js`, write to it only when the state changes: live to stale, stale to recovering, recovering to live, backoff start, backoff end. Never write timer ticks.
2. **Session label.** Pick one format and keep the unit. The server renders "N min left"; `tickSession()` currently rewrites it to "41:59". Use "N min left" while more than 2 minutes remain, then "m:ss left". Announce through `#poll-announce` only at 2 min, 30 s, and expired. Remove `aria-live` from `#session-left`.
3. **Paused Refresh.** In `book.html`, the Refresh link must carry `?paused=1` when `paused` is true, in both `href` and `hx-get`. Add a test: render the paused fragment and assert the Refresh link contains `paused=1`, while "Paused" and "Resume" are still present and "every 3s" is still absent.
4. **Scenario meter.** The label says remaining ("Budget 3 of 3") but the bar fills with `used / allowed` (`routes.py` ~371). The Overview limit meters are also used-based (green under 70 percent, amber from 70, red at cap). To stay consistent, change the scenario label to **"Used {used} of {allowed} per {window}s"** and keep the fill and tone logic. Make the meter a real element: `role="progressbar"`, `aria-valuemin="0"`, `aria-valuemax="{allowed}"`, `aria-valuenow="{used}"`, and an `aria-label`. Apply the same markup to the Overview and Security limit meters via the shared macro in `macros/ui.html`. Add a test for the label text and the aria values.
5. **Nav current state.** `base.html` uses `path == href`. Use prefix matching: `/ui/alerts/120` marks Alerts, `/ui/market-data/...` marks Market, `/ui/audit` marks Security. `/ui` must match only exactly. Put the logic in `routes.py` or a small Jinja test, not in a long inline expression. Add a test.
6. **Feed state outside Market.** `#feed-state` is only refreshed by the market fragment, so other pages show an old value. Cheapest honest fix: on pages that do not poll the feed, render it as "FIX on (at load)" / "FIX off (at load)" using the same `data-tone`. Do not add a new poll or endpoint.
7. **Poll cell on static pages.** On Audit and Security (no polling), show "static" instead of "—".

## M10.5 — Interaction states and tokens (P1)

In `app.css`:

- Replace `var(--bg-base)` in `.threshold-track` (~438) with `var(--bg-app)`. Search for any other `var(--...)` that is not defined and fix it. Add a small test that parses `app.css` and fails if a `var(--x)` has no definition.
- Add `:hover` for rows (`[data-row]`, `tbody tr`), `.text-button`, buttons, and nav links using `--bg-row-hover`.
- Add `:active` (a 1px inset border change, no movement or scaling).
- Add `:disabled` and `[aria-disabled="true"]`: `--text-3`, dashed border, `cursor: not-allowed`. Remove `cursor: pointer` from disabled controls. Confirm the Run and Confirm buttons in the scenario lab look inert when the budget is 0 or the role is not admin.
- Add `:focus-visible` next to the existing `:focus` rules. Keep the 2px ring. Keep the ring on rows that receive focus from the keyboard.
- Remove the duplicate `.dialog` rule block. Keep one.
- Contrast: every new color pair must meet the same 7:1 on active rows and 4.5:1 elsewhere that M9.1 recorded. Add the new ratios to the log.

## M10.6 — Honest filters, errors, and labels (P1/P2)

1. **Time zone.** `_parse_time` in `services/alerts.py` and `services/audit.py` treats `datetime-local` values as UTC. Do not change this. Label every time input "UTC" in `alerts.html` and `audit_filters.html`, and add `title="Times are UTC"`. Show returned times as UTC too, with the suffix `Z` or "UTC" in the column header.
2. **HTMX errors.** HTMX 2 does not swap 4xx. In `console.js`, handle `htmx:responseError` and `htmx:sendError` for non-poll requests (filters, format forms). Write a short message into a visible `<p role="alert" class="form-error" id="...-error">` next to the form. Reuse the existing wording style: "Limit reached, retrying in 9 s" for 429 (read `Retry-After`), "Missing permission" for 403, "Check the filter values" for 400, "Request failed, try again" otherwise. Clear it on the next success. Do not touch the existing poll backoff path. `tests/test_htmx_errors.py` shows the pattern.
3. **Filter controls.** Add a visible "Clear" link (it must work without JS: a plain `href` to the page with no query) and a short line under the filter bar listing the active filters as text. Do not add chips with colour-only meaning.
4. **Security vs Audit.** `security.html` includes `audit_filters.html`, which posts to `/ui/audit`. Without JS that leaves the page, and with JS it spends the shared audit budget (10 per 60 s). Replace the embedded filter on the Security page with a plain link "Open audit log" (and links for status 403 and 429 using the existing query format). Keep the KPI strip, the limits table, and the polling note. Make sure the strings that `test_security_console.py` asserts still appear, or update the test in the same commit and log it.
5. **Market header labels.** In `book.html`, render bid, ask, spread, last, age, sequence, and FIX as a `<dl>` with small uppercase 11px labels (`--text-2`). Keep "Status live/stale", "Spread", and the `data-age-from` + `<time>` age element. Then fix the stale assertions in `tests/test_market_page.py` (~line 101): the test expects `"s</dd>"`, `"Received"`, and `"Age"`. Make the markup and the test agree, deliberately: if you add a visible "Age" and "Received" label, keep the asserts; otherwise change them. Log the choice.
6. **Ladder side.** Add a text "Bid" / "Ask" label per row (a narrow first column or a prefix in the price cell) so side is not shown by colour and position alone.
7. **Error and empty states.** Limit the error card to about 48ch. Add the request id and one action link, chosen by status: 401 "Sign in again", 403 and 404 "Back to Market", 429 "Back" plus the retry time. Keep "no event time" wording. Empty states say what happens next, for example "No trades yet. The first print will appear here."
8. **Dialog.** Add `aria-labelledby` pointing at the Shortcuts heading id.
9. **Captions.** Where `<h2>` and `<caption>` repeat the same words, make the caption describe the window (for example "Latest 50, newest first") and left-align captions in CSS.

## M10.7 — Evidence

- `pytest secure_api/tests` green. Record passed and skipped counts.
- `docker run --rm pytradesim test` still 22 passed (do not edit anything under `tests/`).
- If a browser is available: run M10.0-B and record the widths tested. Take no screenshots into the repo.
- Record contrast ratios for any new colour pair.
- Repeat the M9.9 sign-in check for `market`, `analyst`, and `admin` if Docker is available; confirm the nav `aria-current` is right on a detail page.
- Say plainly what was not run.

## OUT OF SCOPE (record as ideas in PROGRESS.md, do not build)

- Overview "is anything wrong?" summary (most stale book, books not receiving).
- Making the watchlist its own polled fragment (needs a rate-limit budget decision).
- Writing `feed_status.last_message_at` (already an optional M9.3 item).
- Any change to rate-limit numbers, roles, or API routes.

## FINAL REPORT FORMAT

When all tasks are done, reply with: tasks completed, tests added (names), tests changed (names and why), commands run with pass/fail counts, what was not verified, and any decision you made that this prompt did not cover.
