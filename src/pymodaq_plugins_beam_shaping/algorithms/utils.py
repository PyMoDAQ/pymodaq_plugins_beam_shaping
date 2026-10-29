import dataclasses
from typing import TYPE_CHECKING

from pymodaq_utils.logger import set_logger, get_module_name
from pymodaq_utils.enums import StrEnum

from pymodaq_plugins_beam_shaping.utils import Config as PluginConfig

if TYPE_CHECKING:
    pass

logger = set_logger(get_module_name(__file__))
plugin_config = PluginConfig()


class MaskError(Exception):
    pass


class LensSetup(StrEnum):
    NoLens = 'no_lens'
    TwoF = '2f'
    FourF = '4f'


class AlgoType(StrEnum):
    AMPLITUDE = 'Amplitude'
    AMPLITUDE_PHASE = 'AmplitudePhase'

class SLMType(StrEnum):
    LCOS = 'lcos'
    DMD = 'dmd'

class ApplyMaskTo(StrEnum):
    TARGET = 'target_mask'
    INTERMEDIATE = 'intermediate_mask'


@dataclasses.dataclass
class CrossTalk:
    apply: bool = False
    value: float = 0.5


@dataclasses.dataclass
class PhaseManipulation:
    apply: bool = True
    wrap_value: int = 2
    dynamic_value: int = 8





