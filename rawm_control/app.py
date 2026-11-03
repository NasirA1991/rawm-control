"""Application entry point: wires worker, window and tray together."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from . import cli, config  # noqa: E402
from .ui import MainWindow  # noqa: E402
from .worker import DeviceWorker  # noqa: E402


def data_dir() -> Path:
    env = os.environ.get("RAWM_CONTROL_DATA")
    if env:
        return Path(env)
    local = Path(__file__).resolve().parent.parent / "data"
    if local.exists():
        return local
    return Path("/usr/share/rawm-control")


class RawmApplication(Adw.Application):
    def __init__(self, start_hidden: bool = False, use_tray: bool = True, page: str | None = None, demo: bool = False) -> None:
        super().__init__(
            application_id=config.APP_ID,
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        self.start_hidden = start_hidden
        self.use_tray = use_tray
        self.page = page
        self.demo = demo
        self.window: MainWindow | None = None
        self.tray: Tray | None = None
        self.worker: DeviceWorker | None = None
        self._held = False
        self._quitting = False
        self._low_battery_notified = False
        self._activated_once = False
        GLib.set_application_name(config.APP_NAME)
        GLib.set_prgname("rawm-control")
        self.connect("startup", self._on_startup)
        self.connect("activate", self._on_activate)

    # -- startup -----------------------------------------------------------
    def _on_startup(self, _app) -> None:
        self._install_icon_path()
        self._add_actions()

        if self.demo:
            from .worker import DemoWorker

            self.worker = DemoWorker(self._state_from_thread, self._link_from_thread)
        else:
            self.worker = DeviceWorker(self._state_from_thread, self._link_from_thread)
        self.worker.start()

        if not self.use_tray:
            return
        try:
            from .tray import Tray

            tray = Tray(
                app_name=config.APP_NAME,
                on_open=self._show_window,
                on_quit=self._quit,
                on_refresh=self._refresh,
                on_polling=lambda hz: self._on_ui(self._tray_polling, hz),
                on_cpi=lambda dpi: self._on_ui(self._tray_cpi, dpi),
                on_motion_sync=lambda enabled: self._on_ui(self._tray_motion, enabled),
                on_snapping=lambda enabled: self._on_ui(self._tray_snapping, enabled),
                style=self._initial_tray_style(),
                on_style_selected=lambda style: self._on_ui(self._apply_tray_style, style),
            )
            if tray.start():
                self.tray = tray
                self.hold()
                self._held = True
        except Exception as exc:  # tray is optional
            print(f"rawm-control: tray unavailable: {exc}", file=sys.stderr)

    def _install_icon_path(self) -> None:
        display = Gdk.Display.get_default()
        if display is not None:
            theme = Gtk.IconTheme.get_for_display(display)
            icons = data_dir() / "icons"
            if icons.exists():
                theme.add_search_path(str(icons))
        Gtk.Window.set_default_icon_name("rawm-control")

    def _add_actions(self) -> None:
        actions = [
            ("refresh", lambda *_: self._refresh()),
            ("quit", lambda *_: self._quit()),
            ("show", lambda *_: self._show_window()),
            ("about", lambda *_: self._about()),
            ("web-driver", lambda *_: self._open_web_driver()),
        ]
        for name, callback in actions:
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            self.add_action(action)

        style_action = Gio.SimpleAction.new_stateful(
            "tray-style",
            GLib.VariantType.new("s"),
            GLib.Variant.new_string(self._initial_tray_style()),
        )
        style_action.connect("activate", self._on_tray_style_action)
        self.add_action(style_action)

        autostart = Gio.SimpleAction.new_stateful(
            "autostart",
            None,
            GLib.Variant.new_boolean(config.is_autostart_enabled()),
        )
        autostart.connect("activate", self._toggle_autostart)
        self.add_action(autostart)

        self.set_accels_for_action("app.quit", ["<Control>q"])
        self.set_accels_for_action("app.refresh", ["<Control>r"])

    # -- activation --------------------------------------------------------
    def _on_activate(self, _app) -> None:
        self._ensure_window()
        assert self.window is not None
        first = not self._activated_once
        self._activated_once = True
        # A first launch with --tray (or "start hidden") stays in the tray.
        # Later activations - e.g. the user launching rawm-control again - must
        # raise the existing window instead of silently doing nothing.
        if first and (self.start_hidden or config.load().get("start_hidden")):
            if self.tray is not None:
                return
        self.window.set_visible(True)
        self.window.present()

    def _ensure_window(self) -> MainWindow:
        if self.window is None:
            assert self.worker is not None
            self.window = MainWindow(self.worker, initial_page=self.page)
            self.window.set_icon_name("rawm-control")
            self.window.connect("close-request", self._on_close_request)
            self.add_window(self.window)
            # replay current state in case the device connected before the window existed
            if self.worker is not None:
                self.window.on_link(self.worker.connected, None)
                if self.worker.connected:
                    self.window.on_state(self.worker.state, set())
        return self.window

    def _on_close_request(self, _window) -> bool:
        if self.tray is not None and not self._quitting:
            self.window.set_visible(False)
            return True
        return False

    # -- thread -> main loop dispatch -------------------------------------
    def _on_ui(self, callback, *args) -> None:
        GLib.idle_add(lambda: (callback(*args), False)[1])

    def _state_from_thread(self, state, changed) -> None:
        GLib.idle_add(self._apply_state, state, changed)

    def _link_from_thread(self, connected: bool, error: str | None) -> None:
        GLib.idle_add(self._apply_link, connected, error)

    def _apply_state(self, state, changed) -> bool:
        if self.window is not None:
            self.window.on_state(state, changed)
        if self.tray is not None:
            self.tray.update(state, True)
        if (
            state.battery <= 15
            and not state.charging
            and config.load().get("low_battery_notifications", True)
            and not self._low_battery_notified
        ):
            self._low_battery_notified = True
            note = Gio.Notification.new(f"{state.device_name or 'RAWM mouse'} battery low")
            note.set_body(f"{state.battery}% remaining — time to charge.")
            note.set_icon(Gio.ThemedIcon.new("battery-low-symbolic"))
            self.send_notification("low-battery", note)
        elif state.battery > 20 or state.charging:
            self._low_battery_notified = False
        self._activated_once = False
        return False

    def _apply_link(self, connected: bool, error: str | None) -> bool:
        if self.window is not None:
            self.window.on_link(connected, error)
        if self.tray is not None:
            self.tray.update(None if not connected else self.worker.state, connected, error)
        return False

    # -- tray callbacks ----------------------------------------------------
    def _mutate_remote_state(self, mutate) -> None:
        """Apply a tray action through the worker without needing a window."""
        if self.worker is None or not self.worker.connected:
            return
        state = self.worker.state
        mutate(state)
        self.worker.submit(state)

    def _tray_polling(self, hz: int) -> None:
        self._mutate_remote_state(lambda st: setattr(st, "polling_rate", hz))

    def _tray_cpi(self, dpi: int) -> None:
        self._mutate_remote_state(lambda st: setattr(st, "cpi", dpi))

    def _tray_motion(self, enabled: bool) -> None:
        self._mutate_remote_state(lambda st: setattr(st, "motion_sync", 1 if enabled else 0))

    def _tray_snapping(self, enabled: bool) -> None:
        self._mutate_remote_state(lambda st: setattr(st, "angle_snapping", 1 if enabled else 0))

    def _show_window(self) -> None:
        window = self._ensure_window()
        window.set_visible(True)
        window.present()
        self.activate()

    def _refresh(self) -> None:
        if self.worker is not None:
            self.worker.refresh()

    def _quit(self) -> None:
        self._quitting = True
        if self.worker is not None:
            self.worker.stop()
        if self._held:
            self.release()
            self._held = False
        self.quit()

    # -- misc --------------------------------------------------------------
    def _about(self) -> None:
        dialog = Adw.AboutDialog(
            application_name=config.APP_NAME,
            application_icon="rawm-control",
            version=config.VERSION,
            developer_name="RAWM Control contributors",
            comments=(
                "Native Linux configuration tool for RAWM mice, built by "
                "reverse-engineering the RAWM HUB vendor HID protocol. "
                "Not affiliated with RAWM / MiraclTek."
            ),
            website="https://github.com/",
            license_type=Gtk.License.MIT_X11,
        )
        dialog.present(self.window)

    def _open_web_driver(self) -> None:
        launcher = Gtk.UriLauncher.new("https://rawmtech.com/hub.html")
        launcher.launch(self.window, None, None)

    def _initial_tray_style(self) -> str:
        settings = config.load()
        style = settings.get("tray_icon_style")
        if style not in dict(config.TRAY_STYLES):
            # migrate the old boolean preference
            style = "ring" if settings.get("tray_percent", True) else "mouse"
        return style

    def _on_tray_style_action(self, _action, parameter) -> None:
        if parameter is not None:
            self._apply_tray_style(parameter.get_string())

    def _apply_tray_style(self, style: str) -> None:
        if style not in dict(config.TRAY_STYLES):
            return
        settings = config.load()
        settings["tray_icon_style"] = style
        settings["tray_percent"] = style != "mouse"
        config.save(settings)
        action = self.lookup_action("tray-style")
        if action is not None and action.get_state().get_string() != style:
            action.set_state(GLib.Variant.new_string(style))
        if self.tray is not None:
            self.tray.set_style(style)

    def _toggle_autostart(self, action, _param) -> None:
        enabled = not action.get_state().get_boolean()
        config.set_autostart(enabled)
        action.set_state(GLib.Variant.new_boolean(enabled))


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    args = argv[1:]
    start_hidden = "--tray" in args or "--minimized" in args
    page = None
    if "--page" in args:
        try:
            page = args[args.index("--page") + 1]
        except IndexError:
            page = None

    if args and args[0] in ("--version", "-V"):
        print(f"rawm-control {config.VERSION}")
        return 0
    if args and args[0] == "--cli":
        return cli.run(args[1:])
    if args and args[0] in cli.CLI_COMMANDS:
        return cli.run(args)
    if args and args[0] in ("-h", "--help"):
        print("Usage: rawm-control [--tray] [--cli <command>]")
        print("       rawm-control <status|scan|caps|polling|motion-sync|dpi|lod|power|sleep> ...\n")
        cli.build_parser().print_help()
        return 0

    app = RawmApplication(
        start_hidden=start_hidden,
        use_tray="--no-tray" not in args,
        page=page,
        demo="--demo" in args,
    )
    filtered = [argv[0]]
    skip = False
    for a in args:
        if skip:
            skip = False
            continue
        if a == "--page":
            skip = True
            continue
        if a in ("--tray", "--minimized", "--no-tray", "--demo"):
            continue
        filtered.append(a)
    return app.run(filtered)
