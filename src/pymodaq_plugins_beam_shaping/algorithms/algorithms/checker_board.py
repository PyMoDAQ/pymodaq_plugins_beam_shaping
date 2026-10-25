# -*- coding: utf-8 -*-
"""
Created the 20/07/2023

@author: Sebastien Weber
"""
from pathlib import Path
from typing import Union, Tuple, List, TYPE_CHECKING

import numpy as np
from copy import deepcopy

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
class OL2014(AlgoBase):
    """ Implementation of the OPTICS LETTERS / Vol. 39, No. 7 / April 1, 2014
    algorithm to create amplitude and phase modulated image with phase only spatial light modulators
    in a 4f line with two lens and a circular filter in the Fourier Plane

    The corresponding experimental setup should define a working light wavelength and a focal length
    of the used lens
    """

    ALGO_NAME = 'OL2014 - Amplitude/Phase Checkerboard'
    ALGOTYPE = AlgoType.AMPLITUDE_PHASE
    SETUP_TYPE = LensSetup.FourF
    ITERATIVE = False

    params = [
        {'title': 'Mask block size (pxls)', 'name': 'block_size', 'type': 'int', 'value': 5, 'min': 1},
        {'title': 'amplitude divider', 'name': 'divider', 'type': 'float', 'value': 1},

    ]

    def __init__(self, parent: 'AlgoApp' = None, *args, **kwargs):
        super().__init__(parent)

    def compute_phase(self, do_step=True, **kwargs):


        odd_mask = self.create_checker_board()
        even_mask = 1 - odd_mask
        self._target_field = self.normalize_wrt(self._target_field, self._input_field)


        calculated_field: Field = deepcopy(self._target_field)

        beta = np.arccos(calculated_field.amplitude / np.max(calculated_field.amplitude) / self.settings['divider'])
        theta_field = Field('theta', phase=calculated_field.phase + beta)
        alpha_field = Field('alpha', phase=calculated_field.phase - beta)

        theta_field.phase *= odd_mask
        alpha_field.phase *= even_mask

        self.set_phase_in_modulator_plane(theta_field.phase + alpha_field.phase)
        self.intermediate_field = self.modulator_field.fft2(norm='forward') * np.prod(self.modulator_field.shape)
        if self.apply_mask(apply_to=ApplyMaskTo.INTERMEDIATE):
            circ_aperture = self.get_mask_field(apply_to=ApplyMaskTo.INTERMEDIATE)
            self.intermediate_field.amplitude = self.intermediate_field.amplitude * circ_aperture.amplitude

        self.intermediate_field.calibrate_axes(self.intermediate_pixel_sizes)
        self.intermediate_field.axes = self.intermediate_field.get_axes()

        self._output_field = self.intermediate_field.ifft2(norm='forward')

        target_pixel_sizes = [((Q_(plugin_config('setup', 'wavelength_nm',), 'nm') *
                               Q_(plugin_config('setup', str(self.SETUP_TYPE), 'focals')[1], 'mm')) /
                               (self.intermediate_pixel_sizes[ind] * theta_field.shape[ind])
                              ).to('um') for ind in range(2)]
        self.output_field.calibrate_axes(target_pixel_sizes)
        self.output_field.axes = self.output_field.get_axes()

    def create_checker_board(self) -> np.ndarray:

        block_size = self.settings['block_size']
        y, x = np.indices(self._modulator_field.shape)
        mask = ((x // block_size) + (y // block_size)) % 2
        return mask

    def value_changed(self, param):
        self.parent_app.compute_phase()





