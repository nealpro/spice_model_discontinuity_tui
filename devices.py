"""Declarative device field mappings for SPICE CSV columns.

Each ``[devices.<NAME>]`` table in the TOML config declares:

- ``independent`` — the key inside the table whose value is the CSV column to
  use as the derivative x-axis.
- Any number of other ``<semantic_name> = "<CSV column>"`` pairs — these are
  the fields that get analyzed for discontinuities against the independent
  axis.

New device types are added purely in TOML; no code change is required here.
"""

from dataclasses import dataclass
from typing import Any

INDEPENDENT_KEY = "independent"


@dataclass(frozen=True)
class Device:
    name: str
    independent: str  # semantic key inside `fields` used as x-axis
    fields: dict[str, str]  # semantic_name -> CSV column name

    @property
    def independent_column(self) -> str:
        return self.fields[self.independent]

    def dependent_items(self) -> list[tuple[str, str]]:
        return [(k, v) for k, v in self.fields.items() if k != self.independent]


def load_devices(config: dict[str, Any]) -> dict[str, Device]:
    """Parse every ``[devices.<name>]`` table from the config."""
    raw = config.get("devices") or {}
    devices: dict[str, Device] = {}
    for name, table in raw.items():
        if not isinstance(table, dict):
            continue
        independent = table.get(INDEPENDENT_KEY)
        if not isinstance(independent, str):
            raise ValueError(
                f"[devices.{name}] is missing required '{INDEPENDENT_KEY}' field."
            )
        fields = {
            k: v
            for k, v in table.items()
            if k != INDEPENDENT_KEY and isinstance(v, str)
        }
        if independent not in fields:
            raise ValueError(
                f"[devices.{name}].{INDEPENDENT_KEY} points at '{independent}' "
                f"but no '{independent}' field is defined in the same table."
            )
        devices[name] = Device(name=name, independent=independent, fields=fields)
    return devices


def active_device(config: dict[str, Any], override: str | None = None) -> Device | None:
    """Resolve the active device: explicit override → ``[analysis].device`` → None."""
    devices = load_devices(config)
    if not devices:
        return None
    name = override or config.get("analysis", {}).get("device")
    if name is None:
        return None
    if name not in devices:
        raise KeyError(
            f"device '{name}' not found in config; known devices: {sorted(devices)}"
        )
    return devices[name]
