# -*- coding: utf-8 -*-
"""Compensation of the beam profile of the input beam, a piece of code of its own like the initial phase

The modulator multiplies the input beam by what it is asked to do: for an algorithm that computes the pattern of the
modulator from the target directly (binary holograms, checkerboard), the output is the target times the profile of the
beam, unless the pattern is computed for a target divided by this profile. Such a compensation can not give light
where the input has none: this region is *unreachable*.

A compensation is a class registered in the :class:`CompensationFactory`, with its own parameters shown in the
settings of the algorithm app, in the modules of the package ``compensations``. It works on arrays only.
"""
from abc import ABC, abstractmethod
from importlib import import_module
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from pymodaq_gui.parameter import Parameter
from pymodaq_utils.logger import set_logger, get_module_name

logger = set_logger(get_module_name(__file__))

NO_COMPENSATION = 'NoCompensation'  # name of the compensation that does nothing


def register_compensations(parent_module_name: str = 'pymodaq_plugins_beam_shaping'):
    """ Browse the modules containing compensations and register them in the factory"""
    compensations = []
    try:
        compensation_module = import_module(f'{parent_module_name}.algorithms.compensations')
        compensation_path = Path(compensation_module.__path__[0])
        for file in sorted(compensation_path.iterdir()):
            if file.is_file() and file.suffix == '.py' and file.stem != '__init__':
                try:
                    compensations.append(import_module(f'.{file.stem}', compensation_module.__name__))
                except (ModuleNotFoundError, NotImplementedError) as e:
                    logger.warning(str(e))
    except ModuleNotFoundError as e:
        logger.warning(str(e))
    return compensations


def block_average(array: np.ndarray, n: int) -> np.ndarray:
    """ Each element replaced by the mean of its block of n x n elements (the blocks on the edges are cut)"""
    ny, nx = array.shape
    blocks_y, blocks_x = -(-ny // n), -(-nx // n)
    padded = np.zeros((blocks_y * n, blocks_x * n))
    counts = np.zeros(padded.shape)
    padded[:ny, :nx], counts[:ny, :nx] = array, 1.
    sums = padded.reshape(blocks_y, n, blocks_x, n).sum(axis=(1, 3))
    number = counts.reshape(blocks_y, n, blocks_x, n).sum(axis=(1, 3))
    return np.kron(sums / number, np.ones((n, n)))[:ny, :nx]


class CompensationBase(ABC):
    """ Base class of the compensations of the input beam

    Parameters
    ----------
    settings: Parameter
        the group holding the parameters defined in :attr:`params`
    """

    params: list[dict] = []  # definition of the specific parameters of the compensation

    def __init__(self, settings: Parameter):
        self.settings = settings

    @abstractmethod
    def compensate(self, target: np.ndarray, input_amplitude: np.ndarray, block: int = 1
                   ) -> tuple[np.ndarray, Optional[np.ndarray]]:
        """ The amplitude to ask to the modulator to get the target with this input beam

        Parameters
        ----------
        target: the amplitude of the target
        input_amplitude: the amplitude of the input beam on the modulator, of the same shape
        block: the input seen by the modulator is its average over blocks of block x block pixels (a superpixel)

        Returns
        -------
        the compensated amplitude, and the boolean array of the unreachable region (None if there is no such region)
        """

    def unreachable(self, input_amplitude: np.ndarray, block: int = 1) -> Optional[np.ndarray]:
        """ The region where the target cannot be obtained, knowing only the input beam (None if no such region)"""
        return self.compensate(np.ones_like(input_amplitude, dtype=float), input_amplitude, block)[1]


class CompensationFactory:
    """ The factory class for creating compensations of the input beam"""

    _registry: dict[str, type[CompensationBase]] = {}

    @classmethod
    def register_compensation(cls) -> Callable:
        """ Class decorator to register a compensation, above the definition of a CompensationBase class"""

        def inner_wrapper(wrapped_class: type[CompensationBase]) -> type[CompensationBase]:
            name = wrapped_class.__name__
            if name not in cls._registry:
                cls._registry[name] = wrapped_class
            return wrapped_class

        return inner_wrapper

    @classmethod
    def get_compensation(cls, name: str) -> type[CompensationBase]:
        if name not in cls._registry:
            raise ValueError(f'{name} is not a supported compensation of the input beam.')
        return cls._registry[name]

    @property
    def compensations(self) -> list[str]:
        """ The names of the compensations, the one that does nothing first"""
        return sorted(self._registry, key=lambda name: (name != NO_COMPENSATION, name))
