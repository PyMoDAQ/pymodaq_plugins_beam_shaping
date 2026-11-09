import numpy as np

from pymodaq_utils.logger import set_logger, get_module_name

from pymodaq_plugins_beam_shaping.algorithms.compensation import CompensationBase, CompensationFactory, block_average

logger = set_logger(get_module_name(__file__))


@CompensationFactory.register_compensation()
class DivideByInput(CompensationBase):
    """ The target is divided by the amplitude of the input beam, so that the output is the target and not the target
    times the beam profile

    The modulator multiplies the amplitude of the input beam by a transmission t (0 to 1). To get the target, t is
    target / input, scaled so that its maximum is 1 (the efficiency is the price of the flat output). Where the input
    is lower than the *minimum input level* (relative to its maximum) the target cannot be obtained: t is 0 and the
    pixel belongs to the unreachable region.
    """

    params = [
        {'title': 'Min input level:', 'name': 'min_input_level', 'type': 'float', 'value': 0.2, 'min': 0.,
         'max': 1., 'step': 0.01,
         'tip': 'Fraction of the maximum of the input amplitude below which the target cannot be obtained (the '
                'region is the unreachable one, drawn in red)'},
    ]

    def compensate(self, target: np.ndarray, input_amplitude: np.ndarray, block: int = 1):
        peak = float(np.max(input_amplitude)) if input_amplitude.size else 0.
        if peak == 0.:
            return target, None
        if input_amplitude.shape != target.shape:  # not expected: the field loaders give the same shape to both
            logger.warning('The input and the target do not have the same shape: the input is not compensated')
            return target, None
        if block > 1:
            input_amplitude = block_average(input_amplitude, block)
        reachable = input_amplitude >= self.settings['min_input_level'] * peak
        transmission = np.where(reachable, target / np.where(reachable, input_amplitude, 1.), 0.)
        maximum = float(np.max(transmission))
        return (transmission / maximum if maximum > 0 else transmission), ~reachable
