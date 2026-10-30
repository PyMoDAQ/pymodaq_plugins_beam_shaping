# -*- coding: utf-8 -*-
"""
Created the 20/07/2023

see https://gregorygundersen.com/blog/2022/03/20/conjugate-gradient-descent/

@author: Sebastien Weber
"""
from typing import Optional, Union

from typing import Union, Tuple, List, TYPE_CHECKING, Any
from qtpy import QtWidgets

import numpy as np
from torch import nn
from time import perf_counter

from pymodaq_utils.logger import set_logger, get_module_name
from pymodaq_gui.parameter import Parameter

from pymodaq_plugins_beam_shaping.algorithms.loss import LossFactory
from pymodaq_plugins_beam_shaping.algorithms.factory import AlgorithmFactory
from pymodaq_plugins_beam_shaping.algorithms.utils import LensSetup, ApplyMaskTo
from pymodaq_plugins_beam_shaping.algorithms import AlgoBase
from pymodaq_plugins_beam_shaping.utils import Config as PluginConfig
from pymodaq_plugins_beam_shaping.algorithms.algorithms.torch_base import TorchBase
from pymodaq_plugins_beam_shaping.field import Field


import torch

device = torch.accelerator.current_accelerator().type if torch.accelerator.is_available() else "cpu"
print(f"Using {device} device")
torch.set_default_device(device)


if TYPE_CHECKING:
    from pymodaq_plugins_beam_shaping.algorithms.algorithm_app import AlgoApp

logger = set_logger(get_module_name(__file__))
plugin_config = PluginConfig()
loss_factory = LossFactory()


@AlgorithmFactory.register_algorithm()
class TorchOptim(TorchBase):
    """ Implementation of the ConjugateGradient iterative algorithm to create amplitude and phase modulated
    image with phase only spatial light modulators in the Fourier plane of a converging lens

    Based on Vol. 25, No. 10 | 15 May 2017 | OPTICS EXPRESS 11695 and implemented here with pytorch

    The corresponding experimental setup should define a working light wavelength and a focal length
    of the used lens
    """

    ALGO_NAME = 'TorchOptim'
    SETUP_TYPE = LensSetup.TwoF
    ITERATIVE = True
    MANUAL_LOOP = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.optimizer: torch.optim.LBFGS = None  # a given optimizer

    def ini_optimizer(self):

        self.optimizer = torch.optim.LBFGS(
            [self._phase_tensor],
            lr=1.0,
            max_iter=10,
            max_eval=None,
            tolerance_grad=self.settings['tolerance'],
            tolerance_change=self.settings['tolerance'],
            history_size=10,
            line_search_fn="strong_wolfe")
        self._algo_init = True

    def closure(self):
        self.optimizer.zero_grad()
        loss = self.compute_loss(self._phase_tensor)
        loss.backward()
        return loss

    def compute_phase_and_or_amplitude(self, do_step=True, ini_phase=None, **kwargs):
        if ini_phase is not None or self.mask is None:
            self.phase_distribution = ini_phase
            self.ini_optimizer()

        if self.mask is None or self.update_mask:
            self.compute_mask()

        self.optimizer.step(self.closure)

        self.set_phase_in_modulator_plane(self._phase_tensor.detach().numpy())
        self.compute_forward_fft(update_plots=False)
        QtWidgets.QApplication.processEvents()






