# -*- coding: utf-8 -*-
"""
Algorithms for amplitude modulators such as DMDs: binary holograms in a 4f line with a filter in the Fourier plane

The binary pattern sent to the modulator is a hologram: a grating of carrier ``nu`` whose fringes encode the phase
(and the amplitude) of the target. The filter in the intermediate plane selects one diffraction order, which is the
target field. The methods follow the review

    [1] Gutiérrez-Cuevas et al., *Binary holograms for shaping light with digital micromirror devices*,
    J. Phys. Photonics 6, 045022 (2024), https://arxiv.org/abs/2311.16685

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
from pymodaq_plugins_beam_shaping.utilities import regions

if TYPE_CHECKING:
    from pymodaq_plugins_beam_shaping.algorithms.algorithm_app import AlgoApp


logger = set_logger(get_module_name(__file__))
plugin_config = PluginConfig()


CARRIER_FROM = ('Mask center', 'Spectrum centroid')
STATUS_NOTE_CODE_ONLY = 'Code only: the filtered order is checked against the theory in simulation, not on a bench'


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




class BinaryHologram(AlgoBase):
    """ Base of the binary holograms of a 4f line, with a filter in the Fourier plane selecting one diffraction order

    The pattern is a grating of carrier ``nu = (1 / px, -1 / py)`` (in cycles per pixel along x and y, the lattice of
    the review [1], ``py / px`` being an integer, 0 for ``py``: aligned grating ``nu = (1 / px, 0)``) whose fringes
    are shifted by the phase of the target. The order filtered by the mask of the intermediate plane, the order
    (-1, 0) at ``-nu`` in the review (the one that carries the phase of the target), is the target field. Its linear
    phase (the carrier) is removed numerically, see :meth:`get_carrier`: in the setup it should be cancelled by
    moving the second lens off the optical axis, with the filter.

    Subclasses implement :meth:`compute_amplitude_pattern`.
    """
    MODULATOR_TYPES = (ModulatorType.AMPLITUDE, )
    SETUP_TYPE = LensSetup.FourF
    ITERATIVE = False
    RECOMPUTE_ON_CHANGE = True

    _params_carrier = [
        {'title': 'Remove carrier:', 'name': 'remove_carrier', 'type': 'bool', 'value': True,
         'tip': 'Remove the linear phase of the filtered order: the spectrum is shifted so that the position of the '
                'order goes to the zero frequency (needs the mask applied to the intermediate plane)'},
        {'title': 'Carrier from:', 'name': 'carrier_from', 'type': 'list', 'value': CARRIER_FROM[1],
         'limits': list(CARRIER_FROM),
         'tip': 'Position of the order: the center of the mask, or the center of gravity of the intensity of the '
                'spectrum inside the mask (closer to the real peak)'},
        {'title': 'Carrier factor:', 'name': 'carrier_factor', 'type': 'float', 'value': 1., 'step': 0.01,
         'decimals': 6, 'tip': 'The carrier removed is this factor times the position of the order (1: all of it)'},
        {'title': 'Order position:', 'name': 'order_position', 'type': 'str', 'value': '', 'readonly': True,
         'tip': 'Position of the order to filter (-1, 0) in the intermediate plane, and the slices of a mask around '
                'it, to copy to the slices of the Intermediate Masking'},
    ]
    _params_period = [
        {'title': 'Period px (pxls):', 'name': 'px', 'type': 'int', 'value': 4, 'min': 2,
         'tip': 'Period of the grating along x, in pixels'},
        {'title': 'Period py (pxls):', 'name': 'py', 'type': 'int', 'value': 16, 'min': 0,
         'tip': 'Period of the grating along y, in pixels, an integer multiple of px (the lattice of the review). '
                'The default px**2 is the compromise of the review. 0: aligned grating, along x only'},
    ]

    def __init__(self, parent: 'AlgoApp' = None, *args, **kwargs):
        super().__init__(parent)

    def value_changed(self, param):
        if param.name() == 'order_position':
            return
        if param.name() in ('px', 'py'):
            if self.fix_period():  # a value was corrected, this function is called again with the valid one
                return
            self.update_order_position()
        super().value_changed(param)

    def fix_period(self) -> bool:
        """ py has to be 0 or an integer multiple of px (as the lattice of the review). Returns True if it was changed"""
        px, py = self.settings['px'], self.settings['py']
        if py != 0 and py % px != 0:
            self.settings.child('py').setValue(max(px, int(round(py / px)) * px))
            return True
        return False

    def compute_grid(self) -> tuple[np.ndarray, np.ndarray]:
        """ The positions (x, y) of the pixels in pixels, with the origin at the index N // 2, the one of the fields
        transformed by Field.fft2 / ifft2: the phase of the grating is then zero at the origin of the carrier removal,
        and the output field has the phase of the target (not shifted by half a pixel of carrier)"""
        x = np.arange(self.shape[1]) - self.shape[1] // 2
        y = np.arange(self.shape[0]) - self.shape[0] // 2
        return np.meshgrid(x, y)

    def carrier_phase(self) -> np.ndarray:
        """ The phase 2 pi nu . r of the grating at each pixel"""
        xx, yy = self.compute_grid()
        phase = 2 * np.pi * xx / self.settings['px']
        if self.settings['py'] != 0:
            phase -= 2 * np.pi * yy / self.settings['py']
        return phase

    def order_frequency(self) -> tuple[float, float]:
        """ Position (rows, columns) of the order (-1, 0), at -nu, relative to the zero frequency in pixels of the
        intermediate plane, that is in cycles per array"""
        ny, nx = self.shape
        return (ny / self.settings['py'] if self.settings['py'] != 0 else 0.), -nx / self.settings['px']

    def order_slices(self) -> tuple[slice, slice]:
        """ Slices of a mask around the order in the intermediate plane, in the units of the settings of the masks (um)
        (window of a third of the distance of the order to the zero order)"""
        pixel_sizes = regions.pixel_sizes_in_um(self.intermediate_pixel_sizes)
        centre = np.array(self.shape) // 2 + np.array(self.order_frequency())
        half = np.hypot(*self.order_frequency()) / 3
        return tuple(slice((index - half) * size, (index + half) * size) for index, size in zip(centre, pixel_sizes))

    def update_order_position(self):
        """ Update the text of the order position, with the slices of a mask around it if the setup is known"""
        try:
            rows, columns = self.order_frequency()
            text = f'(rows, columns) = ({rows:.1f}, {columns:.1f}) pxls from the zero order'
        except (TypeError, ZeroDivisionError, AttributeError):
            return
        try:
            text += f'; slices: {regions.slices_to_str(self.order_slices())}'
        except (TypeError, ValueError, AttributeError, IndexError):
            pass  # no setup (fields, pixel sizes) yet
        if text != self.settings['order_position']:
            self.settings.child('order_position').setValue(text)

    def compute_amplitude_pattern(self) -> np.ndarray:
        raise NotImplementedError

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
        self.update_order_position()
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


@AlgorithmFactory.register_algorithm()
class BinaryThreshold(BinaryHologram):
    """ Binary threshold hologram: **phase only**

    The grey pattern ``1/2 (1 + cos(2 pi nu . r - phi))`` (the off-axis hologram of the review [1], eq. 5, with a
    constant amplitude) is cut at the threshold (the mean, 0.5, by default), so that a pixel is on where
    ``cos(2 pi nu . r - phi) > 0`` (eq. 9). The amplitude of the target is lost: only its phase is encoded, in
    the position of the fringes. This is the first binary hologram, O. Bryngdahl and A. W. Lohmann, J. Opt. Soc.
    Am. 58, 141 (1968), and a baseline for the others.

    Unchecking *Binarize* keeps the grey levels of the pattern (an ideal modulation, not feasible on a DMD).
    """

    ALGO_NAME = 'Binary Threshold'
    STATUS = AlgoStatus.TESTED
    STATUS_NOTE = STATUS_NOTE_CODE_ONLY
    ALGOTYPE = AlgoType.PHASE

    params = (
        BinaryHologram._params_period +
        [{'title': 'Binarize:', 'name': 'binarize', 'type': 'bool', 'value': True,
          'tip': 'Binarize the pattern to 0 and 1, as a DMD can only do. Unchecked: the grey levels of the pattern '
                 'are kept (ideal modulation, to see what the binarization costs)'},
         {'title': 'threshold', 'name': 'threshold', 'type': 'float', 'value': 0.5, 'limits': [0., 1.],
          'tip': 'Level above which the grey pattern is 1 (0.5: the mean, the pixel is on where '
                 'cos(2 pi nu . r - phi) > 0)'}] +
        BinaryHologram._params_carrier)

    def compute_amplitude_pattern(self) -> np.ndarray:
        amplitude_dmd = 1 / 2 * (1 + np.cos(self.carrier_phase() - self._target_field.phase))
        if self.settings['binarize']:
            amplitude_dmd = (amplitude_dmd > self.settings['threshold']).astype(float)
        return amplitude_dmd


@AlgorithmFactory.register_algorithm()
class ParallelLee(BinaryHologram):
    """ Parallel Lee hologram: **amplitude and phase**

    The fringes of the grating are shifted by the phase of the target and their width follows its amplitude A (the
    target normalised so that its maximum is 1): a pixel is on where ``cos(2 pi nu . r - phi) > cos(pi q)``, with
    ``A = sin(pi q)`` (review [1], eq. 11). The amplitude and the phase are coded along the same direction, which
    couples them. The method is the one of W.-H. Lee, Appl. Opt. 13, 1677 (1974), *Binary synthetic holograms*
    (see also B. R. Brown and A. W. Lohmann, Appl. Opt. 5, 967 (1966)).

    Unchecking *Binarize* keeps the grey pattern ``1/2 (1 + A cos(2 pi nu . r - phi))`` (the off-axis hologram of the
    review, eq. 5, an ideal modulation not feasible on a DMD).

    The amplitude levels the binary pattern can render are limited by the period of the grating: a wide period (8
    pixels or more along x) gives a more faithful amplitude.
    """

    ALGO_NAME = 'Parallel Lee'
    STATUS = AlgoStatus.TESTED
    STATUS_NOTE = STATUS_NOTE_CODE_ONLY
    ALGOTYPE = AlgoType.AMPLITUDE_PHASE

    params = (
        BinaryHologram._params_period +
        [{'title': 'Binarize:', 'name': 'binarize', 'type': 'bool', 'value': True,
          'tip': 'Binarize the pattern to 0 and 1, as a DMD can only do (width modulation of the fringes). '
                 'Unchecked: the grey levels of the pattern are kept (ideal modulation)'}] +
        BinaryHologram._params_carrier)

    def compute_amplitude_pattern(self) -> np.ndarray:
        modulation_depth = self._target_field.normalise_to_one().amplitude  # 1 where the target is the brightest
        phase = self.carrier_phase() - self._target_field.phase
        if self.settings['binarize']:
            # the pixel is on where cos(phase) > cos(pi q): stripes of relative width q = arcsin(A) / pi. Where A = 0
            # the pixels are off
            return (np.cos(phase) > np.sqrt(1 - np.clip(modulation_depth, 0., 1.) ** 2)).astype(float)
        return 1 / 2 * (1 + modulation_depth * np.cos(phase))
