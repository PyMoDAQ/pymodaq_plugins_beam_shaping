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
class DmDLee(AlgoBase):
    """ Implementation of the Lee algorithm W.H. Lee, Progress in Optics (1978)
    algorithm to create a phase modulated image using DMD type spatial light modulators
    in a 4f line with two lens and a circular filter in the Fourier Plane

    The corresponding experimental setup should define a working light wavelength and a focal length
    of the used lens
    """

    ALGO_NAME = 'DMD Lee'
    ALGOTYPE = AlgoType.PHASE
    MODULATOR_TYPES = (ModulatorType.AMPLITUDE, )
    SETUP_TYPE = LensSetup.FourF
    ITERATIVE = False

    params = [
        {'title': 'Super Pixel size (pxls)', 'name': 'super_pixel', 'type': 'int', 'value': 5, 'min': 1},
        {'title': 'threshold', 'name': 'threshold', 'type': 'float', 'value': 0.5, 'limits': [0., 1.]},
    ]

    def __init__(self, parent: 'AlgoApp' = None, *args, **kwargs):
        super().__init__(parent)

    def compute_grid(self) -> tuple[np.ndarray, np.ndarray]:
        """ Compute the centered positions on the grid in pixels"""
        x = np.arange(0, self.shape[1], 1)
        x = x-np.mean(x)
        y = np.arange(0, self.shape[0], 1)
        y = y - np.mean(y)
        xx, yy = np.meshgrid(x, y)
        return xx, yy

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

        self.intermediate_field = self.modulator_field.fft2(norm='forward') * np.prod(self.modulator_field.shape)
        if self.apply_mask(apply_to=ApplyMaskTo.INTERMEDIATE):
            circ_aperture = self.get_mask_field(apply_to=ApplyMaskTo.INTERMEDIATE)
            self.intermediate_field.amplitude = self.intermediate_field.amplitude * circ_aperture.amplitude

        self.intermediate_field.calibrate_axes(self.intermediate_pixel_sizes)
        self.intermediate_field.axes = self.intermediate_field.get_axes()

        self._output_field = self.intermediate_field.ifft2(norm='forward')

        target_pixel_sizes = [((Q_(plugin_config('setup', 'wavelength_nm',), 'nm') *
                               Q_(plugin_config('setup', str(self.SETUP_TYPE), 'focals')[1], 'mm')) /
                               (self.intermediate_pixel_sizes[ind] * self.shape[ind])
                              ).to('um') for ind in range(2)]
        self.output_field.calibrate_axes(target_pixel_sizes)
        self.output_field.axes = self.output_field.get_axes()


    def value_changed(self, param):
        self.parent_app.compute_phase_and_or_amplitude()





