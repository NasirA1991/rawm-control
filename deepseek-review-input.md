# RAWM Control — review handoff for an external LLM (DeepSeek)

> **How to use this file:** paste this whole document into the chat as one message.
> It is self-contained: an LLM with **no access to the repository** can verify the
> claimed bugs from the included code snippets and give a second opinion. For a
> deeper pass, also attach: `rawm_control/protocol.py`, `rawm_control/worker.py`,
> `rawm_control/app.py`, `rawm_control/ui.py`, `rawm_control/tray.py`.

---

## Instructions for the reviewer

You are doing a second-opinion code + UX review of a small open-source Linux desktop app.
The findings below were produced by a first review pass. Your job:

1. Verify or refute each claimed bug (snippets are included — check the reasoning).
2. Argue priorities: what would you fix first and why?
3. Flag anything the first pass likely missed, given the architecture description.
4. Sanity-check the UI/tray proposals for practicality (GTK4/libadwaita + DBus SNI constraints).

Be specific and technical. If a claim is wrong, say why.

---

## 1. Project context

**RAWM Control** — native GTK4/libadwaita configuration app for RAWM gaming mice on Linux.
Talks to a 64-byte vendor HID collection (usage page 0xFF00) recovered by
reverse-engineering the vendor's WebHID web driver. Hardware-verified only on the
ER21Pro (`1915:2338`) direct link and via the RAWM HS Receiver (`1915:232b`).
MIT licensed, no telemetry, AI-assisted development (disclosed in README).

- Language: Python 3.10+, PyGObject/GTK4/libadwaita, pycairo, python-dbus (tray implemented directly on DBus SNI + DBusMenu, no appindicator bindings).
- ~6,500 lines total. Key modules:
  - `protocol.py` (819) — framing, CRC16, query JSON parsing, param-block encoder, hidraw transport, discovery.
  - `worker.py` (589) — `DeviceWorker` thread owning the fd: rebase→validate→write→confirm-verify lifecycle; `DemoWorker` for `--demo`.
  - `ui.py` (1030) — MainWindow, four Adw.PreferencesPage tabs (Device/Performance/DPI/Lighting).
  - `tray.py` (743) — StatusNotifierItem + DBusMenu on raw dbus-python, cairo-rendered tray pixmaps.
  - `app.py` (436) — Adw.Application wiring, actions, notifications, arg dispatch.
  - `cli.py` (379) — `rawmctl` CLI (status/scan/caps/report + setters with read-back verification).
  - `devices.py` + `data/devices.json` — per-model capability DB (34 entries).
  - `diagnostics.py` — local, redacted device reports for GitHub issues.
- Tests: 51 unit tests (unittest), incl. protocol framing/CRC vectors, worker lifecycle regressions, privacy/redaction tests; opt-in hardware tests (`RAWM_HW_TEST=1`). All pass.
- Packaging: AUR (stable sha-pinned tarball + -git), Flatpak (GNOME 50 runtime), AppImage (host GTK, checksum-pinned appimagetool), source `install.sh`. GitHub Actions: CI, release, edge builds, AUR publish.

---

## 2. Confirmed bugs (with evidence)

### B1 — `DemoWorker.stop()` raises AttributeError; quitting `--demo` is broken
`worker.py` (DemoWorker defines only `_started` and `_stop`; there is no `_wake`):
```python
def stop(self, timeout: float = 2.0) -> None:
    self._stop.set()
    self._wake.set()          # AttributeError: DemoWorker has no attribute _wake
```
`app.py` `_quit()` calls `worker.stop()` **before** `release()`/`quit()`, so the exception
aborts the quit sequence → Quit (tray menu / Ctrl+Q) leaves a `--demo` instance running.
`_stop` is never read anywhere in DemoWorker (no thread). Fix: make `stop()` a no-op or remove it.

