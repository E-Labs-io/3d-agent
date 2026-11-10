"""Helpers imported by a project's model.py.

A model.py defines PARTS, a dict of name -> part(...). Shapes are build123d
solids in assembled position, millimetres, Z up.

It may also define HARDWARE, a list of dicts for items that are bought rather
than modelled: {"name", "qty", "spec", "mpn", "supplier", "url", "unit_price"}.
Only "name" is required. These go straight into the bill of materials.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PartSpec:
    shape: object
    material: str = "petg"
    color: str = "#8a93a6"
    opacity: float = 1.0
    reference: bool = False      # fit ghost / bought-in item: shown, never manufactured
    print_flip: bool = False     # export upside down so downward pockets face up
    process: str = "fdm"         # fdm | sla | sls | cnc | sheet | bought
    qty: int = 1
    note: str = ""


def part(shape, **kw) -> PartSpec:
    return PartSpec(shape=shape, **kw)
