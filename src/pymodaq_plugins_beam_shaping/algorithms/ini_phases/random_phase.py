import numpy as np

from pymodaq_plugins_beam_shaping.algorithms.ini_phase import PhaseFactory, PhaseBase


@PhaseFactory.register_phase()
class RandomPhase(PhaseBase):
    """ Uniform random phase in [0, 2 pi[

    With a fixed seed, the same pattern is obtained each time the phase is computed (reproducible runs). Otherwise a
    new pattern is drawn each time.
    """
    params = [
        {'title': 'Fixed seed', 'name': 'fixed_seed', 'type': 'bool', 'value': False,
         'tip': 'If True, the random pattern is generated from the seed below and is therefore the same each time. '
                'Otherwise a different pattern is drawn each time'},
        {'title': 'Seed', 'name': 'seed', 'type': 'int', 'value': 0, 'min': 0,
         'tip': 'Seed of the random generator, change it to get another reproducible pattern'},
    ]

    def compute_phase(self) -> np.ndarray:
        seed = self.settings['seed'] if self.settings['fixed_seed'] else None
        return np.random.default_rng(seed).random(self.algo.shape) * 2 * np.pi