### B2 — `_activated_once` reset on every state update; relaunching while hidden does nothing
`app.py`:
```python
def _on_activate(self, _app) -> None:
    self._ensure_window()
    first = not self._activated_once
    self._activated_once = True
    # A first launch with --tray (or "start hidden") stays in the tray.
    # Later activations - e.g. the user launching rawm-control again - must
    # raise the existing window instead of silently doing nothing.
    if first and (self.start_hidden or config.load().get("start_hidden")):
        if self.tray is not None:
            return
    self.window.set_visible(True)
    ...
def _apply_state(self, state, changed) -> bool:   # runs via GLib.idle_add on EVERY state emit
    ...
    self._activated_once = False                   # <-- last line, resets the flag
```
State callbacks arrive continuously (30 s refresh + notifications), so `_activated_once`
is always `False` when the user re-launches `rawm-control`. With an autostarted
`--tray` instance, the second launch hits the early-return branch and **the window never
appears** — exactly the case the comment says must work. Likely a leftover debug line;
should be removed (or set `True`). Note: there are currently **no tests for app.py**.

### B3 — RSSI / battery calibration dropped after every write (inconsistent state adoption)
Two code paths adopt a fresh query, and only one preserves notification-only fields:
```python
# _perform_query (worker.py ~360-366) — correct:
with self._lock:
    previous = self._state
    state.battery_levels = previous.battery_levels or state.battery_levels
    state.rssi = previous.rssi
    self._state = state

# _loop_connected patch-write path (~390-407) — missing the same fix-up:
fresh, frames = device.query(timeout=1.4)
...
fresh.via_receiver = self._via_receiver
fresh.receiver_product_id = self._receiver_pid
apply_notifications(fresh, frames)
...
with self._lock:
    self._state = copy.deepcopy(fresh)     # rssi -> None, battery_levels -> defaults
```
Result: after any settings write the Signal row shows "—" until the next RSSI request
(only requested on connect). The fix-up logic should be extracted into one shared helper.

### B4 — CLI setters write a stale full-state snapshot
`cli.py` (same pattern for polling/dpi/lod/power):
```python
state, _frames = dev.query(...)      # at _open() time
...
state.polling_rate = args.hz
dev.set_state(state)                 # writes the ENTIRE param block from the stale snapshot
```
The GUI worker deliberately rebases user intent onto a **fresh** query before writing
precisely so a stale snapshot can't revert settings changed by a physical DPI button or
another tool (`worker.submit()` docstring states this). The CLI skips the rebase.
Race window is small but real. Fix: query fresh → apply patch → write, like the worker.

### B5 — Minor but real
- `install.sh --help`: `sed -n '2,9p'` prints the comment block **plus the `set -euo pipefail` line**.
- `app.py main()` usage text omits `--demo`, `--no-tray`, `--page`, `--version`; unknown args are hand-filtered then passed to `app.run()` (GApplication errors ungracefully).
- `Adw.UriLauncher` (app.py `_open_web_driver`) requires GTK 4.10+; no fallback for older stacks despite the declared 3.10+ floor.

---

## 3. Design concerns

- **D6 — `changed` tracking is dead plumbing.** `DeviceWorker` computes changed-field sets
  (incl. a `changed.update({"all"})` string sentinel), but `MainWindow.on_state` and
  `Tray.update` ignore `changed` entirely and re-render everything. Either use it
  (skip widget churn on background refresh, avoid rebuilding open dropdowns) or delete it.
- **D7 — Silent exception swallowing.** `except Exception: pass` around all worker→UI
  callbacks; `config.load()/save()` swallow `OSError` (preferences can silently never
  persist); tray DBus failures swallowed. No `logging` exists anywhere in the package.
- **D8 — Tray inefficiencies.** `_props()` is built twice per property `Get` (rebuilding the
  64×64 pixmap DBus array both times); `GetGroupProperties` → `_find()` rebuilds the whole
  menu layout per id (O(n²) dbus struct construction per menu open); `_argb_pixmap` is a
  pure-Python per-pixel loop. All main-thread work.
