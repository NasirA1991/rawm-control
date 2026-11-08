"""GTK4 / libadwaita user interface."""

from __future__ import annotations

import math
from typing import Callable

import cairo

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402

from . import devices  # noqa: E402
from .config import TRAY_STYLES  # noqa: E402
from .protocol import (  # noqa: E402
    COLOR_BITS,
    COLOR_BITS_TO_NAME,
    COLOR_NAMES,
    LED_AUTO_OFF,
    LED_CPI,
    LED_FLAG,
    LED_RGB_MASK,
    MouseState,
)

CSS = """
.hero-card {
    background-color: alpha(currentColor, 0.055);
    border-radius: 18px;
    padding: 22px;
}
.hero-title { font-size: 26px; font-weight: 800; }
.hero-sub { opacity: 0.68; }
.hero-badge {
    background-color: alpha(currentColor, 0.10);
    border-radius: 999px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 700;
}
.demo-badge {
    background-color: alpha(#e01b24, 0.22);
    color: #ff7b72;
}
.trust-badge {
    background-color: alpha(#e5a50a, 0.22);
    color: #f5c211;
}
.permission-bar {
    background-color: alpha(#e5a50a, 0.12);
    padding: 6px 12px;
}
.battery-value { font-size: 31px; font-weight: 800; }
.battery-sub { font-size: 10px; font-weight: 700; opacity: 0.75; }
.value-label { font-feature-settings: "tnum"; }
.mono { font-family: monospace; font-size: 12px; }
.level-row label { opacity: 0.8; }
"""

COLOR_LABELS = [name for name in COLOR_NAMES]
COLOR_KEY_BY_INDEX = ["off", "red", "green", "blue", "yellow", "purple", "skyblue", "white"]

UDEV_COMMAND = (
    "echo 'SUBSYSTEM==\"hidraw\", ATTRS{idVendor}==\"1915\", "
    "TAG+=\"uaccess\", MODE=\"0660\"' | "
    "sudo tee /usr/lib/udev/rules.d/71-rawm-hid.rules >/dev/null\n"
    "sudo udevadm control --reload-rules && sudo udevadm trigger"
)


def _same_labels(model, labels: list[str]) -> bool:
    if model is None or model.get_n_items() != len(labels):
        return False
    return all(model.get_string(i) == label for i, label in enumerate(labels))


def _set_combo_labels(combo, labels: list[str]) -> None:
    """Only rebuild a Gtk.StringList when its contents actually changed."""
    if _same_labels(combo.get_model(), labels):
        return
    combo.set_model(Gtk.StringList.new(labels))


class BatteryGauge(Gtk.Overlay):
    def __init__(self) -> None:
        super().__init__()
        self.set_accessible_role(Gtk.AccessibleRole.PROGRESS_BAR)
        self._percent = 0
        self._charging = False
        self._connected = False
        self._area = Gtk.DrawingArea()
        self._area.set_content_width(148)
        self._area.set_content_height(148)
        self._area.set_draw_func(self._draw)
        self.set_child(self._area)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        box.set_halign(Gtk.Align.CENTER)
        box.set_valign(Gtk.Align.CENTER)
        self._value = Gtk.Label(label="--")
        self._value.add_css_class("battery-value")
        self._sub = Gtk.Label(label="no mouse")
        self._sub.add_css_class("battery-sub")
        box.append(self._value)
        box.append(self._sub)
        self.add_overlay(box)

    def set_state(self, state: MouseState | None, connected: bool) -> None:
        self._connected = connected and state is not None
        if state is None:
            self._percent = 0
            self._charging = False
            self._value.set_text("--")
            self._sub.set_text("no mouse")
            self._update_accessible("Battery unavailable; no mouse connected", 0)
        else:
            self._percent = max(0, min(100, state.battery))
            self._charging = state.charging
            self._value.set_text(f"{self._percent}%")
            self._sub.set_text("charging" if state.charging else ("wired" if state.wired else "wireless"))
            label = f"Battery {self._percent}%"
            if state.charging:
                label += ", charging"
            self._update_accessible(label, self._percent)
        self._area.queue_draw()

    def _update_accessible(self, label: str, value: int) -> None:
        try:
            self.update_property(
                [
                    Gtk.AccessibleProperty.LABEL,
                    Gtk.AccessibleProperty.VALUE_MIN,
                    Gtk.AccessibleProperty.VALUE_MAX,
                    Gtk.AccessibleProperty.VALUE_NOW,
                    Gtk.AccessibleProperty.VALUE_TEXT,
                ],
                [label, 0, 100, value, label],
            )
        except (AttributeError, TypeError):
            pass

    def _draw(self, area: Gtk.DrawingArea, cr, width: int, height: int) -> None:
        cx, cy = width / 2, height / 2
        radius = min(width, height) / 2 - 9
        cr.set_line_width(10)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        try:
            fg = self.get_style_context().get_color()
            base = (fg.red, fg.green, fg.blue)
        except (AttributeError, TypeError):
            base = (1, 1, 1)
        cr.set_source_rgba(*base, 0.10)
        cr.arc(cx, cy, radius, 0, 2 * math.pi)
        cr.stroke()

        if self._connected:
            pct = self._percent
            if self._charging:
                color = (0.35, 0.72, 1.0)
            elif pct > 40:
                color = (0.33, 0.85, 0.48)
            elif pct > 20:
                color = (0.98, 0.74, 0.18)
            else:
                color = (0.95, 0.34, 0.34)
            start = -math.pi / 2
            sweep = 2 * math.pi * pct / 100.0
            cr.set_source_rgba(*color, 0.95)
            cr.arc(cx, cy, radius, start, start + max(sweep, 0.001))
            cr.stroke()
        else:
            cr.set_source_rgba(*base, 0.15)
            cr.set_line_width(2)
            cr.arc(cx, cy, radius, 0, 2 * math.pi)
            cr.stroke()


