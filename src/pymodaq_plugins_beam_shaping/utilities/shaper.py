from typing import Optional

# The shaper contract (settings groups of the instrument plugin, Shaper dataclass) lives in pymodaq_plugins_utils
from pymodaq_plugins_utils.hardware.shaper import Shaper, ModulatorType, shaper_params, fill_shaper_settings

from pymodaq_plugins_beam_shaping import config

_current_shaper: Optional[Shaper] = None


def get_default_shaper() -> Shaper:
    """The shaper described in the ``default_shaper`` section of the configuration file

    It is used as long as no Shaper actuator tells what the shaper is (actuator absent or not initialized, or a plugin
    that does not provide the shaper settings groups): the same for all the shapers.
    """
    return Shaper(name=config('default_shaper', 'name'),
                  width=config('default_shaper', 'width'),
                  height=config('default_shaper', 'height'),
                  pixel_size=config('default_shaper', 'pixel_size'),
                  has_internal_calibration=config('default_shaper', 'has_internal_calibration'),
                  use_internal_calibration=config('default_shaper', 'use_internal_calibration'),
                  modulator_type=ModulatorType(config('default_shaper', 'modulator_type')[0]))


def set_shaper(shaper: Optional[Shaper]):
    """Set the shaper that get_shaper returns, None to go back to the default one"""
    global _current_shaper
    _current_shaper = shaper


def get_shaper() -> Shaper:
    """The shaper last told by the Shaper actuator (see the BeamShaping extension), else the default one"""
    return _current_shaper if _current_shaper is not None else get_default_shaper()
