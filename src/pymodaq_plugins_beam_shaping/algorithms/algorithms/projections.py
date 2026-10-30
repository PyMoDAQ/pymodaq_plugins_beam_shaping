# -*- coding: utf-8 -*-
"""
Created the 20/07/2023

@author: Sebastien Weber
"""
from pathlib import Path
from typing import Union, Tuple, List, TYPE_CHECKING, Any

import numpy as np
from pymodaq_utils.enums import StrEnum
from pymodaq_utils.logger import set_logger, get_module_name
from pymodaq.utils.data import DataFromPlugins, DataToExport, DataRaw
from pymodaq_utils import math_utils as mutils
from pymodaq_data import Q_
from pymodaq_gui.parameter import Parameter

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
class GbSax(AlgoBase):
    """ Implementation of the Gerchberg-Saxton iterative algorithm to create amplitude modulated
    image with phase only spatial light modulators in the Fourier plane of a converging lens

    The corresponding experimental setup should define a working light wavelength and a focal length
    of the used lens
    """

    ALGO_NAME = 'Gerchberg-Saxton'
    ALGOTYPE = AlgoType.AMPLITUDE
    SETUP_TYPE = LensSetup.TwoF
    ITERATIVE = True

    params = []

    def __init__(self, parent: 'AlgoApp' = None, *args, **kwargs):
        super().__init__(parent)
        self._algo_init = False

    def value_changed(self, param: Parameter):
        self.parent_app.algo_settings_changed()

    def do_things_after_set_target(self):
        if self._algo_init:  #make sure target and object have same shape

            #normalize target_intensity wrt input intensity
            self._target_field = self.normalize_wrt(self._target_field, self._input_field)

    def do_things_after_init(self):
        if not self._algo_init:
            self._algo_init = True
            self.do_things_after_set_target()

    def do_things_after_set_input(self):
        """ Apply the initial phase to the object field """

        pass

    def propagate_field(self):
        self.compute_forward_fft(update_plots=False)

    def evolve_field(self):

        amplitude = self._target_field.amplitude

        field_output_corrected = Field(amplitude=amplitude,
                                      phase=self._output_field.phase,
                                      pixel_sizes=self._output_field.pixels_sizes)

        field_modulator_corrected = self.compute_backward_fft(field_output_corrected)
        self.set_phase_in_modulator_plane(field_modulator_corrected.phase)

    def compute_phase_and_or_amplitude(self, do_step=True, **kwargs):
        self.propagate_field()
        self.evolve_field()


@AlgorithmFactory.register_algorithm()
class Projections(GbSax):
    """ Implementation of the Gerchberg-Saxton with options to implement variants like weighted, ROI, MRAF...

    The corresponding experimental setup should define a working light wavelength and a focal length
    of the used lens

    The weighted algorithm is based on paper https://doi.org/10.1364/OE.413723
    The MRAF algorithm is based on https://doi.org/10.1364/OE.16.002176
        ROI is restricted to rectangular or elliptical area

    """

    ALGO_NAME = 'Projections'
    ITERATIVE = True


    params = [
        {'title': 'Weighting', 'name': 'weighting', 'type': 'bool', 'value': False,
         'tip': 'If True, applies a weighting between calculated output amplitude and target amplitude'},
        {'title': 'Mixing ratio', 'name': 'mixing_ratio', 'type': 'float', 'value': 0.5, 'limits': [0., 1.],
         'tip': 'The mixing ratio correspond to the MRAF hyperparameter. A ROI in the target plane must be selected'
                'for this to work. A value of 1 corresponds to the standard Gerchberg-Saxton algorithm'},]

    def __init__(self, parent: 'AlgoApp' = None, *args, **kwargs):
        super().__init__(parent)

        self.amplitude_mask: Field = None

    def evolve_field(self):
        if self.update_mask:
            self.update_mask = False
            if self.apply_mask(apply_to=ApplyMaskTo.TARGET):
                self.amplitude_mask = self.get_mask_field(ApplyMaskTo.TARGET, inner_value=1, outer_value=0)

            else:
                self.amplitude_mask = Field('mask', amplitude=np.ones_like(self._target_field.amplitude))

        mask_target = self.amplitude_mask.amplitude
        mask_noise = np.ones_like(mask_target) - mask_target

        if self.settings['weighting']:
            weight = np.sum((np.exp(np.abs(self._target_field.amplitude - self.output_field.amplitude))))
        else:
            weight = 1

        amplitude = (self.settings['mixing_ratio'] * weight * self._target_field.amplitude * mask_target +
                     (1-self.settings['mixing_ratio']) * self._output_field.amplitude * mask_noise)

        field_output_corrected = Field(amplitude=amplitude,
                                      phase=self._output_field.phase,
                                      pixel_sizes=self._output_field.pixels_sizes)

        field_modulator_corrected = self.compute_backward_fft(field_output_corrected)
        self.set_phase_in_modulator_plane(field_modulator_corrected.phase)





