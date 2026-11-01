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


def remove_linear_phase(field: np.ndarray, ky: float, kx: float) -> np.ndarray:
    """ Remove a linear phase from a complex array centered as the output of Field.ifft2

    This is the same as shifting the spectrum of the array (Field.fft2: centered, zero frequency at index N // 2)
    by (ky, kx) pixels, fractional values included.

    Parameters
    ----------
    field: np.ndarray
        2D complex array (rows, columns)
    ky, kx: float
        carrier in cycles per array along the rows and the columns, that is the position of the center of the
        mask in the spectrum minus the index of the zero frequency
    """
    ny, nx = field.shape
    y = np.arange(ny) - ny // 2
    x = np.arange(nx) - nx // 2
    return field * np.exp(-2j * np.pi * (ky * y[:, None] / ny + kx * x[None, :] / nx))


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
        {'title': 'Remove carrier:', 'name': 'remove_carrier', 'type': 'bool', 'value': True,
         'tip': 'Remove the linear phase of the filtered order: the spectrum is shifted by the center of the mask '
                'applied to the intermediate plane (needs this mask)'},
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

        # amplitude[amplitude > threshold] = 1
        # amplitude[amplitude <= threshold] = 0

        return amplitude

    def compute_amplitude_pattern(self) -> np.ndarray:
        xx, yy = self.compute_grid()


        amplitude_dmd = 1/2 * (1 + np.cos(2 * np.pi * (xx - yy) / self.settings['super_pixel'] -
                                          self._target_field.phase))

        amplitude_dmd = self.threshold_amplitude(amplitude_dmd)

        return amplitude_dmd


    def get_carrier(self) -> tuple[float, float] | None:
        """ Position (rows, columns) of the center of the intermediate mask relative to the zero frequency, in pixels

        None if the mask is not applied to the intermediate plane
        """
        if not self.apply_mask(apply_to=ApplyMaskTo.INTERMEDIATE):
            return None
        slices = self.get_mask_slices(ApplyMaskTo.INTERMEDIATE)
        if slices is None:
            return None
        # center of the pixels covered by the slices, relative to the index of the zero frequency
        return tuple((_slice.start + _slice.stop - 1) / 2 - size // 2 for _slice, size in zip(slices, self.shape))

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
        if self.settings['remove_carrier']:
            carrier = self.get_carrier()
            if carrier is None:
                logger.warning('The carrier cannot be removed: apply a mask to the intermediate plane')
            else:
                self._output_field.field = remove_linear_phase(self._output_field.field, *carrier)

        target_pixel_sizes = [((Q_(plugin_config('setup', 'wavelength_nm',), 'nm') *
                               Q_(plugin_config('setup', str(self.SETUP_TYPE), 'focals')[1], 'mm')) /
                               (self.intermediate_pixel_sizes[ind] * self.shape[ind])
                              ).to('um') for ind in range(2)]
        self.output_field.calibrate_axes(target_pixel_sizes)
        self.output_field.axes = self.output_field.get_axes()


    def value_changed(self, param):
        self.parent_app.compute_phase_and_or_amplitude()





