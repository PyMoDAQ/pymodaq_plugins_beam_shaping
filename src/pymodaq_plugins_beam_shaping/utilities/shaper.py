# The shaper contract (settings groups of the instrument plugin, Shaper dataclass) lives in pymodaq_plugins_utils
from pymodaq_plugins_utils.hardware.shaper import Shaper, ModulatorType, shaper_params, fill_shaper_settings

from pymodaq_plugins_beam_shaping import config


def get_default_shaper() -> Shaper:
    """The shaper described in the ``default_shaper`` section of the configuration file

    It is used as long as no Shaper actuator tells what the shaper is (actuator absent or not initialized, or a plugin
    that does not provide the shaper settings groups): the same for all the shapers.
    """
    has_internal_calibration = bool(config('default_shaper', 'has_internal_calibration'))
    return Shaper(name=config('default_shaper', 'name'),
                  width=config('default_shaper', 'width'),
                  height=config('default_shaper', 'height'),
                  pixel_size=config('default_shaper', 'pixel_size'),
                  has_internal_calibration=has_internal_calibration,
                  use_internal_calibration=has_internal_calibration and
                  bool(config('calibration', 'use_internal_calibration')),
                  modulator_type=ModulatorType(config('default_shaper', 'modulator_type')[0]))
