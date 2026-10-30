# -*- coding: utf-8 -*-
"""
Created the 20/07/2023

@author: Sebastien Weber
"""
from abc import ABC, abstractmethod
from functools import cache
from pathlib import Path
from typing import Union, Tuple, List, Callable, TYPE_CHECKING

import numpy as np
from pymodaq_utils.logger import set_logger, get_module_name
from pymodaq_data import Q_, DataToExport


from pymodaq_plugins_beam_shaping.algorithms.factory import AlgorithmFactory
from pymodaq_plugins_beam_shaping.algorithms.utils import LensSetup, ApplyMaskTo, AlgoType
from pymodaq_plugins_beam_shaping.algorithms import AlgoBase
from pymodaq_plugins_beam_shaping.utils import Config as PluginConfig
from pymodaq_plugins_beam_shaping.field import Field


if TYPE_CHECKING:
    from pymodaq_plugins_beam_shaping.algorithms.algorithm_app import AlgoApp

logger = set_logger(get_module_name(__file__))
plugin_config = PluginConfig()


def approx_inverse_f(y: np.ndarray):
    return (2 * y + 3 / 10 * y ** 3 + 321 / 2800 * y ** 5 + 3197 / 56000 * y ** 7
    +445617 / 13798400 * y ** 9
    +1766784699 / 89689600000 * y ** 11 + 317184685563 / 25113088000000 * y ** 13
    +14328608561991 / 1707689984000000 * y ** 15
    +6670995251837391 / 1165411287040000000 * y ** 17
    +910588298588385889 / 228420612259840000000 * y ** 19
    +1889106915501879285127263 / 669318078043783168000000000 * y ** 21
    +122684251268939994619239 / 60571771768668160000000000 * y ** 23
    +86578199631805319180104483967 / 58899990867852918784000000000000 * y ** 25
    +36790913563978761395277930686421 /
    34161994703354692894720000000000000 * y ** 27
    +295479400033606079171291233070109663 /
    371437974410411888261201920000000000000 * y ** 29
    +5429197579977012936689051219262425180781 /
    9174517967937173640051687424000000000000000 * y ** 31
    +111912180845235829957717919886518013347855667 /
    252655431286439247725093999083520000000000000000 * y ** 33
    +21623582556767547163123245489615552651038372109 /
    64865414807824606864932296091238400000000000000000 * y ** 35
    +1686950689722579328034933293949678511289600201851 /
    6691379632807169971329857912569856000000000000000000 * y ** 37
    +362964877894310955248925785551248746981943835416147 /
    1895485357802467420969439750506151936000000000000000000 * y ** 39
    +241119375769652087142546687133690376324455849576103305306113 /
    1651328495419246089263940926464174667092459520000000000000000000 * y ** 41
    +62733744440681157939079200023293588467527441653821853933262223 /
    561451688442543670349739914997819386811436236800000000000000000000 * y ** 43
    +90541073261492600342265407374539407149059862146954660576097727343 /
    1055529174271982100257511040195900447205500125184000000000000000000000
    *y ** 45
    +126749063504538759034999649107808731423757688715140874157349767781 /
    1919143953221785636831838254901637176737272954880000000000000000000000
    *y ** 47
    +249693053510060031661928074632553530869877798468407353253082594529911 /
    4897091793534510236175803834629896837864823539630080000000000000000000000
    *y ** 49)


def approx_inverse_sinc(x: np.ndarray) -> np.ndarray:
    return np.sqrt(3/2) * approx_inverse_f(np.sqrt(1 - x))


class PhasePattern(ABC):
    
    NAME: str = None  # to be reimplemented
    METHOD: str = None  # letter from the method description in the DOI:10.1364/OE.24.006249 | OPTICS EXPRESS 6253 paper

    def __init__(self, input_field: Field, target_field: Field, gamma: int, **kwargs):
        self.input_field = input_field
        self.target_field = target_field
        self.gamma = gamma

        self.other_kwargs = kwargs

    @abstractmethod
    def generate_phase(self) -> np.ndarray:
        """ Main method that generate the phase pattern to be applied to the SLM"""
        ...

    def generate_grating_phase(self) -> np.ndarray:
        x_array = np.linspace(0, self.input_field.shape[1], self.input_field.shape[1])
        return (2 * np.pi * x_array / self.gamma) % 2*np.pi

    def relative_amplitude(self) -> np.ndarray:
        relative_amplitude = ((self.target_field.amplitude / self.target_field.amplitude.max()) /
                              (self.input_field.amplitude / self.input_field.amplitude.max()))
        return relative_amplitude / relative_amplitude.max()

    def relative_phase(self) -> np.ndarray:
        return self.target_field.phase - self.input_field.phase + self.generate_grating_phase()


