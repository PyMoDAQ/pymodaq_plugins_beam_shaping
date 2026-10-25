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
class Direct(AlgoBase):
    """ This algorithm is just sending the selected Target Field to the modulator (either the phase, amplitude or both
    depending on the shaper modulation type)
    """

    ALGO_NAME = 'Direct'
    ALGOTYPE = AlgoType.AMPLITUDE_PHASE
    SETUP_TYPE = LensSetup.NoLens
    ITERATIVE = False
    INI_PHASE = False

    params = [
    ]

    def __init__(self, parent: 'AlgoApp' = None, *args, **kwargs):
        super().__init__(parent)

    def get_target_pixels_size(self, input_size: Tuple[Q_, Q_] = None) -> list[Q_]:
        """ Get the expected physical size of the pixels in the target plane given
        the chosen algorithm and physical parameters: focal length, wavelength...

        Here The algorithm is not dependent on the setup as we just define a field to be directly applied to the
        modulator

        """
        return self._input_field.pixels_sizes

    def compute_phase(self, do_step=True, **kwargs):
        self.set_field_in_modulator_plane(self.normalize_wrt(self._target_field, self._input_field))