- **D9 — Magic numbers in capability logic.** `devices.py`: "≥3 power modes ⇒ mode 0 caps
  125 Hz, mode 1 caps 1000 Hz" is a firmware convention baked into generic code;
  `ui.py` hardcodes `tx_output_power = 8` for "wireless turbo". Undocumented model assumptions.
- **D10 — Version string duplicated in 5 places** (config.py, pyproject.toml, root PKGBUILD,
  AUR PKGBUILD.in, metainfo.xml) with a `bump-version.sh` regex patcher. Drift risk.

---

## 4. Repo hygiene

- A generated diagnostics report (`rawm-control-report-20261104-134926.md`, mode 0600,
  produced by v0.1.5) is **tracked in git** — contradicts the feature's own privacy story;
  untrack + gitignore `rawm-control-report-*.md`.
- Stale untracked build dirs in the tree (`AppDir/`, `dist/…0.1.1…AppImage`, `aur-build/`,
  `flatpak-build/`, `flatpak-repo/`, `.flatpak-builder/`); `make clean` covers none.
- No CHANGELOG; eight releases share one metainfo date.

---

## 5. Testing & CI gaps

- Good: 51 tests incl. framing reassembly at every split offset, CRC vectors from the
  original JS driver, worker lifecycle regressions, capability-matrix validation, privacy tests.
- Gaps: **no app.py tests** (B2 lives there), **no tray menu tests** (Event dispatch,
  ID-range arithmetic untested), no lint/type-check in CI (only `compileall` — mypy/ruff
  would mechanically catch B1), CI smoke test treats `timeout` exit 124 as success so a
  startup **hang** passes, hardware test flips motion sync with `finally` restore (a kill
  mid-test leaves the mouse flipped).

## 6. Packaging / CI posture

Good: pinned + SHA-256-verified appimagetool; AUR stable built from an immutable,
sha-pinned release tarball (with `-git` SKIP explained); least-privilege `permissions:`
per workflow; concurrency group + feature flag on the AUR publisher.
Improvement: third-party actions are pinned by **major tag** — especially
`KSXGitHub/github-actions-deploy-aur@v4.2.0`, which receives the SSH key that pushes to
AUR. Pin by commit SHA (supply-chain).

## 7. Security & privacy (assessed as solid)

- Device JSON parsed defensively into a copy; malformed replies raise `ProtocolError` and
  never partially mutate the known-good baseline.
- Unknown PIDs/keyboards are read-only by construction (`validate_patch`); the receiver path
  verifies the *paired* device is a known mouse before exposing writes.
- Diagnostics redact by key name + MAC regex + 12–64-hex-char regex + uevent
  `HID_UNIQ`/`UNIQ`/`SERIAL`; reports written atomically with 0600; identifiers are
  explicit opt-in in `rawmctl status --json`. No network code exists in the package.

---

## 8. UI/UX review (GTK4/libadwaita app)

Overall: idiomatic libadwaita (PreferencesPage/ViewStack, banner+retry, toasts, clamp),
the structure is right; the issues are details.

**Interaction fixes (highest value):**
1. **Combo models rebuilt on every state emit** (`_update_polling_combo`, LOD/power combos,
   DPI level dropdowns all call `set_model(Gtk.StringList.new(...))` inside `on_state`,
   which runs on every 30 s refresh). Setting a new model while the user has the popup open
   closes/resets it. Fix: rebuild only when contents changed; else `set_selected()` only.
2. **Toast spam + no debounce:** every change shows "Saving…" then a result toast (two per
   click); CPI/level/key-delay spin rows submit per `notify::value` while the user is still
   dragging (only the angle slider has a 260 ms debounce). GNOME pattern: silent success,
   failure-only toasts. Apply the existing debounce to the other spin rows.
