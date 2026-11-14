"""StatusNotifierItem tray icon with a quick-action menu.

Implemented directly on DBus (KDE, GNOME with AppIndicator extension, XFCE,
swaybar, waybar, ...) so the GTK4 process never has to load GTK3 libraries.
"""

from __future__ import annotations

import logging
import math
import os
from typing import Callable

logger = logging.getLogger(__name__)

import cairo
import dbus
import dbus.service
import dbus.mainloop.glib
from dbus.mainloop.glib import DBusGMainLoop

from . import devices
from .protocol import LED_AUTO_OFF, LED_CPI, LED_RGB_MASK, MouseState

SNI_IFACE = "org.kde.StatusNotifierItem"
MENU_IFACE = "com.canonical.dbusmenu"
WATCHER = "org.kde.StatusNotifierWatcher"
WATCHER_PATH = "/StatusNotifierWatcher"

ID_STATUS = 1
ID_SEP1 = 2
ID_POLLING = 3
ID_DPI = 10
# Keep large gaps between ID ranges.  Menu IDs are internal, but a range must
# never overlap another even if a future model exposes hundreds of rates.
ID_POLLING_BASE = 100
ID_DPI_BASE = 1000
ID_STYLE_BASE = 2000
ID_CATEGORY = 12
ID_CATEGORY_BASE = 2100
ID_MOTION = 4
ID_SNAPPING = 5
ID_SEP2 = 6
ID_STYLE = 11
ID_OPEN = 7
ID_REFRESH = 8
ID_QUIT = 9

ICON_SIZE = 64
TRAY_ICON_SIZES = (22, 32, 48, 64)


def _argb_pixmap(surface: cairo.ImageSurface) -> list[tuple[int, int, bytes]]:
    """Convert a cairo surface to SNI's a(iiay) ARGB32 network-order form."""
    surface.flush()
    data = bytes(surface.get_data())
    width, height = surface.get_width(), surface.get_height()
    stride = surface.get_stride()
    out = bytearray(width * height * 4)
    for y in range(height):
        row = data[y * stride : y * stride + width * 4]
        for x in range(width):
            b, g, r, a = row[x * 4 : x * 4 + 4]
            out[(y * width + x) * 4 : (y * width + x) * 4 + 4] = bytes((a, r, g, b))
    return [(width, height, bytes(out))]


from .config import (
    DEFAULT_TRAY_CATEGORY,
    DEFAULT_TRAY_STYLE,
    TRAY_CATEGORIES,
    TRAY_STYLES,
)

STYLE_KEYS = [key for key, _label in TRAY_STYLES]
CATEGORY_KEYS = [key for key, _label in TRAY_CATEGORIES]


def _accent(state: MouseState | None, connected: bool):
    """(colour, level, charging, text) for the current device state."""
    if not connected or state is None:
        return (0.55, 0.55, 0.58), 0, False, "—"
    level = max(0, min(100, state.battery))
    charging = bool(state.charging)
    if charging:
        accent = (0.35, 0.72, 1.0)
    elif level > 40:
        accent = (0.30, 0.86, 0.46)
    elif level > 20:
        accent = (0.98, 0.74, 0.18)
    else:
        accent = (0.95, 0.32, 0.32)
    return accent, level, charging, str(level)


