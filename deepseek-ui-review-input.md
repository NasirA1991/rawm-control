# RAWM Control — UI/UX review handoff for an external LLM (DeepSeek)

> **How to use:** paste this entire file as one message. It is self-contained — the
> reviewer needs no repo access; every claimed issue includes the relevant code.
> This document covers **UI/UX only** (GTK4/libadwaita window + DBus tray icon).
> A separate file (`deepseek-review-input.md`) covers the code-level review (bugs, CI, packaging).

---

## Instructions for the reviewer

You are reviewing proposed UI/UX changes for a native GTK4/libadwaita Linux app that
configures gaming mice (DPI, polling rate, lighting, battery). The proposals below came
from a first review pass. Your job:

1. Judge each proposal: is it the right fix? Simpler alternative? Overkill?
2. Re-order them by user impact vs. effort.
3. Flag anything a polished GNOME/libadwaita settings app would do that this list misses.
4. For the tray icons: they are rendered as cairo ARGB pixmaps over
   `org.kde.StatusNotifierItem` (SNI) + `com.canonical.dbusmenu` on raw dbus-python —
   judge feasibility against SNI's constraints (pixmap-only, host-dependent theming).

Be concrete. If a proposal is wrong for this stack, say why.

---

## 1. App UI context

- `MainWindow` (Adw.ApplicationWindow): headerbar with an `Adw.ViewSwitcher` over four
  `Adw.PreferencesPage` tabs (Device / Performance / DPI / Lighting), inside `Adw.ToolbarView`
  + `Adw.ToastOverlay`, clamped to 820 px. Disconnect shows an `Adw.Banner` with a Retry
  button; while disconnected the whole ViewStack is set insensitive.
- Device flow: a `DeviceWorker` thread owns the HID fd. UI edits call `worker.submit(state)`;
  the worker rebases onto a fresh device query, writes, then confirms by read-back ~0.4 s
  later and calls back to the UI with ok/message → toast. Background refresh emits full
  state every 30 s plus on device notifications.
- Tray: five icon styles rendered at a single 64×64 pixmap
  (`ring + mouse glyph`, `number only`, `battery outline + %`, `mouse + number sidecar`,
  `mouse only`); menu with polling-rate radio items, DPI level radio items, motion-sync /
  angle-snapping check items, style picker, open/refresh/quit. Status flips Active/Passive.
- All UI strings are hardcoded English (no i18n yet). Python 3.10+, GTK4 + libadwaita.

## 2. Current behaviour — the problems (with code)

### P1 — Dropdown models are rebuilt on every state refresh (popup closes under the user)
`on_state()` runs on every worker emit (≥ every 30 s) and unconditionally does:
```python
def _update_polling_combo(self, state, caps):
    rates = devices.effective_polling_rates(state)
    model = Gtk.StringList.new([caps.polling_label(hz) for hz in rates])
    self.row_polling_combo.set_model(model)      # new model every time
    ...
```
Same pattern for the LOD combo, power-mode combo, and the 8 per-level colour `Gtk.DropDown`s.
Setting a new model while the user has the popup open closes/resets it. **Proposed fix:**
only rebuild when the item list actually changed; otherwise just `set_selected()`.

### P2 — Toast spam: two toasts per change; writes fire per-tick with no debounce
```python
def _write(self, state, toast=None):
    self.worker.submit(state)
    if toast:
        saving = Adw.Toast.new("Saving…")        # toast 1
        saving.set_timeout(2)
        self.toast_overlay.add_toast(saving)

def on_write_result(self, ok, message):
    self.toast_overlay.add_toast(Adw.Toast.new(message))   # toast 2 ("Saved to mouse" / error)
```
And every spin row submits immediately per `notify::value` while the user is still
scrolling/typing — e.g. `_on_cpi_changed` / `_on_level_changed` / key-delay spins.
Only the angle slider debounces (260 ms via `GLib.timeout_add`).
**Proposed fix:** apply the existing 260 ms debounce to CPI/levels/key-delay; drop the
"Saving…" toast entirely; keep failure toasts (GNOME pattern: silent success, error toast).

### P3 — No per-row "busy" indicator
Writes are async (submit → confirm query → toast ~0.4–2 s later on a wireless link), but
nothing shows which control is pending. **Proposed:** a small `Adw.Spinner` suffix on the
row being written until the confirm resolves.

