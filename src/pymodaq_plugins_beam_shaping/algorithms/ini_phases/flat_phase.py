import numpy as np

from pymodaq_plugins_beam_shaping.algorithms.ini_phase import PhaseFactory, PhaseBase


@PhaseFactory.register_phase()
class FlatPhase(PhaseBase):
    params = [
        {'title': 'Phase value (pi)', 'name': 'phase_value', 'type': 'float', 'value': 0.},
         ]
    def compute_phase(self) -> np.ndarray:
        return np.ones(self.algo.shape) * np.pi * self.settings['phase_value']