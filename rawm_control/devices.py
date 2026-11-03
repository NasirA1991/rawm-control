"""Per-model capabilities, bundled from the vendor's device database.

The official hub fetches this table from ``miracletek.net/game/device.php``.
Shipping a filtered copy keeps the app fully offline and lets the UI expose
only the settings a given mouse actually supports.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .protocol import MouseState

_DATA = Path(__file__).with_name("data") / "devices.json"


@dataclass
class Capabilities:
    product_id: int
    name: str
    display_name: str
    polling_rates: list[int] = field(default_factory=lambda: [125, 250, 500, 1000])
    boost_polling_rates: list[int] = field(default_factory=list)
    polling_rate_max: int = 8000
    cpi_range: tuple[int, int] = (50, 30000)
    cpi_step: int = 50
    power_modes: list[str] = field(default_factory=list)
    lod_names: list[str] = field(default_factory=list)
    angle_tuning: bool = True
    glass_mode: bool = False
    battery: bool = True
    light: bool = True
    receiver: bool = False
    mouse: bool = True
    keyboard: bool = False
    sensor: str = ""
    working_modes: str = "usb,2.4g"

    @property
    def max_polling(self) -> int:
        return max(self.polling_rates) if self.polling_rates else 1000

    def polling_label(self, hz: int) -> str:
        # Always show the raw frequency: 1000 Hz, 2000 Hz, 8000 Hz.
        return f"{hz} Hz"

    def lod_label(self, value: int) -> str:
        idx = value - 1
        if 0 <= idx < len(self.lod_names):
            return f"{self.lod_names[idx].title()} ({value})"
        return str(value)


def _load() -> dict[int, Capabilities]:
    caps: dict[int, Capabilities] = {}
    try:
        raw = json.loads(_DATA.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return caps
    for entry in raw:
        try:
            pid = int(entry["product_id"], 16)
        except (KeyError, TypeError, ValueError):
            continue
        rates = sorted(int(x) for x in entry.get("polling_rates", []) or [])
        boost = sorted(int(x) for x in entry.get("boost_polling_rates", []) or [])
        cpi_range = entry.get("cpi_range") or [50, 30000]
        caps[pid] = Capabilities(
            product_id=pid,
            name=entry.get("name") or f"{pid:04X}",
            display_name=entry.get("display_name") or entry.get("name") or f"RAWM {pid:04X}",
            polling_rates=rates,
            boost_polling_rates=boost,
            polling_rate_max=int(entry.get("polling_rate_max") or 8000),
            cpi_range=(int(cpi_range[0]), int(cpi_range[1])),
            cpi_step=int(entry.get("cpi_step") or 50),
            power_modes=list(entry.get("power_modes2") or entry.get("power_modes") or []),
            lod_names=list(entry.get("lods") or []),
            angle_tuning=bool(entry.get("angle_tuning", False)),
            glass_mode=bool(entry.get("glass_mode", False)),
            battery=bool(entry.get("battery", True)),
            light=bool(entry.get("light", True)),
            receiver=bool(entry.get("receiver", False)),
            mouse=bool(entry.get("mouse", False)),
            keyboard=bool(entry.get("keyboard", False)),
            sensor=str(entry.get("sensor") or ""),
            working_modes=str(entry.get("working_modes") or "usb,2.4g"),
        )
    return caps


_DB = _load()


def for_product(product_id: int) -> Capabilities:
    caps = _DB.get(product_id)
    if caps is not None:
        return caps
    return Capabilities(
        product_id=product_id,
        name=f"RAWM {product_id:04X}",
        display_name=f"RAWM {product_id:04X}",
        mouse=True,
        power_modes=["Office", "LP", "HP", "Gaming+"],
        lod_names=["LOW", "MEDIUM", "HIGH"],
    )


def for_state(state: MouseState) -> Capabilities:
    return for_product(state.product_id)


def all_capabilities() -> list[Capabilities]:
    return sorted(_DB.values(), key=lambda c: c.display_name.lower())


def _receiver_caps(state) -> Capabilities | None:
    pid = getattr(state, "receiver_product_id", None)
    return _DB.get(int(pid)) if pid else None


def wireless_boost(state) -> bool:
    """The link can use the receiver's boost polling rates."""
    return bool(getattr(state, "via_receiver", False) and not getattr(state, "wired", False))


def max_polling_rate(state) -> int:
    """Mirror get_max_polling_rate(): link type + power mode + model cap."""
    caps = for_state(state)
    if wireless_boost(state):
        receiver = _receiver_caps(state)
        limit = 1000
        if receiver is not None and receiver.boost_polling_rates:
            limit = max(receiver.boost_polling_rates)
        limit = min(limit, caps.polling_rate_max)
    else:
        limit = max(caps.polling_rates) if caps.polling_rates else 1000
        limit = min(limit, caps.polling_rate_max)
    if len(caps.power_modes) >= 3:
        if state.power_mode == 0:
            limit = min(limit, 125)
        elif state.power_mode == 1:
            limit = min(limit, 1000)
    return limit


def effective_polling_rates(state) -> list[int]:
    """Rates to show in the UI, matching get_polling_rates()."""
    caps = for_state(state)
    rates = list(caps.polling_rates)
    if wireless_boost(state):
        receiver = _receiver_caps(state)
        if receiver is not None:
            rates.extend(receiver.boost_polling_rates)
    # the driver always keeps doubling up to the current rate so it is visible
    current = int(getattr(state, "polling_rate", 0) or 0)
    rate = 125
    while rate <= max(125, current):
        if rate not in rates:
            rates.append(rate)
        rate *= 2
    limit = max_polling_rate(state)
    allowed = sorted({r for r in rates if r <= limit})
    if current and current not in allowed:
        allowed.append(current)
        allowed.sort()
    return allowed
