import dataclasses
from typing import Optional

from pymodaq_utils.enums import StrEnum
from pymodaq_utils.config import GlobalConfig

config = GlobalConfig()


class ModulatorType(StrEnum):
    PHASE = 'phase'
    AMPLITUDE = 'amplitude'
    BOTH = 'both'


@dataclasses.dataclass
class Shaper:
    name: str
    width: int
    height: int
    pixel_size: float  # in micrometer
    has_internal_calibration: bool
    use_internal_calibration: bool
    modulator_type: ModulatorType


SHAPER_GEOMETRY_NAME = 'shaper_geometry'


def shaper_geometry_params() -> dict:
    """Settings group that an instrument plugin driving a shaper (SLM, DMD...) adds to its parameters

    The BeamShaping extension reads the number of pixels and their size from this group in the settings of the
    control module (the plugin itself lives in another thread and fills the group when it is initialized). A plugin
    does not need to import this module: the group is a contract, its name and the names of its children are what
    matters. All the children are read only, sizes in micrometer.
    """
    return {'title': 'Shaper geometry:', 'name': SHAPER_GEOMETRY_NAME, 'type': 'group', 'children': [
        {'title': 'Width (pixels):', 'name': 'width', 'type': 'int', 'value': 0, 'readonly': True},
        {'title': 'Height (pixels):', 'name': 'height', 'type': 'int', 'value': 0, 'readonly': True},
        {'title': 'Pixel size x (um):', 'name': 'pixel_size_x', 'type': 'float', 'value': 0., 'readonly': True},
        {'title': 'Pixel size y (um):', 'name': 'pixel_size_y', 'type': 'float', 'value': 0., 'readonly': True},
    ]}


@dataclasses.dataclass(frozen=True)
class ShaperGeometry:
    """Pixel layout of a shaper (SLM, DMD...), as reported by its instrument plugin"""
    width: int  # number of pixels along x (horizontal)
    height: int  # number of pixels along y (vertical)
    pixel_size_x: float  # in micrometer
    pixel_size_y: float  # in micrometer

    @property
    def shape(self) -> tuple[int, int]:
        """The shape (height, width) of the arrays to send to the shaper"""
        return self.height, self.width

    @property
    def pixel_size(self) -> tuple[float, float]:
        """The pixel sizes (x, y) in micrometer"""
        return self.pixel_size_x, self.pixel_size_y

    @classmethod
    def from_parameter(cls, group) -> 'ShaperGeometry':
        """Read the group created by :func:`shaper_geometry_params`"""
        return cls(int(group['width']), int(group['height']),
                   float(group['pixel_size_x']), float(group['pixel_size_y']))


def get_module_shaper_geometry(module) -> Optional[ShaperGeometry]:
    """The geometry given by a DAQ_Move control module, None if its plugin has no shaper geometry group or did not
    fill it yet (not initialized)"""
    try:
        group = module.settings.child(module._hw_settings_name, SHAPER_GEOMETRY_NAME)
    except (KeyError, AttributeError):
        return None
    geometry = ShaperGeometry.from_parameter(group)
    return geometry if geometry.width > 0 and geometry.height > 0 and geometry.pixel_size_x > 0 else None


def get_shaper() -> Shaper:
    default_slm = config('beam_shaping', 'SLM', 'default_slm')[0]
    return Shaper(name=default_slm,
                  width=config('beam_shaping', 'SLM', default_slm, 'width'),
                  height=config('beam_shaping', 'SLM', default_slm, 'height'),
                  pixel_size=config('beam_shaping', 'SLM', default_slm, 'pixel_size'),
                  has_internal_calibration=config('beam_shaping', 'SLM', default_slm, 'has_internal_calibration'),
                  use_internal_calibration=config('beam_shaping', 'SLM', default_slm, 'use_internal_calibration'),
                  modulator_type=ModulatorType(config('beam_shaping', 'SLM', default_slm, 'modulator_type')[0])
                  )