import numpy as np

from pymodaq_plugins_beam_shaping.algorithms.compensation import CompensationBase, CompensationFactory


@CompensationFactory.register_compensation()
class NoCompensation(CompensationBase):
    """ The output is the target times the profile of the input beam"""

    def compensate(self, target: np.ndarray, input_amplitude: np.ndarray, block: int = 1):
        return target, None