def _text(ctx, value, cx, cy, size, color=(1, 1, 1), outline=(0.02, 0.03, 0.05), outline_w=2.6):
    ctx.select_font_face("DejaVu Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    ctx.set_font_size(size)
    ext = ctx.text_extents(value)
    x = cx - ext.width / 2 - ext.x_bearing
    y = cy - ext.height / 2 - ext.y_bearing
    ctx.move_to(x, y)
    ctx.text_path(value)
    ctx.set_line_width(outline_w)
    ctx.set_source_rgba(*outline, 0.9)
    ctx.stroke_preserve()
    ctx.set_source_rgba(*color, 1.0)
    ctx.fill()


def _canvas(size: int = ICON_SIZE):
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    ctx = cairo.Context(surface)
    # All icon coordinates are authored on a 64 px grid.
    ctx.scale(size / ICON_SIZE, size / ICON_SIZE)
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    ctx.set_line_join(cairo.LINE_JOIN_ROUND)
    return surface, ctx


def _charging_bolt(ctx: cairo.Context, cx: float, cy: float, radius: float = 9.0) -> None:
    """A shape, not just a colour change, so charging is visible/accessibility-safe."""
    ctx.arc(cx, cy, radius, 0, 2 * math.pi)
    ctx.set_source_rgba(0.02, 0.03, 0.05, 0.96)
    ctx.fill()
    ctx.set_line_width(1.4)
    ctx.set_source_rgba(1.0, 1.0, 1.0, 0.95)
    ctx.stroke()
    ctx.move_to(cx + 1.0, cy - 6.0)
    ctx.line_to(cx - 4.2, cy + 0.8)
    ctx.line_to(cx - 0.7, cy + 0.8)
    ctx.line_to(cx - 1.0, cy + 6.0)
    ctx.line_to(cx + 4.2, cy - 1.2)
    ctx.line_to(cx + 0.7, cy - 1.2)
    ctx.close_path()
    ctx.set_source_rgba(1.0, 1.0, 1.0, 1.0)
    ctx.fill()


def render_mouse_icon(
    state: MouseState | None,
    connected: bool,
    size: int = ICON_SIZE,
    show_battery: bool = True,
) -> list[tuple[int, int, bytes]]:
    """Mouse glyph with a small battery column (no digits)."""
    surface, ctx = _canvas(size)
    accent, level, charging, _text_value = _accent(state, connected)
    fg = (1.0, 1.0, 1.0) if connected else (0.62, 0.62, 0.66)
    body_fill = (0.22, 0.47, 0.88) if connected else (0.42, 0.44, 0.50)

    ctx.set_line_width(3.0)
    _rounded_rect(ctx, 17.5, 5.5, 29.0, 53.0, 13.5)
    ctx.set_source_rgba(*body_fill, 0.95)
    ctx.fill_preserve()
    ctx.set_source_rgba(1.0, 1.0, 1.0, 0.92)
    ctx.stroke()

    ctx.set_source_rgba(1.0, 1.0, 1.0, 0.75)
    ctx.set_line_width(2.0)
    ctx.move_to(18.5, 21.5)
    ctx.line_to(45.5, 21.5)
    ctx.stroke()
    ctx.set_source_rgba(1.0, 1.0, 1.0, 0.92)
    _rounded_rect(ctx, 29.0, 11.0, 6.0, 9.0, 3.0)
    ctx.fill()

    if connected and show_battery:
        bar_x, bar_y, bar_w, bar_h = 23.0, 28.0, 18.0, 26.0
        ctx.set_source_rgba(0.03, 0.06, 0.12, 0.42)
        _rounded_rect(ctx, bar_x, bar_y, bar_w, bar_h, 4.0)
        ctx.fill()
        fill_h = bar_h * level / 100.0
        if fill_h > 0.5:
            ctx.set_source_rgba(*accent, 1.0)
            _rounded_rect(ctx, bar_x, bar_y + bar_h - fill_h, bar_w, fill_h, 3.0)
            ctx.fill()
    else:
        ctx.set_source_rgba(1.0, 1.0, 1.0, 0.55)
        ctx.set_line_width(2.4)
        ctx.move_to(31.0, 32.0)
        ctx.line_to(37.0, 38.0)
        ctx.move_to(37.0, 32.0)
        ctx.line_to(31.0, 38.0)
        ctx.stroke()
    if charging:
        _charging_bolt(ctx, 50.0, 13.0, 9.0)
    return _argb_pixmap(surface)


def render_ring_icon(state: MouseState | None, connected: bool, size: int = ICON_SIZE) -> list[tuple[int, int, bytes]]:
    """Progress ring around a mouse glyph with the percentage inside."""
    surface, ctx = _canvas(size)
    accent, level, charging, value = _accent(state, connected)

    ctx.set_source_rgba(0.045, 0.055, 0.075, 0.95)
    ctx.arc(32.0, 32.0, 30.0, 0, 2 * math.pi)
    ctx.fill()

    radius = 27.0
    ctx.set_line_width(4.6)
    ctx.set_source_rgba(1, 1, 1, 0.16)
    ctx.arc(32.0, 32.0, radius, 0, 2 * math.pi)
    ctx.stroke()
    if level:
        start_angle = -math.pi / 2
        ctx.set_source_rgba(*accent, 0.98)
        ctx.arc(32.0, 32.0, radius, start_angle, start_angle + 2 * math.pi * level / 100)
        ctx.stroke()

    ctx.set_line_width(2.2)
    ctx.set_source_rgba(1, 1, 1, 0.92)
    _rounded_rect(ctx, 18.5, 13.5, 27.0, 35.0, 10.0)
    ctx.stroke()
    ctx.set_source_rgba(1, 1, 1, 0.9)
    _rounded_rect(ctx, 29.5, 18.0, 5.0, 7.0, 2.5)
    ctx.fill()
    _text(ctx, value, 32.0, 38.5, 19.0 if len(value) <= 2 else 13.0)
    if charging:
        _charging_bolt(ctx, 51.0, 13.0, 8.0)
    return _argb_pixmap(surface)


def render_number_icon(state: MouseState | None, connected: bool, size: int = ICON_SIZE) -> list[tuple[int, int, bytes]]:
    """Large percentage only.  The most readable style on tiny panels."""
    surface, ctx = _canvas(size)
    accent, level, charging, value = _accent(state, connected)

    _rounded_rect(ctx, 3.0, 3.0, 58.0, 58.0, 15.0)
    ctx.set_source_rgba(0.045, 0.055, 0.075, 0.96)
    ctx.fill_preserve()
    ctx.set_line_width(3.0)
    ctx.set_source_rgba(*accent, 0.95)
    ctx.stroke()

    font_size = 36.0 if len(value) <= 2 else 26.0
    _text(ctx, value, 32.0, 33.0, font_size, (1, 1, 1), (0.02, 0.03, 0.05), 1.6)
    if charging:
        _charging_bolt(ctx, 52.0, 51.0, 8.0)
    return _argb_pixmap(surface)


def render_battery_icon(state: MouseState | None, connected: bool, size: int = ICON_SIZE) -> list[tuple[int, int, bytes]]:
    """Classic battery outline with the percentage inside."""
    surface, ctx = _canvas(size)
    accent, level, charging, value = _accent(state, connected)

    body = (9.0, 14.0, 46.0, 40.0, 9.0)
    ctx.set_line_width(3.4)
    _rounded_rect(ctx, *body)
    ctx.set_source_rgba(0.045, 0.055, 0.075, 0.9)
    ctx.fill_preserve()
    ctx.set_source_rgba(1, 1, 1, 0.92)
    ctx.stroke()

    ctx.set_source_rgba(1, 1, 1, 0.92)
    _rounded_rect(ctx, 26.0, 6.0, 12.0, 9.0, 3.0)
    ctx.fill()

    if level:
        ctx.save()
        _rounded_rect(ctx, 9.0, 14.0, 46.0, 40.0, 9.0)
        ctx.clip()
        fill_h = 38.0 * level / 100.0
        ctx.set_source_rgba(*accent, 0.58)
        ctx.rectangle(9.0, 52.0 - fill_h, 46.0, fill_h)
        ctx.fill()
        ctx.restore()

    _text(ctx, value, 32.0, 34.0, 28.0 if len(value) <= 2 else 20.0)
    if charging:
        _charging_bolt(ctx, 52.0, 12.0, 8.0)
    return _argb_pixmap(surface)


def render_sidecar_icon(state: MouseState | None, connected: bool, size: int = ICON_SIZE) -> list[tuple[int, int, bytes]]:
    """Narrow mouse glyph with a big percentage beside it."""
    surface, ctx = _canvas(size)
    accent, level, charging, value = _accent(state, connected)

    ctx.set_line_width(2.7)
    ctx.set_source_rgba(1, 1, 1, 0.92)
    _rounded_rect(ctx, 2.0, 6.0, 27.0, 52.0, 11.0)
    ctx.stroke()
    ctx.set_source_rgba(1, 1, 1, 0.9)
    _rounded_rect(ctx, 13.0, 10.0, 5.0, 8.0, 2.5)
    ctx.fill()
    _text(ctx, value, 46.0, 32.0, 30.0 if len(value) <= 2 else 21.0, accent, (0.02, 0.03, 0.05), 3.0)
    if charging:
        _charging_bolt(ctx, 8.0, 52.0, 8.0)
    return _argb_pixmap(surface)


_RENDERERS = {
    "ring": render_ring_icon,
    "number": render_number_icon,
    "battery": render_battery_icon,
    "sidecar": render_sidecar_icon,
    "mouse": render_mouse_icon,
}


def render_tray_icon(state: MouseState | None, connected: bool, style: str = DEFAULT_TRAY_STYLE):
    return _RENDERERS.get(style, render_ring_icon)(state, connected)


def render_tray_icon_sizes(
    state: MouseState | None,
    connected: bool,
    style: str = DEFAULT_TRAY_STYLE,
    sizes: tuple[int, ...] = TRAY_ICON_SIZES,
    show_battery: bool = True,
) -> list[tuple[int, int, bytes]]:
    renderer = _RENDERERS.get(style, render_ring_icon)
    out: list[tuple[int, int, bytes]] = []
    for size in sizes:
        if renderer is render_mouse_icon:
            out.extend(renderer(state, connected, size, show_battery=show_battery))
        else:
            out.extend(renderer(state, connected, size))
    return out


# backwards-compatible helpers
def render_icon(state: MouseState | None, connected: bool, show_percent: bool = False):
    return render_tray_icon(state, connected, "ring" if show_percent else "mouse")


def render_percent_icon(state: MouseState | None, connected: bool):
    return render_ring_icon(state, connected)


def _rounded_rect(ctx: cairo.Context, x: float, y: float, w: float, h: float, r: float) -> None:
    r = min(r, w / 2, h / 2)
    ctx.new_sub_path()
    ctx.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    ctx.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    ctx.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    ctx.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    ctx.close_path()


class Tray(dbus.service.Object):
    """SNI item + DBusMenu."""

    def __init__(
        self,
        app_name: str,
        on_open: Callable[[], None],
        on_quit: Callable[[], None],
        on_refresh: Callable[[], None],
        on_polling: Callable[[int], None],
        on_cpi: Callable[[int], None],
        on_motion_sync: Callable[[bool], None],
        on_snapping: Callable[[bool], None],
        style: str = DEFAULT_TRAY_STYLE,
        on_style_selected: Callable[[str], None] | None = None,
        category: str = DEFAULT_TRAY_CATEGORY,
        on_category_selected: Callable[[str], None] | None = None,
    ) -> None:
        DBusGMainLoop(set_as_default=True)
        self.bus = dbus.SessionBus()
        self.app_name = app_name
        self.on_open = on_open
        self.on_quit = on_quit
        self.on_refresh = on_refresh
        self.on_polling = on_polling
        self.on_cpi = on_cpi
        self.on_motion_sync = on_motion_sync
        self.on_snapping = on_snapping
        self.style = style if style in STYLE_KEYS else DEFAULT_TRAY_STYLE
        self.category = category if category in CATEGORY_KEYS else DEFAULT_TRAY_CATEGORY
        self.on_style_selected = on_style_selected
        self.on_category_selected = on_category_selected
        self.state: MouseState | None = None
        self.connected = False
        self.caps = devices.for_product(0)
        self.revision = 1
        self._status_text = "Not connected"
        # Passive lets hosts that use "show when relevant" hide the item while
        # no mouse is connected; it becomes Active as soon as one is present.
        self.sni_status = "Passive"
        self.polling_rates = [125, 250, 500, 1000]
        self._icon = render_tray_icon_sizes(
            None, False, self.style, show_battery=self.caps.battery
        )

        # Flatpak does not allow owning the conventional PID-based SNI name
        # (wildcards are invalid), so inside the sandbox use a name derived from
        # the app ID.  SNI hosts accept any registered service name.
        flatpak_id = os.environ.get("FLATPAK_ID")
        if flatpak_id:
            sni_name = f"{flatpak_id}.StatusNotifierItem"
        else:
            sni_name = f"org.kde.StatusNotifierItem-{os.getpid()}-1"
        self.bus_name = dbus.service.BusName(sni_name, self.bus, do_not_queue=True)
        dbus.service.Object.__init__(self, self.bus_name, "/StatusNotifierItem")
        self.menu = TrayMenu(self)

    # -- public ------------------------------------------------------------
    def start(self) -> bool:
        try:
            watcher = self.bus.get_object(WATCHER, WATCHER_PATH)
            watcher.RegisterStatusNotifierItem(
                self.bus_name.get_name(), dbus_interface=WATCHER
            )
        except dbus.DBusException as exc:
            logger.warning("StatusNotifier watcher unavailable: %s", exc)
            return False
        return True

    def update(self, state: MouseState | None, connected: bool, message: str | None = None) -> None:
        self.state = state
        self.connected = connected
        if state is not None:
            self.caps = devices.for_state(state)
            self.polling_rates = devices.effective_polling_rates(state)
            link = "USB" if state.wired else ("2.4 GHz via receiver" if state.via_receiver else "2.4 GHz")
            charger = ", charging" if state.charging else ""
            if self.caps.battery:
                battery = f"{state.battery}%"
                self._status_text = f"{self.caps.display_name} — {battery} · {link}{charger}"
            else:
                self._status_text = f"{self.caps.display_name} — {link}{charger}"
        else:
            self._status_text = message or "Click to open RAWM Control"
        self.sni_status = "Active" if connected and state is not None else "Passive"
        style = self.style if state is None or self.caps.battery else "mouse"
        self._icon = render_tray_icon_sizes(
            state, connected, style, show_battery=self.caps.battery
        )
        self._emit("NewIcon")
        self._emit("NewToolTip")
        self._emit("NewTitle")
        self.NewStatus(self.sni_status)
        self.menu.refresh()

    def set_category(self, category: str) -> None:
        if category not in CATEGORY_KEYS or category == self.category:
            return
        self.category = category
        # SNI has no NewCategory signal.  Re-registering with the watcher makes
        # Plasma read the new hint; if the host ignores it, the setting still
        # persists and applies on the next launch.
        try:
            watcher = self.bus.get_object(WATCHER, WATCHER_PATH)
            watcher.UnregisterStatusNotifierItem(
                self.bus_name.get_name(), dbus_interface=WATCHER
            )
            watcher.RegisterStatusNotifierItem(
                self.bus_name.get_name(), dbus_interface=WATCHER
            )
        except dbus.DBusException as exc:
            logger.warning("Could not re-register tray category: %s", exc)
        self.menu.refresh()

    def set_style(self, style: str) -> None:
        if style not in STYLE_KEYS or style == self.style:
            return
        self.style = style
        effective = style if self.caps.battery else "mouse"
        self._icon = render_tray_icon_sizes(
            self.state, self.connected, effective, show_battery=self.caps.battery
        )
        self._emit("NewIcon")
        self.menu.refresh()

    def _emit(self, signal: str) -> None:
        getattr(self, signal)()

    # -- SNI properties ----------------------------------------------------
    def _props(self) -> dict[str, object]:
        return {
            "Category": dbus.String(self.category),
            "Id": dbus.String("rawm-control"),
            "Title": dbus.String("RAWM Control"),
            "Status": dbus.String(self.sni_status),
            # Empty on purpose: KDE prefers IconName over IconPixmap when it is
            # set, which would hide the battery percentage drawn in the pixmap.
            "IconName": dbus.String(""),
            "IconPixmap": dbus.Array(
                [
                    dbus.Struct(
                        (dbus.Int32(w), dbus.Int32(h), dbus.ByteArray(pixels)),
                        signature="iiay",
                    )
                    for w, h, pixels in self._icon
                ],
                signature="(iiay)",
            ),
            "ToolTip": dbus.Struct(
                (
                    dbus.String("input-mouse"),
                    dbus.Array([], signature="(iiay)"),
                    dbus.String("RAWM Control"),
                    dbus.String(self._status_text),
                ),
                signature="sa(iiay)ss",
            ),
            # Conventional tray behaviour: primary click opens the window;
            # secondary click uses the host's menu for the Menu property.
            # Setting this true makes hosts show the menu on primary click.
            "ItemIsMenu": dbus.Boolean(False),
            "Menu": dbus.ObjectPath("/MenuBar"),
        }

    @dbus.service.method("org.freedesktop.DBus.Properties", in_signature="ss", out_signature="v")
    def Get(self, interface: str, prop: str):
        if prop in self._props():
            return self._props()[prop]
        raise dbus.exceptions.DBusException("Unknown property", name="org.freedesktop.DBus.Error.InvalidArgs")

    @dbus.service.method("org.freedesktop.DBus.Properties", in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface: str):
        return dbus.Dictionary(self._props(), signature="sv")

    @dbus.service.method("org.freedesktop.DBus.Properties", in_signature="ssv")
    def Set(self, interface: str, prop: str, value) -> None:
        return None

    # -- SNI methods -------------------------------------------------------
    @dbus.service.method(SNI_IFACE, in_signature="ii", out_signature="")
    def Activate(self, x: int, y: int) -> None:
        self.on_open()

    @dbus.service.method(SNI_IFACE, in_signature="ii", out_signature="")
    def SecondaryActivate(self, x: int, y: int) -> None:
        self.on_open()

    @dbus.service.method(SNI_IFACE, in_signature="ii", out_signature="")
    def ContextMenu(self, x: int, y: int) -> None:
        return None

    @dbus.service.method(SNI_IFACE, in_signature="is", out_signature="")
    def Scroll(self, delta: int, orientation: str) -> None:
        return None

    # -- SNI signals -------------------------------------------------------
    @dbus.service.signal(SNI_IFACE, signature="")
    def NewIcon(self) -> None: ...

    @dbus.service.signal(SNI_IFACE, signature="")
    def NewToolTip(self) -> None: ...

    @dbus.service.signal(SNI_IFACE, signature="")
    def NewTitle(self) -> None: ...

    @dbus.service.signal(SNI_IFACE, signature="s")
    def NewStatus(self, status: str) -> None: ...


class TrayMenu(dbus.service.Object):
    def __init__(self, tray: Tray) -> None:
        self.tray = tray
        dbus.service.Object.__init__(self, tray.bus_name, "/MenuBar")

    # -- layout ------------------------------------------------------------
    def _item(self, item_id: int, props: dict, children: list | None = None):
        children = children or []
        return dbus.Struct(
            (
                dbus.Int32(item_id),
                dbus.Dictionary({k: _variant(v) for k, v in props.items()}, signature="sv"),
                dbus.Array(children, signature="v"),
            ),
            signature="ia{sv}av",
        )

    def _layout(self):
        state = self.tray.state
        connected = self.tray.connected and state is not None
        polling_rates = self.tray.polling_rates
        items = [
            self._item(
                ID_STATUS,
                {
                    "label": self.tray._status_text,
                    "enabled": False,
                    "visible": True,
                },
            ),
            self._item(ID_SEP1, {"type": "separator"}),
            self._item(
                ID_POLLING,
                {"label": "Polling rate", "enabled": connected, "children-display": "submenu"},
                [
                    self._item(
                        ID_POLLING_BASE + i,
                        {
                            "label": self.tray.caps.polling_label(hz),
                            "toggle-type": "radio",
                            "toggle-state": 1 if state and state.polling_rate == hz else 0,
                            "enabled": connected,
                        },
                    )
                    for i, hz in enumerate(polling_rates)
                ],
            ),
            self._item(
                ID_DPI,
                {"label": "DPI", "enabled": connected, "children-display": "submenu"},
                [
                    self._item(
                        ID_DPI_BASE + i,
                        {
                            "label": f"{value}",
                            "toggle-type": "radio",
                            "toggle-state": 1 if state and state.cpi == value else 0,
                            "enabled": connected,
                        },
                    )
                    for i, value in enumerate(state.cpi_levels if state else [])
                    if value
                ],
            ),
            self._item(
                ID_MOTION,
                {
                    "label": "Motion sync",
                    "toggle-type": "check",
                    "toggle-state": 1 if state and state.motion_sync else 0,
                    "enabled": connected,
                },
            ),
            self._item(
                ID_SNAPPING,
                {
                    "label": "Angle snapping",
                    "toggle-type": "check",
                    "toggle-state": 1 if state and state.angle_snapping else 0,
                    "enabled": connected,
                },
            ),
            self._item(
                ID_STYLE,
                {"label": "Tray icon", "children-display": "submenu"},
                [
                    self._item(
                        ID_STYLE_BASE + i,
                        {
                            "label": label,
                            "toggle-type": "radio",
                            "toggle-state": 1 if self.tray.style == key else 0,
                        },
                    )
                    for i, (key, label) in enumerate(TRAY_STYLES)
                ],
            ),
            self._item(
                ID_CATEGORY,
                {"label": "Tray category", "children-display": "submenu"},
                [
                    self._item(
                        ID_CATEGORY_BASE + i,
                        {
                            "label": label,
                            "toggle-type": "radio",
                            "toggle-state": 1 if self.tray.category == key else 0,
                        },
                    )
                    for i, (key, label) in enumerate(TRAY_CATEGORIES)
                ],
            ),
            self._item(ID_SEP2, {"type": "separator"}),
            self._item(ID_OPEN, {"label": "Open RAWM Control"}),
            self._item(ID_REFRESH, {"label": "Refresh", "enabled": connected}),
            self._item(ID_QUIT, {"label": "Quit"}),
        ]
        return dbus.Struct(
            (
                dbus.Int32(0),
                dbus.Dictionary({}, signature="sv"),
                dbus.Array(items, signature="v"),
            ),
            signature="ia{sv}av",
        )

    def _find(self, item_id: int):
        """Find an item anywhere in the current tree."""
        def walk(node):
            if int(node[0]) == item_id:
                return node
            for child in node[2]:
                found = walk(child)
                if found is not None:
                    return found
            return None

        return walk(self._layout())

    def _all_items(self) -> list:
        out = []

        def walk(node):
            out.append(node)
            for child in node[2]:
                walk(child)

        walk(self._layout())
        return out

    def refresh(self) -> None:
        self.tray.revision += 1
        try:
            self.LayoutUpdated(dbus.UInt32(self.tray.revision), dbus.Int32(0))
        except dbus.DBusException as exc:
            logger.debug("Could not emit LayoutUpdated: %s", exc)

    # -- DBusMenu API ------------------------------------------------------
    @dbus.service.method(MENU_IFACE, in_signature="iias", out_signature="u(ia{sv}av)")
    def GetLayout(self, parent_id: int, recursion: int, properties: list[str]):
        # KDE asks for a submenu with GetLayout(parent_id, 1, ...); returning
        # the root here makes nested submenus empty or unusable.
        if int(parent_id) in (0, -1):
            node = self._layout()
        else:
            node = self._find(int(parent_id))
            if node is None:
                node = self._item(int(parent_id), {}, [])
        return dbus.UInt32(self.tray.revision), node

    @dbus.service.method(MENU_IFACE, in_signature="aias", out_signature="a(ia{sv})")
    def GetGroupProperties(self, ids: list[int], properties: list[str]):
        if ids:
            items = [item for item_id in ids if (item := self._find(int(item_id))) is not None]
        else:
            items = self._all_items()
        return [dbus.Struct((item[0], item[1]), signature="ia{sv}") for item in items]

    @dbus.service.method(MENU_IFACE, in_signature="is", out_signature="v")
    def GetProperty(self, item_id: int, name: str):
        item = self._layout() if int(item_id) in (0, -1) else self._find(int(item_id))
        if item is not None:
            return item[1].get(name, _variant(False))
        return _variant(False)

    @dbus.service.method(MENU_IFACE, in_signature="isvu", out_signature="")
    def Event(self, item_id: int, event_id: str, data, timestamp: int) -> None:
        if event_id != "clicked":
            return
        if item_id == ID_OPEN:
            self.tray.on_open()
        elif item_id == ID_REFRESH:
            self.tray.on_refresh()
        elif item_id == ID_QUIT:
            self.tray.on_quit()
        elif ID_STYLE_BASE <= item_id < ID_STYLE_BASE + len(TRAY_STYLES):
            style = TRAY_STYLES[item_id - ID_STYLE_BASE][0]
            if self.tray.on_style_selected is not None:
                self.tray.on_style_selected(style)
        elif ID_CATEGORY_BASE <= item_id < ID_CATEGORY_BASE + len(TRAY_CATEGORIES):
            category = TRAY_CATEGORIES[item_id - ID_CATEGORY_BASE][0]
            if self.tray.on_category_selected is not None:
                self.tray.on_category_selected(category)
        elif item_id == ID_MOTION:
            self.tray.on_motion_sync(not bool(self.tray.state and self.tray.state.motion_sync))
        elif item_id == ID_SNAPPING:
            self.tray.on_snapping(not bool(self.tray.state and self.tray.state.angle_snapping))
        elif ID_POLLING_BASE <= item_id < ID_POLLING_BASE + len(self.tray.polling_rates):
            hz = self.tray.polling_rates[item_id - ID_POLLING_BASE]
            self.tray.on_polling(hz)
        elif ID_DPI_BASE <= item_id:
            levels = [v for v in (self.tray.state.cpi_levels if self.tray.state else []) if v]
            index = item_id - ID_DPI_BASE
            if 0 <= index < len(levels):
                self.tray.on_cpi(levels[index])

    @dbus.service.method(MENU_IFACE, in_signature="i", out_signature="b")
    def AboutToShow(self, item_id: int) -> bool:
        # Plasma calls this and expects a bool "needRefresh".  Returning
        # nothing makes the reply invalid, so the menu is never populated.
        return True

    @dbus.service.method(MENU_IFACE, in_signature="ai", out_signature="ai")
    def AboutToShowGroup(self, ids: list[int]):
        return dbus.Array([int(item) for item in ids], signature="i")

    @dbus.service.method("org.freedesktop.DBus.Properties", in_signature="ss", out_signature="v")
    def Get(self, interface: str, prop: str):
        props = {
            "Version": dbus.UInt32(3),
            "TextDirection": dbus.String("ltr"),
            "Status": dbus.String("normal"),
            "IconThemePath": dbus.Array([], signature="s"),
        }
        return props.get(prop, dbus.String(""))

    @dbus.service.method("org.freedesktop.DBus.Properties", in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface: str):
        return dbus.Dictionary(
            {
                "Version": dbus.UInt32(3),
                "TextDirection": dbus.String("ltr"),
                "Status": dbus.String("normal"),
                "IconThemePath": dbus.Array([], signature="s"),
            },
            signature="sv",
        )

    @dbus.service.signal(MENU_IFACE, signature="ui")
    def LayoutUpdated(self, revision: int, parent: int) -> None:
        ...

    @dbus.service.signal(MENU_IFACE, signature="a(ia{sv})a(ias)")
    def ItemsPropertiesUpdated(self, updated, removed) -> None:
        ...


def _variant(value):
    if isinstance(value, bool):
        return dbus.Boolean(value)
    if isinstance(value, int):
        return dbus.Int32(value)
    return dbus.String(str(value))
