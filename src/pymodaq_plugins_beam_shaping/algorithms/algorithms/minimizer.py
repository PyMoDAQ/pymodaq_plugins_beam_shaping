# -*- coding: utf-8 -*-
"""
Created the 20/07/2023

see https://gregorygundersen.com/blog/2022/03/20/conjugate-gradient-descent/

@author: Sebastien Weber
"""

from typing import TYPE_CHECKING
from qtpy import QtWidgets

import numpy as np

from pymodaq_plugins_beam_shaping.algorithms.loss import LossFactory
from pymodaq_utils.logger import set_logger, get_module_name
from pymodaq_gui.parameter import Parameter

from pymodaq_plugins_beam_shaping.algorithms.factory import AlgorithmFactory
from pymodaq_plugins_beam_shaping.algorithms.utils import LensSetup, ApplyMaskTo
from pymodaq_plugins_beam_shaping.algorithms import AlgoBase
from pymodaq_plugins_beam_shaping.utils import Config as PluginConfig
from pymodaq_plugins_beam_shaping.field import Field
from pymodaq_plugins_beam_shaping.algorithms.algorithms.torch_base import TorchBase

import torch
from torchmin import minimize



device = torch.accelerator.current_accelerator().type if torch.accelerator.is_available() else "cpu"
print(f"Using {device} device")
torch.set_default_device(device)


if TYPE_CHECKING:
    from pymodaq_plugins_beam_shaping.algorithms.algorithm_app import AlgoApp

logger = set_logger(get_module_name(__file__))
plugin_config = PluginConfig()


methods = ['bfgs',
           'l-bfgs',
           'cg',
           'newton-cg',
           'newton-exact',
           'dogleg',
           'trust-ncg',
           'trust-exact',
           'trust-krylov']

loss_factory = LossFactory()


@AlgorithmFactory.register_algorithm()
class Minimize(TorchBase):
    """ Implementation of minimization iterative algorithms to create amplitude and phase modulated
    image with phase only spatial light modulators in the Fourier plane of a converging lens

    Based on Vol. 25, No. 10 | 15 May 2017 | OPTICS EXPRESS 11695 and implemented here with pytorch
    and the pytorch-minimize package

    The corresponding experimental setup should define a working light wavelength and a focal length
    of the used lens
    """

    ALGO_NAME = 'Minimize'
    SETUP_TYPE = LensSetup.TwoF
    ITERATIVE = True
    MANUAL_LOOP = False

    params = TorchBase.params + [
        {'title': 'Method', 'name': 'method', 'type': 'list', 'value': 'l-bfgs', 'limits': methods},
    ]

    def callback(self, phase):
        self.iter += 1
        self.update_data(phase)

        if not self._running:
            ### todo could use that call to stop the inner minimize loop
            # PR in pytorch-minimize in that direction submitted and accepted
            return True

    def update_data(self, phase):
        phase = phase.detach().numpy().reshape(self.modulator_field.shape)
        # phase = (phase + np.pi) % (2 * np.pi) - np.pi
        self.set_phase_in_modulator_plane(phase)
        self.compute_forward_fft(update_plots=False)
        print(f'{self.iter}')
        self.parent_app.fields_to_plot.emit(self.get_fields_to_plot())
        QtWidgets.QApplication.processEvents()

    def ini_optimizer(self):
        """ To be reimplemented"""
        pass


    def compute_phase_and_or_amplitude(self, do_step=True, ini_phase=None, **kwargs):
        self.iter = 0

        if ini_phase is not None:
            self.phase_distribution = ini_phase
        if self.mask is None or self.update_mask:
            self.compute_mask()

        if do_step:
            max_iter = 1
        else:
            max_iter = self.settings['max_iter']
        result = minimize(self.compute_loss, self._phase_tensor,
                          method=self.settings['method'],
                          max_iter=max_iter,
                          callback=self.callback,
                          tol=self.settings['tolerance'])

        self.set_phase_in_modulator_plane(result.x.detach().numpy())
        self.compute_forward_fft(update_plots=False)





