# -*- coding: utf-8 -*-
"""
Created the 20/07/2023

@author: Sebastien Weber
"""
from pathlib import Path
from typing import Union, Tuple, List, TYPE_CHECKING

import numpy as np
from copy import deepcopy

from pymodaq_plugins_beam_shaping.utilities.shaper import ModulatorType
from pymodaq_utils.logger import set_logger, get_module_name

from pymodaq_utils import math_utils as mutils
from pymodaq_data import Q_

from pymodaq_plugins_beam_shaping.algorithms.factory import AlgorithmFactory
from pymodaq_plugins_beam_shaping.algorithms.utils import LensSetup, ApplyMaskTo, AlgoType
from pymodaq_plugins_beam_shaping.algorithms import AlgoBase
from pymodaq_plugins_beam_shaping.utils import Config as PluginConfig
from pymodaq_plugins_beam_shaping.field import Field

if TYPE_CHECKING:
    from pymodaq_plugins_beam_shaping.algorithms.algorithm_app import AlgoApp


logger = set_logger(get_module_name(__file__))
plugin_config = PluginConfig()


@AlgorithmFactory.register_algorithm()
class SuperPixel(AlgoBase):
    """ Implementation of the
    Optics Express Vol. 22, Issue 15, pp. 17999-18009 (2014) •https://doi.org/10.1364/OE.22.017999
    algorithm to create a phase modulated image using DMD type spatial light modulators
    in a 4f line with two lens and a circular filter in the Fourier Plane

    The corresponding experimental setup should define a working light wavelength and a focal length
    of the used lens
    """

    ALGO_NAME = 'SuperPixels'
    ALGOTYPE = AlgoType.PHASE
    MODULATOR_TYPES = (ModulatorType.AMPLITUDE, )
    SETUP_TYPE = LensSetup.FourF
    ITERATIVE = False
    RECOMPUTE_ON_CHANGE = True

    params = [
        {'title': 'Super Pixel size (pxls)', 'name': 'super_pixel', 'type': 'int', 'value': 5, 'min': 1},
        {'title': 'threshold', 'name': 'threshold', 'type': 'float', 'value': 0.5, 'limits': [0., 1.]},
    ]

    def __init__(self, parent: 'AlgoApp' = None, *args, **kwargs):
        super().__init__(parent)

    def threshold_amplitude(self, amplitude: np.ndarray):
        threshold = self.settings['threshold']

        amplitude[amplitude > threshold] = 1
        amplitude[amplitude <= threshold] = 0

        return amplitude

    def compute_amplitude_pattern(self) -> np.ndarray:
        xx, yy = self.compute_grid()


        amplitude_dmd = 1/2 * (1 + np.cos(2 * np.pi * (xx) / self.settings['super_pixel'] -
                                          self._target_field.phase))

        amplitude_dmd = self.threshold_amplitude(amplitude_dmd)

        return amplitude_dmd


    def compute_phase_and_or_amplitude(self, do_step=True, **kwargs):

        amplitude_pattern = self.compute_amplitude_pattern()

        self.set_amplitude_in_modulator_plane(amplitude_pattern)

        self.compute_intermediate_field()
        self.compute_output_from_intermediate()