class PatternFactory:
    """The factory class for creating Diffractive Phases to be used with the diffractive algorithm below"""

    _registry: dict[str, type[PhasePattern]] = {}

    @classmethod
    def register(cls) -> Callable:
        """Class decorator method to register class to the internal registry. Must be used as
        decorator above the definition of a DiffractiveBase inherited class.

        The Diffractive class must implement specific class attributes and methods
        """

        def inner_wrapper(wrapped_class: type[PhasePattern]) -> type[PhasePattern]:
            name = wrapped_class.NAME
            if name is None:
                raise NotImplementedError('The reimplemented class must have a valid NAME string attribute')
            if wrapped_class.METHOD is None:
                raise NotImplementedError('The reimplemented class must have a valid METHOD letter string attribute')
            if name not in cls._registry:
                cls._registry[name] = wrapped_class
            # Return wrapped_class
            return wrapped_class
        # Return decorated function
        return inner_wrapper

    @classmethod
    def get_phase(cls, name: str, **kwargs) -> np.ndarray:
        """Factory command to get registered Phase patterns
        """
        if name not in cls._registry:
            raise ValueError(f".{name} is not a supported Algorithm.")

        return cls._registry[name](**kwargs).generate_phase()

    @property
    def keys(self):
        return list(self._registry.keys())


@PatternFactory.register()
class RelativeAmplitude(PhasePattern):
    NAME = 'Relative Amplitude'
    METHOD = 'A'

    def generate_phase(self) -> np.ndarray:
        return self.relative_amplitude() * self.relative_phase()


@PatternFactory.register()
class Scattering(PhasePattern):
    NAME = 'Scattering'
    METHOD = 'B'

    def generate_phase(self) -> np.ndarray:
        alpha = np.max(self.input_field.amplitude) / np.max(self.target_field.amplitude)

        interference = (self.input_field +
                        alpha * self.target_field.amplitude *
                        np.exp(1j * (self.target_field.phase +  self.generate_grating_phase())))
        phase = interference.phase
        return phase


@PatternFactory.register()
class Davis(PhasePattern):
    NAME = 'Davis'
    METHOD = 'C'

    def generate_phase(self) -> np.ndarray:
        return (1 - 1 / np.pi * approx_inverse_sinc(self.relative_amplitude())) * self.relative_phase()


@PatternFactory.register()
class Bolduc(PhasePattern):
    NAME = 'Bolduc'
    METHOD = 'D'

    def generate_phase(self) -> np.ndarray:
        Mfactor = (1 + 1 / np.pi * approx_inverse_sinc(self.relative_amplitude()))
        return Mfactor * (self.relative_phase() - np.pi * Mfactor)


@PatternFactory.register()
class Arrizon(PhasePattern):
    NAME = 'Arrizon'
    METHOD = 'E'

    def generate_phase(self) -> np.ndarray:
        raise NotImplementedError



diff_factory = PatternFactory()


@AlgorithmFactory.register_algorithm()
class OE2016(AlgoBase):
    """ Implementation of the algorithms discussed in OPTICS EXPRESS DOI:10.1364/OE.24.006249
    The algorithms create amplitude image with phase only spatial light modulators
    in a 4f line with two lens and a circular filter in the Fourier Plane to filter out undiffracted light

    The corresponding experimental setup should define a working light wavelength and focal lengths
    of the used lens
    """

    ALGO_NAME = 'Diffractive'
    ALGOTYPE = AlgoType.AMPLITUDE
    SETUP_TYPE = LensSetup.FourF
    ITERATIVE = False

    params = [
        {'title': 'Gamma', 'name': 'gamma', 'type': 'int', 'value': 4,
         'tip': 'Grating period of the modulation in pixels'},
        {'title': 'Diffractive Models', 'name': 'diff_model', 'type': 'list', 'value': diff_factory.keys[0],
         'limits': diff_factory.keys},
        {'title': 'Order N', 'name': 'order_n', 'type': 'int', 'value': 10,}
    ]

    def __init__(self, parent: 'AlgoApp' = None, *args, **kwargs):
        super().__init__(parent)

    def compute_phase_and_or_amplitude(self, do_step=True, **kwargs):

        diff_phase = diff_factory.get_phase(self.settings['diff_model'],
                                            input_field=self._input_field,
                                            target_field=self._target_field,
                                            gamma=self.settings['gamma'],
                                            order_n = self.settings['order_n'])

        self.set_phase_in_modulator_plane(diff_phase)

        circ_aperture = self.get_mask_field(apply_to=ApplyMaskTo.INTERMEDIATE, inner_value=1, outer_value=0)
        self.intermediate_field = self.modulator_field.fft2() * circ_aperture.amplitude
        self.intermediate_field.calibrate_axes(self.intermediate_pixel_sizes)
        self.intermediate_field.axes = self.intermediate_field.get_axes()

        self._output_field = self.intermediate_field.ifft2()

        self.output_field.calibrate_axes(self._target_field.pixels_sizes)
        self.output_field.axes = self.output_field.get_axes()

    def value_changed(self, param):
        self.parent_app.compute_phase_and_or_amplitude()





