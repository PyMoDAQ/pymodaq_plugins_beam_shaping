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
from pymodaq_plugins_beam_shaping.algorithms.utils import LensSetup, ApplyMaskTo, AlgoType
from pymodaq_plugins_beam_shaping.algorithms import AlgoBase
from pymodaq_plugins_beam_shaping.utils import Config as PluginConfig
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


class TorchBase(AlgoBase):
    """ Usage of torch package to get optimization of a loss expression

    The corresponding experimental setup should define a working light wavelength and a focal length
    of the used lens
    """

    ALGO_NAME = None
    ALGOTYPE = AlgoType.AMPLITUDE  # depends and defined in the loss
    SETUP_TYPE = LensSetup.TwoF
    ITERATIVE = True
    MANUAL_LOOP = False

    params = [
        {'title': 'Max Iterations', 'name': 'max_iter', 'type': 'int', 'value': 100, 'min': 1},
        {'title': 'Tolerance', 'name': 'tolerance', 'type': 'float', 'value': 1e-9},

        {'title': 'Loss', 'name': 'loss', 'type': 'list', 'value': loss_factory.losses[0],
         'limits': loss_factory.losses},
        {'title': 'Loss Value', 'name': 'loss_value', 'type': 'float', 'value': 0.,},
        {'title': 'Loss Parameters', 'name': 'loss_params', 'type': 'group', 'children': []}
    ]

    def __init__(self, parent: 'AlgoApp' = None, *args, **kwargs):
        super().__init__(parent)
        self._slices: tuple[slice, slice] = None
        self.iter = 0

        self._algo_init = False
        self._phase_tensor: torch.Tensor = None
        self._target_tensor: torch.Tensor = None
        self._amplitude_tensor: torch.Tensor = None
        self.image_field_array: np.ndarray = None
        self.mask: torch.Tensor = None
        self.ratio: torch.Tensor = None

        self._calculated_fitness: float = 0.

        self.optimizer = None  # a given optimizer

        for loss in loss_factory.losses:
            self.settings.child('loss_params').addChild({'title': loss, 'name': loss, 'type': 'group',
                                                         'visible': self.settings['loss'] == loss,
                                                         'children': loss_factory.get_loss(loss).params})

        self._loss = loss_factory.get_loss(self.settings['loss'])(self.settings.child('loss_params',
                                                                                      self.settings['loss']))

    def value_changed(self, param: Parameter):
        #self.parent_app.algo_settings_changed()
        if param.name() == 'loss':
            for param_child in self.settings.child('loss_params').children():
                param_child.show(param.value() == param_child.name())
            self._loss = loss_factory.get_loss(param.value())(self.settings.child('loss_params', param.value()))

    def do_things_after_set_target(self):
        if self._algo_init:  #make sure target and object have same shape
            #self._target_field.phase = self._target_field.phase / np.max(self._target_field.phase) * np.pi
            target_tensor = torch.from_numpy(self._target_field.field)

            #normalize target_intensity wrt input amplitude
            self._target_tensor = self.normalize_intensity_wrt(target_tensor, self._amplitude_tensor)

    def do_things_after_set_input(self):
        self._modulator_field.amplitude = self._input_field.amplitude
        self._amplitude_tensor = torch.from_numpy(self.modulator_field.amplitude)

    @staticmethod
    def compute_intensity_ratio(tensor: torch.Tensor, tensor_ref: torch.Tensor) -> torch.Tensor:
        return torch.sqrt((torch.sum(torch.abs(tensor_ref)**2) /
                           torch.sum(torch.abs(tensor)**2)))

    def normalize_intensity_wrt(self, tensor: torch.Tensor, tensor_ref: torch.Tensor) -> torch.Tensor:
        return tensor * self.compute_intensity_ratio(tensor, tensor_ref)

    def do_things_after_init(self):
        # Initialize phase distribution as trainable parameter
        self.phase_distribution = self.modulator_field.phase
        self._amplitude_tensor = torch.from_numpy(self.modulator_field.amplitude)

        if not self._algo_init:
            self._algo_init = True
            self.do_things_after_set_target()

        fft_tensor = self.compute_image_field(torch.zeros_like(self._amplitude_tensor))
        self.ratio = self.compute_intensity_ratio(fft_tensor, self._amplitude_tensor)

        self.ini_optimizer()

    # def do_things_after_set_input(self):
    #     self.do_things_after_init()

    def ini_optimizer(self):
        """ To be reimplemented"""
        raise NotImplementedError

    @property
    def phase_distribution(self):
        return self._phase_tensor.detach().numpy()

    @phase_distribution.setter
    def phase_distribution(self, value: np.ndarray):
        self._phase_tensor = torch.tensor(value.copy(), requires_grad=True)

    def compute_image_field(self, phase_input: torch.Tensor) -> torch.Tensor:
        output_tensor = torch.fft.fftshift(
            torch.fft.fft2(self._amplitude_tensor * torch.exp(1j * phase_input), norm='forward'
            )
        )
        return output_tensor

    def compute_mask(self):
        if self.apply_mask(apply_to=ApplyMaskTo.TARGET):
            self.mask = torch.tensor(self.get_mask_field(ApplyMaskTo.TARGET).amplitude, dtype=torch.float32)
        else:
            self.mask = torch.ones_like(self._amplitude_tensor, dtype=torch.float32)
        self.update_mask = False

    def compute_loss(self, phase) -> torch.Tensor:
        output_tensor = self.ratio * self.compute_image_field(phase)

        loss = self._loss.compute_loss(output_tensor * self.mask,
                                       self._target_tensor * self.mask)
        self.settings.child('loss_value').setValue(loss.item())
        return loss


    def compute_phase_and_or_amplitude(self, do_step=True, ini_phase=None, **kwargs):
        """ To be reimplemented """
        raise NotImplementedError


