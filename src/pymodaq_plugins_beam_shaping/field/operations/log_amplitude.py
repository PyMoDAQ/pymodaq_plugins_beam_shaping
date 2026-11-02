import numpy as np

from pymodaq_plugins_beam_shaping.field import Field
from pymodaq_plugins_beam_shaping.field.operations.base import FieldOperation, OperationFactory
from pymodaq_plugins_beam_shaping.field.operations import compute


@OperationFactory.register_operation()
class Log10Amplitude(FieldOperation):
    """ Replace the amplitude by log10(amplitude / max), clipped at a floor, to see the weak parts of a field

    The phase is kept. Put it at the end of the chain: the fits of the other operations are weighted by the intensity.
    """
    OPERATION_NAME = 'Log10 amplitude'
    params = [
        {'title': 'Floor', 'name': 'floor', 'type': 'float', 'value': 1e-4, 'min': 1e-12, 'max': 1.,
         'tip': 'smallest relative amplitude (amplitude / max) kept: avoids log10(0), sets the dynamic shown'},
    ]
    results = [
        {'title': 'Min (log10)', 'name': 'min', 'type': 'float', 'value': 0., 'decimals': 3},
    ]

    def apply(self, field: Field, support: np.ndarray) -> Field:
        amplitude = compute.log10_amplitude(field.amplitude, self.settings['floor'])
        self.set_result('min', float(np.min(amplitude)) if amplitude.size else 0.)
        return self.new_field(field, amplitude=amplitude)