class MainWindow(Adw.ApplicationWindow):
    def __init__(
        self,
        worker,
        on_settings_changed: Callable[[], None] | None = None,
        initial_page: str | None = None,
        demo: bool = False,
    ) -> None:
        super().__init__(title="RAWM Control")
        self.worker = worker
        self.demo = demo
        self._state: MouseState | None = None
        self._connected = False
        self._loading = False
        self._angle_timer = 0
        self._edit_timer = 0
        self._levels: list[dict] = []
        self._key_index = 0
        self._kd_model_len = 0
        self._on_settings_changed = on_settings_changed

        self.set_default_size(980, 760)
        self.set_size_request(620, 520)

        self._build_ui()
        self._install_css()
        if initial_page:
            self.stack.set_visible_child_name(initial_page)

    # ------------------------------------------------------------------ UI
    def _install_css(self) -> None:
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS.encode("utf-8"))
        display = Gdk.Display.get_default()
        if display:
            Gtk.StyleContext.add_provider_for_display(
                display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )

    def _build_ui(self) -> None:
        self.toast_overlay = Adw.ToastOverlay()
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        self.banner = Adw.Banner(title="Mouse not connected")
        self.banner.set_button_label("Retry")
        self.banner.connect("button-clicked", lambda *_: self.worker.refresh())
        self.banner.set_revealed(False)
        root.append(self.banner)

        self.permission_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.permission_bar.add_css_class("permission-bar")
        self.permission_bar.set_visible(False)
        permission_label = Gtk.Label(
            label="Missing hidraw permission. Install the udev rule on the host once.",
            xalign=0,
        )
        permission_label.set_hexpand(True)
        permission_label.set_wrap(True)
        self.permission_copy = Gtk.Button(label="Copy setup command")
        self.permission_copy.connect("clicked", self._on_copy_udev)
        self.permission_bar.append(permission_label)
        self.permission_bar.append(self.permission_copy)
        root.append(self.permission_bar)

        self.stack = Adw.ViewStack()
        self.stack.add_titled_with_icon(
            self._build_device_page(), "device", "Device", "rawm-device-symbolic"
        )
        self.stack.add_titled_with_icon(
            self._build_performance_page(), "performance", "Performance", "rawm-performance-symbolic"
        )
        self.stack.add_titled_with_icon(
            self._build_dpi_page(), "dpi", "DPI", "rawm-dpi-symbolic"
        )
        self.stack.add_titled_with_icon(
            self._build_lighting_page(), "lighting", "Lighting", "rawm-lighting-symbolic"
        )

        clamp = Adw.Clamp()
        clamp.set_maximum_size(820)
        clamp.set_tightening_threshold(600)
        clamp.set_child(self.stack)
        clamp.set_vexpand(True)
        root.append(clamp)
        self.toast_overlay.set_child(root)

        switcher = Adw.ViewSwitcher()
        switcher.set_stack(self.stack)
        try:
            switcher.set_policy(Adw.ViewSwitcherPolicy.AUTO)
        except (AttributeError, TypeError):
            switcher.set_policy(Adw.ViewSwitcherPolicy.WIDE)

        header = Adw.HeaderBar()
        header.set_title_widget(switcher)

        menu = Gtk.MenuButton()
        menu.set_icon_name("open-menu-symbolic")
        menu.set_tooltip_text("Main menu")
        menu.set_menu_model(self._build_menu())
        header.pack_end(menu)

        refresh = Gtk.Button(icon_name="view-refresh-symbolic")
        refresh.set_tooltip_text("Refresh")
        refresh.connect("clicked", lambda *_: self.worker.refresh())
        header.pack_start(refresh)

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(header)
        toolbar.set_content(self.toast_overlay)
        self.set_content(toolbar)

    def _build_menu(self):
        from gi.repository import Gio

        menu = Gio.Menu()
        menu.append("Refresh", "app.refresh")
        style_menu = Gio.Menu()
        for key, label in TRAY_STYLES:
            item = Gio.MenuItem.new(label, None)
            item.set_action_and_target_value("app.tray-style", GLib.Variant.new_string(key))
            style_menu.append_item(item)
        menu.append_submenu("Tray icon", style_menu)
        menu.append("Autostart at login", "app.autostart")
        menu.append("Open official web driver", "app.web-driver")
        menu.append("About RAWM Control", "app.about")
        menu.append("Quit", "app.quit")
        return menu

    def _build_device_page(self) -> Gtk.Widget:
        page = Adw.PreferencesPage()
        page.set_title("Device")

        hero_group = Adw.PreferencesGroup()
        hero_group.set_margin_top(18)
        hero_card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=22)
        hero_card.add_css_class("hero-card")

        self.gauge = BatteryGauge()
        hero_card.append(self.gauge)

        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        text.set_valign(Gtk.Align.CENTER)
        text.set_hexpand(True)
        self.hero_title = Gtk.Label(label="No mouse connected")
        self.hero_title.add_css_class("hero-title")
        self.hero_title.set_xalign(0)
        self.hero_sub = Gtk.Label(label="Plug in the 2.4 GHz receiver or connect the mouse over USB.")
        self.hero_sub.add_css_class("hero-sub")
        self.hero_sub.set_xalign(0)
        self.hero_sub.set_wrap(True)
        badges = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.badge_link = Gtk.Label(label="disconnected")
        self.badge_link.add_css_class("hero-badge")
        self.badge_sensor = Gtk.Label(label="")
        self.badge_sensor.add_css_class("hero-badge")
        self.badge_demo = Gtk.Label(label="DEMO — simulated device")
        self.badge_demo.add_css_class("hero-badge")
        self.badge_demo.add_css_class("demo-badge")
        self.badge_demo.set_visible(self.demo)
        self.badge_trust = Gtk.Label(label="UNVERIFIED MODEL")
        self.badge_trust.add_css_class("hero-badge")
        self.badge_trust.add_css_class("trust-badge")
        self.badge_trust.set_tooltip_text(
            "This model is supported by the vendor capability database, but has not "
            "been verified on physical hardware."
        )
        self.badge_trust.set_visible(False)
        badges.append(self.badge_link)
        badges.append(self.badge_sensor)
        badges.append(self.badge_demo)
        badges.append(self.badge_trust)
        badges.set_halign(Gtk.Align.START)
        text.append(self.hero_title)
        text.append(self.hero_sub)
        text.append(badges)
        hero_card.append(text)
        hero_group.add(hero_card)
        page.add(hero_group)

        self.group_about = Adw.PreferencesGroup(title="Device")
        self.row_model = Adw.ActionRow(title="Model")
        self.row_trust = Adw.ActionRow(title="Support status")
        self.row_firmware = Adw.ActionRow(title="Firmware")
        self.row_sensor = Adw.ActionRow(title="Sensor")
        self.row_connection = Adw.ActionRow(title="Connection")
        self.row_polling = Adw.ActionRow(title="Polling rate")
        self.row_lod = Adw.ActionRow(title="Lift-off distance")
        self.row_power = Adw.ActionRow(title="Power mode")
        self.row_signal = Adw.ActionRow(title="Signal")
        self.row_onboard = Adw.ActionRow(title="Onboard profiles")
        self.row_esb = Adw.ActionRow(title="Receiver address")
        self._esb_value = ""
        self._esb_revealed = False
        self.reveal_esb = Gtk.ToggleButton(label="Show")
        self.reveal_esb.set_valign(Gtk.Align.CENTER)
        self.reveal_esb.add_css_class("flat")
        self.reveal_esb.connect("toggled", self._on_reveal_esb)
        self.row_esb.add_suffix(self.reveal_esb)
        for row in (
            self.row_model,
            self.row_trust,
            self.row_firmware,
            self.row_sensor,
            self.row_connection,
            self.row_polling,
            self.row_lod,
            self.row_power,
            self.row_signal,
            self.row_onboard,
            self.row_esb,
        ):
            row.set_activatable(False)
            self.group_about.add(row)
        self.row_esb.add_css_class("mono")
        page.add(self.group_about)

        self.group_actions = Adw.PreferencesGroup(title="Maintenance")
        self.row_refresh = Adw.ButtonRow(title="Refresh device state")
        self.row_refresh.connect("activated", lambda *_: self.worker.refresh())
        self.group_actions.add(self.row_refresh)

        self.row_restore = Adw.ActionRow(
            title="Restore detected settings",
            subtitle="Revert to the values read when this mouse connected.",
        )
        self.row_restore.set_activatable(False)
        self.restore_button = Gtk.Button(label="Restore")
        self.restore_button.set_valign(Gtk.Align.CENTER)
        self.restore_button.set_sensitive(False)
        self.restore_button.connect("clicked", self._on_restore_clicked)
        self.row_restore.add_suffix(self.restore_button)
        self.group_actions.add(self.row_restore)
        page.add(self.group_actions)

        diagnostics = Adw.PreferencesGroup(
            title="Diagnostics",
            description=(
                "Read-only report for adding support for another RAWM model. "
                "It is saved locally; nothing is uploaded automatically."
            ),
        )
        self.row_report = Adw.ActionRow(
            title="Save device report",
            subtitle="Review the file, then attach it to a GitHub issue.",
        )
        self.row_report.set_activatable(False)
        report_button = Gtk.Button(icon_name="document-save-symbolic")
        report_button.set_tooltip_text("Save a read-only device report")
        report_button.set_valign(Gtk.Align.CENTER)
        report_button.add_css_class("flat")
        report_button.connect("clicked", self._on_save_report)
        self.row_report.add_suffix(report_button)
        diagnostics.add(self.row_report)
        page.add(diagnostics)
        return page

    def _on_save_report(self, *_args) -> None:
        from . import diagnostics

        dialog = Gtk.FileDialog()
        dialog.set_title("Save RAWM Control device report")
        dialog.set_initial_name(diagnostics.default_filename())
        dialog.save(self, None, self._on_report_saved)

    def _on_report_saved(self, dialog, result) -> None:
        from . import diagnostics

        try:
            gfile = dialog.save_finish(result)
        except GLib.Error:
            return
        if gfile is None or not gfile.get_path():
            return
        try:
            path = diagnostics.write_report(gfile.get_path())
        except Exception as exc:
            self.toast_overlay.add_toast(Adw.Toast.new(f"Could not write report: {exc}"))
            return
        self.toast_overlay.add_toast(Adw.Toast.new(f"Report saved to {path.name}"))

    def _build_performance_page(self) -> Gtk.Widget:
        page = Adw.PreferencesPage()
        page.set_title("Performance")

        polling = Adw.PreferencesGroup(
            title="Polling rate",
            description="How often the mouse reports to the computer. Higher rates feel smoother but use more battery.",
        )
        self.row_polling_combo = Adw.ComboRow(title="Report rate")
        self.row_polling_combo.connect("notify::selected", self._on_polling_selected)
        polling.add(self.row_polling_combo)
        page.add(polling)

        sensor = Adw.PreferencesGroup(title="Sensor")
        self.row_motion = Adw.SwitchRow(
            title="Motion sync",
            subtitle="Aligns sensor sampling with the report interval for more consistent tracking.",
        )
        self.row_motion.connect("notify::active", self._on_motion_toggled)
        sensor.add(self.row_motion)

        self.row_snapping = Adw.SwitchRow(
            title="Angle snapping",
            subtitle="Straightens near-horizontal and near-vertical movement.",
        )
        self.row_snapping.connect("notify::active", self._on_snapping_toggled)
        sensor.add(self.row_snapping)

        self.row_ripple = Adw.SwitchRow(
            title="Ripple control",
            subtitle="Smooths small pixel-level jitter.",
        )
        self.row_ripple.connect("notify::active", self._on_ripple_toggled)
        sensor.add(self.row_ripple)

        self.row_glass = Adw.SwitchRow(
            title="Glass mode",
            subtitle="Tune tracking for glass or very smooth surfaces.",
        )
        self.row_glass.connect("notify::active", self._on_glass_toggled)
        sensor.add(self.row_glass)

        angle_row = Adw.ActionRow(
            title="Angle tuning",
            subtitle="Rotate the sensor axis from -30° to +30°.",
        )
        self.angle_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, -30, 30, 1)
        self.angle_scale.set_size_request(260, -1)
        self.angle_scale.set_draw_value(True)
        self.angle_scale.set_value_pos(Gtk.PositionType.RIGHT)
        self.angle_scale.set_hexpand(True)
        self.angle_scale.connect("value-changed", self._on_angle_changed)
        angle_row.add_suffix(self.angle_scale)
        sensor.add(angle_row)
        self.row_angle = angle_row
        page.add(sensor)

        lift = Adw.PreferencesGroup(title="Lift-off distance")
        self.row_lod_combo = Adw.ComboRow(title="Lift-off distance")
        self.row_lod_combo.connect("notify::selected", self._on_lod_selected)
        lift.add(self.row_lod_combo)
        self.row_surface = Adw.ActionRow(title="Surface quality")
        self.row_surface.set_activatable(False)
        lift.add(self.row_surface)
        page.add(lift)

        keydelay = Adw.PreferencesGroup(
            title="Key delay",
            description="Debounce time per button; raise it if clicks double or drop.",
        )
        self.row_key = Adw.ComboRow(title="Button")
        self.row_key.connect("notify::selected", self._on_key_selected)
        keydelay.add(self.row_key)
        self.row_press = Adw.SpinRow(
            title="Press delay",
            subtitle="milliseconds",
            adjustment=Gtk.Adjustment(value=2, lower=0, upper=10, step_increment=1),
        )
        self.row_press.set_digits(0)
        self.row_press.connect("notify::value", self._on_press_changed)
        keydelay.add(self.row_press)
        self.row_release = Adw.SpinRow(
            title="Release delay",
            subtitle="milliseconds (high nibble of the key-delay byte)",
            adjustment=Gtk.Adjustment(value=2, lower=0, upper=10, step_increment=1),
        )
        self.row_release.set_digits(0)
        self.row_release.connect("notify::value", self._on_release_changed)
        keydelay.add(self.row_release)
        self.group_keydelay = keydelay
        page.add(keydelay)

        power = Adw.PreferencesGroup(
            title="Power",
            description="Power mode trades latency and maximum polling rate for battery life.",
        )
        self.row_power_combo = Adw.ComboRow(title="Power mode")
        self.row_power_combo.connect("notify::selected", self._on_power_selected)
        power.add(self.row_power_combo)
        self.row_sleep = Adw.SpinRow(
            title="Sleep timer",
            subtitle="Idle time before the mouse goes to sleep.",
            adjustment=Gtk.Adjustment(value=5, lower=1, upper=30, step_increment=1, page_increment=5),
        )
        self.row_sleep.set_digits(0)
        self.row_sleep.connect("notify::value", self._on_sleep_changed)
        power.add(self.row_sleep)
        page.add(power)

        self.group_wireless = Adw.PreferencesGroup(title="Wireless")
        wireless = self.group_wireless
        self.row_turbo = Adw.SwitchRow(
            title="Wireless turbo",
            subtitle="Raises transmit power for a stronger link; costs battery.",
        )
        self.row_turbo.connect("notify::active", self._on_turbo_toggled)
        wireless.add(self.row_turbo)
        page.add(wireless)
        return page

    def _build_dpi_page(self) -> Gtk.Widget:
        page = Adw.PreferencesPage()
        page.set_title("DPI")

        active = Adw.PreferencesGroup(
            title="Active resolution",
            description="The CPI currently reported to the system.",
        )
        adj = Gtk.Adjustment(value=1600, lower=50, upper=30000, step_increment=50, page_increment=500)
        self.row_cpi = Adw.SpinRow(title="CPI / DPI", adjustment=adj)
        self.row_cpi.set_digits(0)
        self.row_cpi.connect("notify::value", self._on_cpi_changed)
        active.add(self.row_cpi)
        page.add(active)

        self.levels_group = Adw.PreferencesGroup(
            title="DPI levels",
            description="Levels cycled by the DPI button. Set a level to 0 to disable it.",
        )
        for index in range(8):
            row = Adw.ActionRow(title=f"Level {index + 1}")
            row.set_activatable(False)
            spin_adj = Gtk.Adjustment(
                value=0, lower=0, upper=30000, step_increment=50, page_increment=500
            )
            spin = Gtk.SpinButton(adjustment=spin_adj, climb_rate=1, digits=0)
            spin.set_size_request(130, -1)
            spin.add_css_class("value-label")
            spin.connect("value-changed", self._on_level_changed, index)
            combo = Gtk.DropDown.new_from_strings(COLOR_LABELS)
            combo.set_size_request(130, -1)
            combo.connect("notify::selected", self._on_level_color_changed, index)
            suffix = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            suffix.append(spin)
            suffix.append(combo)
            row.add_suffix(suffix)
            self.levels_group.add(row)
            self._levels.append({"row": row, "spin": spin, "combo": combo})
        page.add(self.levels_group)
        return page

    def _build_lighting_page(self) -> Gtk.Widget:
        page = Adw.PreferencesPage()
        page.set_title("Lighting")

        group = Adw.PreferencesGroup(
            title="Indicator",
            description="RAWM mice light up the CPI indicator. Choose what the LED shows.",
        )
        self.row_light_mode = Adw.ComboRow(title="LED mode")
        self.row_light_mode.set_model(
            Gtk.StringList.new(["DPI colour indicator", "Static colour", "Off"])
        )
        self.row_light_mode.connect("notify::selected", self._on_light_mode_changed)
        group.add(self.row_light_mode)

        self.row_light_color = Adw.ComboRow(title="Colour")
        self.row_light_color.set_model(Gtk.StringList.new(COLOR_LABELS[1:]))
        self.row_light_color.connect("notify::selected", self._on_light_color_changed)
        group.add(self.row_light_color)
        page.add(group)

        behaviour = Adw.PreferencesGroup(title="Behaviour")
        self.row_auto_off = Adw.SwitchRow(
            title="Turn LED off when idle",
            subtitle="Saves battery when the mouse is not moving.",
        )
        self.row_auto_off.connect("notify::active", self._on_auto_off_toggled)
        behaviour.add(self.row_auto_off)
        page.add(behaviour)

        note = Adw.PreferencesGroup()
        label = Gtk.Label(
            label="Per-level colours are configured on the DPI page. "
            "Lighting support varies between models; unsupported controls are hidden automatically.",
            wrap=True,
            xalign=0,
        )
        label.add_css_class("dim-label")
        label.set_margin_top(6)
        label.set_margin_bottom(12)
        label.set_margin_start(6)
        label.set_margin_end(6)
        note.add(label)
        page.add(note)
        return page

    # ------------------------------------------------------------- updates
    def on_state(self, state: MouseState, changed: set[str]) -> None:
        self._state = state
        self._connected = True
        caps = devices.for_state(state)
        self._loading = True
        try:
            self.banner.set_revealed(False)
            self.stack.set_sensitive(True)
            self.gauge.set_state(state, True)

            self.hero_title.set_text(caps.display_name)
            bits = [state.firmware or "firmware ?", state.sensor or caps.sensor or "sensor ?"]
            self.hero_sub.set_text(" · ".join(b for b in bits if b))
            self.badge_link.set_text(
                "USB" if state.wired else ("via receiver" if state.via_receiver else "2.4 GHz")
            )
            self.badge_sensor.set_text("charging" if state.charging else "on battery")

            self.row_model.set_subtitle(caps.display_name)
            self.row_trust.set_subtitle(devices.support_status(caps))
            self.badge_trust.set_visible(caps.mouse and caps.product_id != 0x2338)
            self.restore_button.set_sensitive(bool(getattr(self.worker, "has_baseline", False)))
            self.row_firmware.set_subtitle(state.firmware or "unknown")
            self.row_sensor.set_subtitle(state.sensor or caps.sensor or "unknown")
            link = "USB wired" if state.wired else "2.4 GHz wireless"
            if state.via_receiver and not state.wired:
                link += " (receiver)"
            self.row_connection.set_subtitle(link + (" · charging" if state.charging else ""))
            max_rate = devices.max_polling_rate(state)
            self.row_polling.set_subtitle(
                f"{self._polling_text(state.polling_rate)} · up to {self._polling_text(max_rate)}"
            )
            self.row_lod.set_subtitle(caps.lod_label(state.lod))
            self.row_power.set_subtitle(self._power_text(state, caps))
            self.row_signal.set_subtitle(
                f"{state.rssi} dBm" if state.rssi is not None else "—"
            )
            self.row_onboard.set_subtitle(
                f"{state.onboard_count} profiles · active {state.onboard + 1}"
            )
            self._esb_value = state.esb_address or ""
            self.row_esb.set_subtitle(
                self._esb_value if self._esb_revealed and self._esb_value else ("••••••••" if self._esb_value else "—")
            )
            self.row_esb.set_visible(bool(self._esb_value))

            self._update_polling_combo(state, caps)
            self._update_performance(state, caps)
            self._update_key_delay(state)
            self._update_dpi(state, caps)
            self._update_lighting(state)
        finally:
            self._loading = False

    def on_link(self, connected: bool, error: str | None) -> None:
        self._connected = connected
        if connected:
            self.banner.set_revealed(False)
            self.permission_bar.set_visible(False)
            return
        self._state = None
        self.badge_trust.set_visible(False)
        self.restore_button.set_sensitive(False)
        self.stack.set_sensitive(False)
        self.gauge.set_state(None, False)
        self.hero_title.set_text("No mouse connected")
        self.hero_sub.set_text(
            "Plug in the 2.4 GHz receiver or connect the mouse over USB. "
            "If the mouse is connected, the udev rule may be missing."
        )
        self.badge_link.set_text("disconnected")
        self.badge_sensor.set_text("")
        self.banner.set_title(error or "Mouse not connected")
        self.banner.set_revealed(True)
        permission = bool(error and any(
            word in error.lower() for word in ("permission", "udev", "hidraw")
        ))
        self.permission_bar.set_visible(permission)

    def _update_polling_combo(self, state: MouseState, caps) -> None:
        rates = devices.effective_polling_rates(state)
        _set_combo_labels(self.row_polling_combo, [caps.polling_label(hz) for hz in rates])
        try:
            selected = rates.index(state.polling_rate)
        except ValueError:
            selected = 0
        self.row_polling_combo.set_selected(selected)
        maximum = devices.max_polling_rate(state)
        self.row_polling_combo.set_subtitle(
            f"Up to {caps.polling_label(maximum)} on this link and power mode"
        )

    def _on_copy_udev(self, _button) -> None:
        display = Gdk.Display.get_default()
        if display is not None:
            display.get_clipboard().set(UDEV_COMMAND)
        self.show_toast("Setup command copied — run it on the host")

    def _update_performance(self, state: MouseState, caps) -> None:
        self.row_motion.set_active(bool(state.motion_sync))
        self.row_snapping.set_active(bool(state.angle_snapping))
        self.row_ripple.set_active(bool(state.ripple_control))
        self.row_glass.set_active(bool(state.glass_mode_enabled))
        self.row_glass.set_visible(bool(caps.glass_mode))
        self.angle_scale.set_value(float(state.angle_tuning))
        self.row_angle.set_visible(bool(caps.angle_tuning))

        lods = caps.lod_names or ["LOW", "MEDIUM", "HIGH"]
        _set_combo_labels(self.row_lod_combo, [name.title() for name in lods])
        self.row_lod_combo.set_selected(max(0, min(len(lods) - 1, state.lod - 1)))
        if state.surface_quality:
            self.row_surface.set_subtitle(f"{round(state.surface_quality * 100 / 255)}% (sensor estimate)")
            self.row_surface.set_visible(True)
        else:
            self.row_surface.set_visible(False)

        modes = caps.power_modes
        self.row_power_combo.set_visible(bool(modes))
        if modes:
            _set_combo_labels(self.row_power_combo, modes)
            self.row_power_combo.set_selected(max(0, min(len(modes) - 1, state.power_mode)))
        self.row_sleep.set_value(max(1, min(30, round(state.sleep_time / 60) or 1)))
        wireless = not state.wired
        self.group_wireless.set_visible(wireless)
        self.row_turbo.set_visible(wireless)
        self.row_turbo.set_active(state.tx_output_power not in (0, 0xFF))

    def _update_key_delay(self, state: MouseState) -> None:
        delays = state.key_delay
        if not delays:
            self.group_keydelay.set_visible(False)
            return
        self.group_keydelay.set_visible(True)
        if self._kd_model_len != len(delays):
            self.row_key.set_model(
                Gtk.StringList.new([f"Button {i + 1}" for i in range(len(delays))])
            )
            self._kd_model_len = len(delays)
        index = max(0, min(self._key_index, len(delays) - 1))
        byte = delays[index] & 0xFF
        self.row_press.set_value(byte & 0x0F)
        self.row_release.set_value((byte >> 4) & 0x0F)

    def _update_dpi(self, state: MouseState, caps) -> None:
        adj = self.row_cpi.get_adjustment()
        adj.set_lower(caps.cpi_range[0])
        adj.set_upper(caps.cpi_range[1])
        adj.set_step_increment(caps.cpi_step)
        self.row_cpi.set_value(max(caps.cpi_range[0], min(caps.cpi_range[1], state.cpi)))
        for index, widgets in enumerate(self._levels):
            level = state.cpi_levels[index] if index < len(state.cpi_levels) else 0
            spin = widgets["spin"]
            spin_adj = spin.get_adjustment()
            spin_adj.set_lower(0)
            spin_adj.set_upper(caps.cpi_range[1])
            spin_adj.set_step_increment(caps.cpi_step)
            spin.set_value(level)
            color = state.cpi_level_colors[index] if index < len(state.cpi_level_colors) else 0
            name = COLOR_BITS_TO_NAME.get(color & LED_RGB_MASK, "off")
            try:
                widgets["combo"].set_selected(COLOR_KEY_BY_INDEX.index(name))
            except ValueError:
                widgets["combo"].set_selected(0)
            widgets["row"].set_subtitle("active" if level and level == state.cpi else "")

    def _update_lighting(self, state: MouseState) -> None:
        light = state.light & ~LED_FLAG
        if light & LED_CPI:
            mode = 0
        elif light & LED_RGB_MASK:
            mode = 1
        else:
            mode = 2
        self.row_light_mode.set_selected(mode)
        color_index = 0
        bits = light & LED_RGB_MASK
        name = COLOR_BITS_TO_NAME.get(bits, "off")
        if name in COLOR_KEY_BY_INDEX[1:]:
            color_index = COLOR_KEY_BY_INDEX[1:].index(name)
        self.row_light_color.set_selected(color_index)
        self.row_light_color.set_sensitive(mode == 1)
        self.row_auto_off.set_active(bool(light & LED_AUTO_OFF))
        try:
            page = self.stack.get_page(self.stack.get_child_by_name("lighting"))
            page.set_visible(bool(devices.for_state(state).light))
        except (AttributeError, TypeError):
            pass

    def _on_reveal_esb(self, button) -> None:
        self._esb_revealed = button.get_active()
        button.set_label("Hide" if self._esb_revealed else "Show")
        self.row_esb.set_subtitle(
            self._esb_value if self._esb_revealed and self._esb_value else ("••••••••" if self._esb_value else "—")
        )

    # ------------------------------------------------------------ handlers
    def _current_caps(self):
        return devices.for_state(self._state) if self._state else devices.for_product(0)

    def _polling_text(self, hz: int) -> str:
        return self._current_caps().polling_label(hz)

    def _power_text(self, state: MouseState, caps) -> str:
        modes = caps.power_modes
        if modes and 0 <= state.power_mode < len(modes):
            return modes[state.power_mode]
        return "Not mapped for this model"

    def _schedule_write(self) -> None:
        if self._edit_timer:
            GLib.source_remove(self._edit_timer)
        self._edit_timer = GLib.timeout_add(260, self._commit_edit)

    def _commit_edit(self) -> bool:
        self._edit_timer = 0
        if self._state:
            self._write(self._state)
        return False

    def _write(self, state: MouseState, toast: str | None = None) -> None:
        self.worker.submit(state)

    def on_write_result(self, ok: bool, message: str) -> None:
        self.toast_overlay.add_toast(Adw.Toast.new(message))
        if not ok:
            self.worker.refresh()

    def show_toast(self, message: str) -> None:
        self.toast_overlay.add_toast(Adw.Toast.new(message))

    def _on_restore_clicked(self, _button) -> None:
        dialog = Adw.AlertDialog(
            heading="Restore detected settings?",
            body=(
                "This sends the settings that were read when the mouse connected. "
                "Changes made since then will be overwritten. It does not perform "
                "a factory reset."
            ),
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("restore", "Restore")
        dialog.set_response_appearance("restore", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        dialog.connect("response", self._on_restore_response)
        dialog.present(self)

    def _on_restore_response(self, _dialog, response: str) -> None:
        if response != "restore":
            return
        if not self.worker.restore_baseline():
            self.show_toast("No detected settings snapshot is available")

    def _on_polling_selected(self, row, _pspec) -> None:
        if self._loading or not self._state:
            return
        caps = self._current_caps()
        rates = devices.effective_polling_rates(self._state)
        index = row.get_selected()
        if 0 <= index < len(rates):
            hz = rates[index]
            if hz != self._state.polling_rate:
                self._state.polling_rate = hz
                self._write(self._state, f"Polling rate: {caps.polling_label(hz)}")

    def _on_motion_toggled(self, row, _pspec) -> None:
        if self._loading or not self._state:
            return
        self._state.motion_sync = 1 if row.get_active() else 0
        self._write(self._state, "Motion sync " + ("on" if self._state.motion_sync else "off"))

    def _on_snapping_toggled(self, row, _pspec) -> None:
        if self._loading or not self._state:
            return
        self._state.angle_snapping = 1 if row.get_active() else 0
        self._write(self._state, "Angle snapping " + ("on" if self._state.angle_snapping else "off"))

    def _on_ripple_toggled(self, row, _pspec) -> None:
        if self._loading or not self._state:
            return
        self._state.ripple_control = 1 if row.get_active() else 0
        self._write(self._state, "Ripple control " + ("on" if self._state.ripple_control else "off"))

    def _on_turbo_toggled(self, row, _pspec) -> None:
        if self._loading or not self._state:
            return
        self._state.tx_output_power = 8 if row.get_active() else 0
        self._write(
            self._state,
            "Wireless turbo " + ("on" if row.get_active() else "off"),
        )

    def _on_key_selected(self, row, _pspec) -> None:
        if self._loading or not self._state:
            return
        self._key_index = row.get_selected()
        self._loading = True
        try:
            self._update_key_delay(self._state)
        finally:
            self._loading = False

    def _write_key_delay(self, index: int, value: int) -> None:
        if not self._state or index >= len(self._state.key_delay):
            return
        if self._state.key_delay[index] == value:
            return
        self._state.key_delay[index] = value & 0xFF
        self._schedule_write()

    def _on_press_changed(self, row, _pspec) -> None:
        if self._loading or not self._state:
            return
        index = max(0, min(self._key_index, len(self._state.key_delay) - 1))
        byte = (self._state.key_delay[index] & 0xF0) | (int(round(row.get_value())) & 0x0F)
        self._write_key_delay(index, byte)

    def _on_release_changed(self, row, _pspec) -> None:
        if self._loading or not self._state:
            return
        index = max(0, min(self._key_index, len(self._state.key_delay) - 1))
        byte = ((int(round(row.get_value())) & 0x0F) << 4) | (self._state.key_delay[index] & 0x0F)
        self._write_key_delay(index, byte)

    def _on_glass_toggled(self, row, _pspec) -> None:
        if self._loading or not self._state:
            return
        self._state.glass_mode_enabled = 1 if row.get_active() else 0
        self._write(self._state, "Glass mode " + ("on" if row.get_active() else "off"))

    def _on_angle_changed(self, scale) -> None:
        if self._loading or not self._state:
            return
        if self._angle_timer:
            GLib.source_remove(self._angle_timer)
        value = int(round(scale.get_value()))
        self._angle_timer = GLib.timeout_add(260, self._commit_angle, value)

    def _commit_angle(self, value: int) -> bool:
        self._angle_timer = 0
        if self._state and self._state.angle_tuning != value:
            self._state.angle_tuning = value
            self._write(self._state, f"Angle tuning: {value}°")
        return False

    def _on_lod_selected(self, row, _pspec) -> None:
        if self._loading or not self._state:
            return
        value = row.get_selected() + 1
        if value != self._state.lod:
            self._state.lod = value
            self._write(self._state, f"LOD: {self._current_caps().lod_label(value)}")

    def _on_power_selected(self, row, _pspec) -> None:
        if self._loading or not self._state:
            return
        modes = self._current_caps().power_modes
        index = row.get_selected()
        if not modes:
            # The row is hidden for unmapped models; restore any programmatic change.
            self._loading = True
            try:
                row.set_selected(max(0, min(3, self._state.power_mode)))
            finally:
                self._loading = False
            return
        if 0 <= index < len(modes) and index != self._state.power_mode:
            self._state.power_mode = index
            self._loading = True
            try:
                self._update_polling_combo(self._state, self._current_caps())
            finally:
                self._loading = False
            self._write(self._state, f"Power mode: {modes[index]}")

    def _on_sleep_changed(self, row, _pspec) -> None:
        if self._loading or not self._state:
            return
        minutes = int(round(row.get_value()))
        seconds = max(60, minutes * 60)
        if abs(seconds - self._state.sleep_time) >= 30:
            self._state.sleep_time = seconds
            self.worker.submit_sleep_time(seconds)

    def _on_cpi_changed(self, row, _pspec) -> None:
        if self._loading or not self._state:
            return
        value = int(round(row.get_value()))
        caps = self._current_caps()
        value = max(caps.cpi_range[0], min(caps.cpi_range[1], value))
        if value != self._state.cpi:
            self._state.cpi = value
            self._schedule_write()

    def _on_level_changed(self, spin, index: int) -> None:
        if self._loading or not self._state:
            return
        value = int(round(spin.get_value()))
        if index < len(self._state.cpi_levels) and self._state.cpi_levels[index] != value:
            self._state.cpi_levels[index] = value
            self._schedule_write()

    def _on_level_color_changed(self, combo, _pspec, index: int) -> None:
        if self._loading or not self._state:
            return
        key = COLOR_KEY_BY_INDEX[combo.get_selected()]
        bits = COLOR_BITS[key]
        if index < len(self._state.cpi_level_colors) and self._state.cpi_level_colors[index] != bits:
            self._state.cpi_level_colors[index] = bits
            self._write(self._state, f"Level {index + 1} colour: {COLOR_NAMES[combo.get_selected()]}")

    def _apply_light(self, toast: str) -> None:
        if not self._state:
            return
        self._state.light = (self._state.light & ~LED_FLAG) | LED_FLAG
        self._write(self._state, toast)

    def _on_light_mode_changed(self, row, _pspec) -> None:
        if self._loading or not self._state:
            return
        mode = row.get_selected()
        light = self._state.light & ~LED_FLAG
        if mode == 0:
            light = (light & ~LED_RGB_MASK) | LED_CPI
        elif mode == 1:
            light = (light & ~LED_CPI) | (light & LED_RGB_MASK or COLOR_BITS["red"])
        else:
            light = light & ~(LED_CPI | LED_RGB_MASK)
        self._state.light = light
        self.row_light_color.set_sensitive(mode == 1)
        self._apply_light("LED mode updated")

    def _on_light_color_changed(self, combo, _pspec) -> None:
        if self._loading or not self._state:
            return
        key = COLOR_KEY_BY_INDEX[combo.get_selected() + 1]
        bits = COLOR_BITS[key] or COLOR_BITS["off"]
        self._state.light = (self._state.light & ~(LED_RGB_MASK | LED_CPI)) | bits
        self._apply_light(f"LED colour: {COLOR_NAMES[combo.get_selected() + 1]}")

    def _on_auto_off_toggled(self, row, _pspec) -> None:
        if self._loading or not self._state:
            return
        if row.get_active():
            self._state.light |= LED_AUTO_OFF
        else:
            self._state.light &= ~LED_AUTO_OFF
        self._apply_light("Auto-off " + ("enabled" if row.get_active() else "disabled"))

    # -- actions used by the tray -----------------------------------------
    def tray_set_polling(self, hz: int) -> None:
        if self._state and hz != self._state.polling_rate:
            self._state.polling_rate = hz
            self._write(self._state, f"Polling rate: {self._current_caps().polling_label(hz)}")

    def tray_toggle_motion_sync(self, enabled: bool) -> None:
        if self._state:
            self._state.motion_sync = 1 if enabled else 0
            self._write(self._state, "Motion sync " + ("on" if enabled else "off"))

    def tray_toggle_snapping(self, enabled: bool) -> None:
        if self._state:
            self._state.angle_snapping = 1 if enabled else 0
            self._write(self._state, "Angle snapping " + ("on" if enabled else "off"))