### P4 — Close-to-tray is silent
```python
def _on_close_request(self, _window):
    if self.tray is not None and not self._quitting:
        self.window.set_visible(False)   # hides to tray, no hint
        return True
    return False
```
**Proposed:** one-time toast on first close: "RAWM Control keeps running in the tray —
quit from the tray menu".

### P5 — Copy / information issues
- Key-delay subtitle leaks protocol internals: `"milliseconds (low nibble of the key-delay byte)"` → just "milliseconds".
- `--demo` renders a fully convincing fake ER21Pro with no on-screen indication → add a permanent demo-mode banner.
- Model trust ("Capability profile only — hardware unverified") is a buried row subtitle → amber badge in the hero card.
- The permission banner names the udev rule but the exact fix is only in the README → add a "Copy setup command" action that puts the `sudo tee …` one-liner on the clipboard.

### P6 — Text where pixels belong
Colour choices (DPI level colours, lighting colour) are text-only dropdowns
("Red", "Sky blue", …) although the underlying data is 3-bit RGB. **Proposed:** colour
swatches inside the dropdown rows / next to each level.

### P7 — Accessibility & polish
- `BatteryGauge` is a bare `Gtk.DrawingArea` (custom cairo ring) — no accessible label/role; screen readers get nothing.
- Angle-tuning slider (−30…+30) has no center mark and no quick reset-to-0.
- `Adw.UriLauncher` used for the web-driver link requires GTK 4.10+, no fallback.
- Nice-to-haves: desktop file `Actions=` (Status/Performance/DPI) wired to the existing
  `--page` CLI flag; `Gtk.ShortcutsWindow` for Ctrl+Q/Ctrl+R; copy button on the
  receiver/ESB address row (it already has Show/Hide); "Undo" action on change toasts.

## 3. Tray icon proposals

**Problem being solved:** every existing style draws a dark `#0B0E13` rounded badge.
GNOME's top bar is dark even in light themes → dark-on-dark; the icons only pop on light
Plasma panels. Also, charging state is encoded **only by colour** (blue), and only one
64×64 pixmap is sent, so hosts upscaling it for ~22–24 px panels look soft.

Current styles (for reference): progress ring + mouse glyph + % inside; number-only badge;
battery outline + %; mouse glyph + accent-coloured number beside it; filled mouse glyph
with an internal charge column.

**Proposed additions:**
1. **Symbolic** — theme-following monochrome glyph + small percentage; no badge. Fixes
   dark-on-dark; matches system status icons on GNOME/KDE.
2. **Pill** — accent-outlined pill, number inside, thin progress underline; explicit
   lightning-bolt badge when charging.
3. **Arc gauge** — transparent background, open 270° gauge arc + number; no badge.
4. **Pips** — 10 segments (2×5 dots), filled per 10 %; glanceable, no text.
5. **Glyph + badge** — symbolic mouse with a small notification-style number badge.

**Cross-cutting changes regardless of style:**
- Add the charging bolt overlay to all styles (charging must not be colour-only).
- Append **multiple pixmap sizes (22/32/48/64)** to SNI `IconPixmap` instead of one 64 px
  entry, so panels get a crisp native-size icon.
- Interactive mockups of all styles (dark/light panel, 0–100 %, charging, disconnected)
  already exist; screenshots can be attached on request.

## 4. Questions for the reviewer

1. Tray styles: which of the five proposals are realistic within SNI (pixmap-only, no
   per-host theming API — "Symbolic" would need the app to query the panel style or ship
   light/dark variants)? Which would you cut?
2. Spin rows: is a 260 ms debounce the right call, or write-on-release
   (`Gtk.SpinButton` "output"/button-release), given `worker.submit()` already coalesces
   concurrent patches into one write?
3. Silent-success vs. current double toast: the write path can legitimately fail to
   confirm (device asleep). Is "failure-only toasts" safe here, or is a single "Saved"
   toast worth keeping as reassurance?
4. For the DPI page: the first pass proposed either a log-scaled slider with level ticks
   or a radial "dial" with clickable level chips. Range is 50–30,000 with daily use at
   400–3,200 — which design holds up, and is either worth the complexity over the current
   SpinRow?
5. Order these by impact/effort and name anything missing for a libadwaita settings app
   (e.g., `Adw.Dialog` subpages, `Adw.ToggleGroup`, keynav/a11y conventions).
