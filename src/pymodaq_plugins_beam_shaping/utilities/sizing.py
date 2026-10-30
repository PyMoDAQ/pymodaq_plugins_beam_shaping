import numpy as np
from pymodaq_utils.math_utils import greater2n, is_power_of_two
from pymodaq_plugins_beam_shaping import config as plugin_config
from pymodaq_plugins_beam_shaping.utilities.shaper import Shaper


def get_binning() -> int:
    return plugin_config('sizing', 'binning')


def get_effective_needed_field_size(shaper: Shaper) -> tuple[int, int]:
    """ Compute from the shaper and the configuration values the needed size of the fields to be used"""

    binning = plugin_config('sizing', 'binning')
    if not is_power_of_two(binning):
        raise ValueError('binning must be a multiple of 2')
    if plugin_config('sizing', 'square_size'):
        needed_field_size = greater2n(max(get_slm_size(shaper))) // binning
        needed_field_size = (needed_field_size, needed_field_size)
    else:
        needed_field_size = tuple(np.array(get_slm_size(shaper)) // binning)
    return needed_field_size


def get_slm_size(shaper: Shaper) -> tuple[int, int]:
    """The shape (height, width) of the shaper in pixels"""
    return shaper.shape


def get_effective_slm_size(shaper: Shaper) -> tuple[int, int]:
    binning = plugin_config('sizing', 'binning')
    if not is_power_of_two(binning):
        raise ValueError('binning must be a multiple of 2')
    size = np.array(get_slm_size(shaper)) // binning
    return int(size[0]), int(size[1])


def get_effective_slm_pixel_size(shaper: Shaper) -> float:
    """ Compute the effective SLM pixel size in microns (the one of the shaper times the binning)"""

    return shaper.pixel_size * plugin_config('sizing', 'binning')


def unbin_to_real_slm(phase: np.ndarray, binning: int = None) -> np.ndarray:
    """ "rebin" a given ndarray by repeating its values binning time to fit the pixel arrays of the real SLM

    The final shape is initial shape x binning

    """
    if binning is None:
        binning = plugin_config('sizing', 'binning')
    return np.repeat(np.repeat(phase, binning, axis=0), binning, axis=1)


def get_effective_area_pos_size_in_pxls(shaper: Shaper) -> tuple[np.ndarray, np.ndarray]:
    """ Get the position and size of the effective area image of the SLM in pixels

    pos is the position of the left, bottom corner of the area
    """
    size = np.array(get_effective_slm_size(shaper))
    pos = (np.array(get_effective_needed_field_size(shaper)) - size) / 2
    return pos, size



if __name__ == '__main__':
    pass