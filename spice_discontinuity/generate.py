"""SPICE netlist generation utilities for FET simulations."""

from dataclasses import dataclass
from typing import Literal

FetType = Literal["nfet", "pfet"]


@dataclass(frozen=True)
class FetSpec:
    """Input parameters for generating a simple FET SPICE deck."""

    fet_type: FetType
    model_name: str
    width: float
    length: float
    drain: str = "d"
    gate: str = "g"
    source: str = "s"
    body: str = "b"
    vgs: float = 1.0
    vds: float = 1.0


def generate_fet_netlist(spec: FetSpec) -> str:
    """Return a minimal SPICE netlist for NFET/PFET DC simulation."""
    model = "NMOS" if spec.fet_type == "nfet" else "PMOS"
    return (
        f"* Auto-generated {spec.fet_type.upper()} deck\n"
        f"VGS {spec.gate} {spec.source} {spec.vgs}\n"
        f"VDS {spec.drain} {spec.source} {spec.vds}\n"
        f"M1 {spec.drain} {spec.gate} {spec.source} {spec.body} {spec.model_name} "
        f"W={spec.width}u L={spec.length}u\n"
        f".MODEL {spec.model_name} {model}\n"
        ".OP\n"
        ".END\n"
    )
