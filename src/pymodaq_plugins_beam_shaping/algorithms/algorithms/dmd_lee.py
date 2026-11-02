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
from pymodaq_plugins_beam_shaping.algorithms.utils import AlgoStatus, LensSetup, ApplyMaskTo, AlgoType
from pymodaq_plugins_beam_shaping.algorithms import AlgoBase
from pymodaq_plugins_beam_shaping.utils import Config as PluginConfig
from pymodaq_plugins_beam_shaping.field import Field

if TYPE_CHECKING:
    from pymodaq_plugins_beam_shaping.algorithms.algorithm_app import AlgoApp


logger = set_logger(get_module_name(__file__))
plugin_config = PluginConfig()


CARRIER_FROM = ('Mask center', 'Spectrum centroid')
BINARIZATIONS = ('Width modulation', 'Threshold')


def spectrum_centroid(spectrum: np.ndarray) -> tuple[float, float]:
    """ Center of gravity (rows, columns) of the intensity of a centered spectrum, relative to the zero frequency"""
    intensity = np.abs(spectrum) ** 2
    total = intensity.sum()
    if total == 0:
        raise ValueError('The spectrum is null: nothing to find the position of the order from')
    rows, columns = np.indices(intensity.shape)
    return tuple(float((index * intensity).sum() / total) - size // 2
                 for index, size in zip((rows, columns), intensity.shape))


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
    STATUS = AlgoStatus.IN_PROGRESS
    STATUS_NOTE = ('Code tested but not tested on real hardware'
                   )
    ALGOTYPE = AlgoType.AMPLITUDE_PHASE
    MODULATOR_TYPES = (ModulatorType.AMPLITUDE, )
    SETUP_TYPE = LensSetup.FourF
    ITERATIVE = False
    RECOMPUTE_ON_CHANGE = True

    params = [
        {'title': 'Super Pixel size (pxls)', 'name': 'super_pixel', 'type': 'int', 'value': 5, 'min': 1},
        {'title': 'Binarize:', 'name': 'binarize', 'type': 'bool', 'value': True,
         'tip': 'Binarize the pattern to 0 and 1, as a DMD can only do (needed for the real pattern). Unchecked: '
                'the grey levels of the pattern are kept (ideal modulation)'},
        {'title': 'Binarization:', 'name': 'binarize_method', 'type': 'list', 'value': BINARIZATIONS[0],
         'limits': list(BINARIZATIONS),
         'tip': 'Width modulation: the width of the on stripes follows the amplitude of the target, so that the '
                'selected order has this amplitude (the binary Lee hologram). Threshold: the pattern is cut at the '
                'threshold below, the amplitude of the target is then lost (at 0.5 only its phase is kept)'},
        {'title': 'threshold', 'name': 'threshold', 'type': 'float', 'value': 0.5, 'limits': [0., 1.],
         'tip': 'Level above which the pattern is 1 (binarization by threshold)'},
        {'title': 'Remove carrier:', 'name': 'remove_carrier', 'type': 'bool', 'value': True,
         'tip': 'Remove the linear phase of the filtered order: the spectrum is shifted so that the position of the '
                'order goes to the zero frequency (needs the mask applied to the intermediate plane)'},
        {'title': 'Carrier from:', 'name': 'carrier_from', 'type': 'list', 'value': CARRIER_FROM[1],
         'limits': list(CARRIER_FROM),
         'tip': 'Position of the order: the center of the mask, or the center of gravity of the intensity of the '
                'spectrum inside the mask (closer to the real peak)'},
        {'title': 'Carrier factor:', 'name': 'carrier_factor', 'type': 'float', 'value': 1., 'step': 0.01,
         'decimals': 6, 'tip': 'The carrier removed is this factor times the position of the order (1: all of it)'},
    ]

    def __init__(self, parent: 'AlgoApp' = None, *args, **kwargs):
        super().__init__(parent)

    def threshold_amplitude(self, amplitude: np.ndarray):
        """ Cut the pattern at the threshold: a DMD pixel is either on or off"""
        threshold = self.settings['threshold']
        amplitude[amplitude > threshold] = 1
        amplitude[amplitude <= threshold] = 0
        return amplitude

    def compute_amplitude_pattern(self) -> np.ndarray:
        xx, yy = self.compute_grid()

        modulation_depth = self._target_field.normalise_to_one().amplitude  # 1 where the target is the brightest
        phase = 2 * np.pi * (xx - yy) / self.settings['super_pixel'] - self._target_field.phase

        if self.settings['binarize'] and self.settings['binarize_method'] == BINARIZATIONS[0]:
            # binary Lee hologram: the pixel is on where cos(phase) > cos(pi * w), the stripes of relative width
            # w = arcsin(A) / pi give a first order of amplitude A. Where A = 0 the pixels are off
            return (np.cos(phase) > np.sqrt(1 - np.clip(modulation_depth, 0., 1.) ** 2)).astype(float)

        amplitude_dmd = 1 / 2 * (1 + modulation_depth * np.cos(phase))
        if self.settings['binarize']:
            amplitude_dmd = self.threshold_amplitude(amplitude_dmd)

        return amplitude_dmd

    def get_carrier(self, spectrum: np.ndarray = None) -> tuple[float, float] | None:
        """ Position (rows, columns) of the order selected by the intermediate mask relative to the zero frequency, in
        pixels, multiplied by the *carrier factor*

        It is the center of the mask or, with the spectrum already filtered by the mask, its center of gravity.
        None if the mask is not applied to the intermediate plane
        """
        if not self.apply_mask(apply_to=ApplyMaskTo.INTERMEDIATE):
            return None
        slices = self.get_mask_slices(ApplyMaskTo.INTERMEDIATE)
        if slices is None:
            return None
        if self.settings['carrier_from'] == CARRIER_FROM[1] and spectrum is not None:
            carrier = spectrum_centroid(spectrum)
        else:
            # center of the pixels covered by the slices, relative to the index of the zero frequency
            carrier = tuple((_slice.start + _slice.stop - 1) / 2 - size // 2
                            for _slice, size in zip(slices, self.shape))
        return tuple(self.settings['carrier_factor'] * value for value in carrier)

    def compute_phase_and_or_amplitude(self, do_step=True, **kwargs):

        amplitude_pattern = self.compute_amplitude_pattern()

        self.set_amplitude_in_modulator_plane(amplitude_pattern)

        self.compute_intermediate_field()
        self.compute_output_from_intermediate()
        if self.settings['remove_carrier']:
            carrier = self.get_carrier(self.intermediate_field.field)
            if carrier is None:
                logger.warning('The carrier cannot be removed: apply a mask to the intermediate plane')
            else:
                self._output_field.field = remove_linear_phase(self._output_field.field, *carrier)






