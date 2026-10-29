import dataclasses

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


class ShaperInterface:
    """Base class (mixin) of the instrument plugins (DAQ_Move) that drive a shaper

    A plugin deriving from it must tell the BeamShaping extension the number of pixels and their size, whatever the
    driver (the values come from the instrument, not from the configuration file). Put it first in the bases:
    ``class DAQ_Move_X(ShaperInterface, DAQ_Move_base)``.
    """

    def get_shaper_geometry(self) -> ShaperGeometry:
        """Number of pixels along x and y and size of the pixels in micrometer, to be implemented"""
        raise NotImplementedError


def has_shaper_interface(obj) -> bool:
    """True if the object (a plugin, or a controller) gives the geometry of the shaper, derived from
    ShaperInterface or not (so that a plugin does not need beam_shaping installed to provide it)"""
    return callable(getattr(obj, 'get_shaper_geometry', None))


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