"""Masking regions expressed in real (axes) units and their conversion to array indexes.

The ROIs of the viewers (pymodaq_gui >= 5.3) work in the units of the data axes (meters for the Fields). The
regions are therefore stored as slices of floats in these units and only converted to indexes when an array has to be
sliced (this is what ``DataWithAxes.vsig`` / ``isig`` do for the data with axes).
"""
from typing import Optional, Sequence

import numpy as np

from pymodaq_data.data import Axis

from pymodaq_plugins_beam_shaping.utilities import sizing


def pixel_sizes_in_meters(pixel_sizes: Sequence) -> np.ndarray:
    """ pixel sizes as quantities (or floats in m) -> array of floats in m"""
    return np.array([getattr(size, 'm_as', lambda unit, _s=size: _s)('m') for size in pixel_sizes], dtype=float)


def get_effective_area(pixel_sizes: Sequence) -> tuple[np.ndarray, np.ndarray]:
    """ Position of the origin and size (in m, (y, x)) of the SLM effective area in a plane of given pixel sizes"""
    pos_pxl, size_pxl = sizing.get_effective_area_pos_size_in_pxls()
    pxl = pixel_sizes_in_meters(pixel_sizes)
    return pos_pxl * pxl, size_pxl * pxl


def default_slices(pixel_sizes: Sequence, fraction: float = 2 / 3) -> tuple[slice, slice]:
    """ Region centered on the effective area and covering a fraction of its size (in m)"""
    pos, size = get_effective_area(pixel_sizes)
    center = pos + size / 2
    half = size * fraction / 2
    return tuple(slice(float(c - h), float(c + h)) for c, h in zip(center, half))


def constrain_slices(slices: Sequence[slice], pixel_sizes: Sequence) -> tuple[slice, slice]:
    """ Restrict the slices (in m) to the effective area"""
    pos, size = get_effective_area(pixel_sizes)
    return tuple(slice(float(max(_slice.start, p)), float(min(_slice.stop, p + s)))
                 for _slice, p, s in zip(slices, pos, size))


def are_slices_in_area(slices: Sequence[slice], pixel_sizes: Sequence) -> bool:
    """ True if the slices (in m) are not empty and lie in the effective area"""
    pos, size = get_effective_area(pixel_sizes)
    tol = 1e-6 * size
    return all(_slice.start < _slice.stop and _slice.start >= p - t and _slice.stop <= p + s + t
               for _slice, p, s, t in zip(slices, pos, size, tol))


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
    return str(tuple(slice(float(_slice.start), float(_slice.stop)) for _slice in slices))


def slices_to_indexes(slices: Sequence[slice], pixel_sizes: Sequence, shape: Sequence[int]) -> tuple[slice, slice]:
    """ Convert slices in m to slices of indexes (as ``DataWithAxes.vsig`` would do) clipped to the array shape"""
    pxl = pixel_sizes_in_meters(pixel_sizes)
    indexes = []
    for dim, _slice in enumerate(slices):
        axis = Axis(units='m', scaling=pxl[dim], offset=0., size=int(shape[dim]), index=dim)
        indexes.append(slice(int(np.clip(axis.find_index(_slice.start), 0, shape[dim])),
                             int(np.clip(axis.find_index(_slice.stop), 0, shape[dim]))))
    return tuple(indexes)
