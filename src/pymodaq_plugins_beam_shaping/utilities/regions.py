"""Masking regions expressed in real units (um, the unit of the pixel sizes) and their conversion to array indexes.

The ROIs of the viewers (pymodaq_gui >= 5.3) work in the units of the data axes (m for the Fields). The regions are
stored in the settings as slices of floats in um (readable numbers) and only converted to indexes when an array has to
be sliced (this is what ``DataWithAxes.vsig`` / ``isig`` do for the data with axes).
"""
from typing import Optional, Sequence

import numpy as np

from pymodaq_plugins_beam_shaping.utilities import sizing
from pymodaq_plugins_beam_shaping.utilities.shaper import Shaper


AXIS_UNIT_TO_UM = 1e6  # the axes of the Fields (hence the ROIs) are in m, the settings in um


def from_axis_units(slices: Sequence[slice]) -> tuple[slice, ...]:
    """ slices in the units of the axes (m) -> slices in um"""
    return tuple(slice(_slice.start * AXIS_UNIT_TO_UM, _slice.stop * AXIS_UNIT_TO_UM) for _slice in slices)


def to_axis_units(slices: Sequence[slice]) -> tuple[slice, ...]:
    """ slices in um -> slices in the units of the axes (m)"""
    return tuple(slice(_slice.start / AXIS_UNIT_TO_UM, _slice.stop / AXIS_UNIT_TO_UM) for _slice in slices)


def pixel_sizes_in_um(pixel_sizes: Sequence) -> np.ndarray:
    """ pixel sizes as quantities (or floats in um) -> array of floats in um"""
    return np.array([getattr(size, 'm_as', lambda unit, _s=size: _s)('um') for size in pixel_sizes], dtype=float)


def get_effective_area(shaper: Shaper, pixel_sizes: Sequence) -> tuple[np.ndarray, np.ndarray]:
    """ Position of the origin and size (in um, (y, x)) of the SLM effective area in a plane of given pixel sizes"""
    pos_pxl, size_pxl = sizing.get_effective_area_pos_size_in_pxls(shaper)
    pxl = pixel_sizes_in_um(pixel_sizes)
    return pos_pxl * pxl, size_pxl * pxl


def default_slices(shaper: Shaper, pixel_sizes: Sequence, fraction: float = 2 / 3) -> tuple[slice, slice]:
    """ Region centered on the effective area and covering a fraction of its size (in um)"""
    pos, size = get_effective_area(shaper, pixel_sizes)
    center = pos + size / 2
    half = size * fraction / 2
    return tuple(slice(float(c - h), float(c + h)) for c, h in zip(center, half))


def constrain_slices(shaper: Shaper, slices: Sequence[slice], pixel_sizes: Sequence) -> tuple[slice, slice]:
    """ Restrict the slices (in um) to the effective area"""
    pos, size = get_effective_area(shaper, pixel_sizes)
    return tuple(slice(float(max(_slice.start, p)), float(min(_slice.stop, p + s)))
                 for _slice, p, s in zip(slices, pos, size))


def are_slices_in_area(shaper: Shaper, slices: Sequence[slice], pixel_sizes: Sequence) -> bool:
    """ True if the slices (in um) are not empty and lie in the effective area"""
    pos, size = get_effective_area(shaper, pixel_sizes)
    tol = 1.  # um, the slices are stored with a 1 um resolution
    return all(_slice.start < _slice.stop and _slice.start >= p - tol and _slice.stop <= p + s + tol
               for _slice, p, s in zip(slices, pos, size))


def parse_slices(text: str) -> Optional[tuple[slice, slice]]:
    """ Get the slices from their string representation, None if not valid"""
    try:
        slices = eval(text, {'slice': slice, 'None': None})
    except Exception:
        return None
    if (isinstance(slices, tuple) and len(slices) == 2 and
            all(isinstance(_slice, slice) and _slice.start is not None and _slice.stop is not None
                for _slice in slices)):
        return slices
    return None


def slices_to_str(slices: Sequence[slice]) -> str:
    """ String representation (to be stored in the settings) with a resolution of 1 um, below the pixel size"""
    return str(tuple(slice(int(round(_slice.start)), int(round(_slice.stop))) for _slice in slices))


def slices_to_indexes(slices: Sequence[slice], pixel_sizes: Sequence, shape: Sequence[int]) -> tuple[slice, slice]:
    """ Convert slices in um to slices of indexes (as ``DataWithAxes.vsig`` would do) clipped to the array shape"""
    pxl = pixel_sizes_in_um(pixel_sizes)
    indexes = []
    for dim, _slice in enumerate(slices):  # nearest pixel, as the axes find_index does but robust to rounding errors
        indexes.append(slice(int(np.clip(round(_slice.start / pxl[dim]), 0, shape[dim])),
                             int(np.clip(round(_slice.stop / pxl[dim]), 0, shape[dim]))))
    return tuple(indexes)
