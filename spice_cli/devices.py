"""Declarative device field mappings for SPICE CSV columns.

Each ``devices.<NAME>`` table in the YAML config declares:

- ``independent`` — the key inside the table whose value is the CSV column to
  use as the derivative x-axis.
- Any number of other ``<semantic_name> = "<CSV column>"`` pairs — these are
  the fields that get analyzed for discontinuities against the independent
  axis.

New device types are added purely in YAML; no code change is required here.
"""

from dataclasses import dataclass
from typing import Any

INDEPENDENT_KEY = "independent"


@dataclass(frozen=True)
class Device:
    """Maps semantic field names to CSV column headers for a SPICE device.

    Each field in *fields* uses a semantic key (e.g. ``"drain_current"``) that
    maps to the exact CSV column header (e.g. ``"I(VDRAIN)"``). One field is
    designated as the independent axis via *independent*.

    Attributes
    ----------
    name:
        Device identifier (matches the ``devices.<NAME>`` YAML key).
    independent:
        Semantic key of the x-axis field within *fields*.
    fields:
        ``{semantic_name: csv_column_header}`` for all declared fields.
    """

    name: str
    independent: str
    fields: dict[str, str]

    @property
    def independent_column(self) -> str:
        """CSV column header for the independent (x-axis) field."""
        return self.fields[self.independent]

    def dependent_items(self) -> list[tuple[str, str]]:
        """Return ``[(semantic, csv_column), ...]`` for all non-independent fields."""
        return [(k, v) for k, v in self.fields.items() if k != self.independent]


def load_devices(config: dict[str, Any]) -> dict[str, Device]:
    """Parse every ``[devices.<name>]`` table from the config.

    Parameters
    ----------
    config:
        Parsed YAML config dict. Device tables live under the ``"devices"`` key.

    Returns
    -------
    dict
        ``{device_name: Device}`` for every valid table found.

    Raises
    ------
    ValueError
        If a table is missing the ``"independent"`` key, or if the value of
        ``"independent"`` does not name a field in the same table.
    """
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
    """Resolve the active device: explicit override → ``[analysis].device`` → None.

    Parameters
    ----------
    config:
        Parsed YAML config dict.
    override:
        Device name from the ``--device`` CLI flag. Takes priority over config.

    Returns
    -------
    Device or None
        The resolved device, or ``None`` if no device name is set in either
        *override* or ``[analysis].device``.

    Raises
    ------
    KeyError
        If a device name is specified but not found in ``[devices]``.
    """
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