3. **Per-row pending indicator:** writes are async (submit → confirm query → toast); show a
   small spinner suffix on the row being written until confirmation resolves.
4. **First-close hint:** closing hides to tray; show a one-time toast ("keeps running in
   the tray") on first close.

**Copy/info fixes:**
5. "milliseconds (low nibble of the key-delay byte)" — protocol jargon in UI text.
6. `--demo` is indistinguishable from a real device on screen → add a permanent demo banner.
7. Unverified-model warning is a buried subtitle → add an amber badge to the hero card.
8. Permission banner should offer a one-click **copy of the exact udev command**.

**Polish:**
9. Colour swatches instead of text-only colour dropdowns (3-bit RGB values already exist).
10. Battery gauge is a bare `DrawingArea` with no accessible label (screen readers get nothing).
11. Angle slider: add a center mark / reset-to-0 affordance.
12. Send multiple tray pixmap sizes (see §9) for sharp HiDPI panels.
13. Nice-to-have: desktop `Actions=` using the existing `--page` flag, a Gtk.ShortcutsWindow,
    a copy button on the receiver/ESB address row, an Undo action on toasts.

## 9. Tray icon proposals (SNI pixmaps, cairo-rendered)

Existing five styles: ring+mouse, number-only, battery outline, sidecar, mouse-with-column.
**Key problem:** all use a dark `#0B0E13` badge — GNOME's top bar is dark even in light
themes → dark-on-dark; they only pop on light Plasma panels. Charging is encoded by
colour only.

Proposed additions:
1. **Symbolic** — theme-following monochrome glyph + percentage; fixes dark-on-dark; matches system icons.
2. **Pill** — accent progress pill with number; explicit **bolt badge when charging**.
3. **Arc gauge** — transparent, open 270° gauge + number, no badge.
4. **Pips** — 10 segments, glanceable, no text.
5. **Glyph + badge** — symbolic mouse with a small notification-style number badge.

Plus a cross-cutting change: **append multiple pixmap sizes (22/32/48/64) to `IconPixmap`**
— KDE wants ~22–24 px and nearest-neighbour upscaling of the single 64 px pixmap is why
tray icons look soft. (Interactive mockups of all of these exist; ask the author.)

---

## 10. First-pass priority order (challenge this)

1. Fix `DemoWorker.stop()` (B1) — one line, demo quit broken today.
2. Fix/verify `_activated_once` reset (B2) — user-visible with autostart.
3. Shared fresh-state adoption helper preserving `rssi`/`battery_levels` (B3).
4. Rebase CLI writes on a fresh query (B4).
5. Untrack the committed report + gitignore the pattern (§4).
6. Decide fate of `changed` plumbing (D6); add stderr/logging to swallowed exceptions (D7).
7. Add ruff+mypy to CI (would have caught B1 mechanically).
8. Pin the AUR-deploy action by SHA (§6).
9. UI: stop rebuilding combo models (8.1), debounce + silent-success toasts (8.2), demo banner (8.6).
10. Tray: symbolic style + charging bolt + multi-size pixmaps (§9).

## 11. Questions for the reviewer

1. Is B2's `self._activated_once = False` plausibly intentional (some flow we're missing), or clearly a bug?
2. For B4, is a fresh query per CLI write acceptable latency (~1.4 s worst case), or is a
   conditional rebase (only before writes) the right shape?
3. Any additional failure modes in the worker lifecycle (connect → 3× query retries →
   confirm-after-0.4 s → 2-miss disconnect, backoff 0.5→3.0 s) worth hardening?
4. Are the proposed tray styles realistic within SNI's constraints (pixmap-only, no
   IconName for the percent styles, host-dependent contrast)? Which would you cut?
5. Anything in the protocol encoder (`encode_mouse_param`: 16/32-bit CPI paths, CRC
   envelope, per-key nibble delays) that looks fragile for unverified models?
