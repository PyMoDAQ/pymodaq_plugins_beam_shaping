from pymodaq_utils.config import GlobalConfig

# The shaper contract (settings groups of the instrument plugin, Shaper dataclass) lives in pymodaq_plugins_utils
from pymodaq_plugins_utils.hardware.shaper import Shaper, ModulatorType, shaper_params, fill_shaper_settings

config = GlobalConfig()


def get_shaper() -> Shaper:
    """The shaper as described in the configuration, used when the Shaper actuator does not tell (plugin not
    initialized or not exposing the shaper settings groups of pymodaq_plugins_utils)"""
    default_slm = config('beam_shaping', 'SLM', 'default_slm')[0]
    return Shaper(name=default_slm,
                  width=config('beam_shaping', 'SLM', default_slm, 'width'),
                  height=config('beam_shaping', 'SLM', default_slm, 'height'),
                  pixel_size=config('beam_shaping', 'SLM', default_slm, 'pixel_size'),
                  has_internal_calibration=config('beam_shaping', 'SLM', default_slm, 'has_internal_calibration'),
                  use_internal_calibration=config('beam_shaping', 'SLM', default_slm, 'use_internal_calibration'),
                  modulator_type=ModulatorType(config('beam_shaping', 'SLM', default_slm, 'modulator_type')[0])
                  )
