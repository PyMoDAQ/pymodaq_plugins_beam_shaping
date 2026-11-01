import numpy as np

from pymodaq_plugins_beam_shaping.field import Field
from pymodaq_plugins_beam_shaping.field.operations.base import FieldOperation, OperationFactory
from pymodaq_plugins_beam_shaping.field.operations import compute


@OperationFactory.register_operation()
class UnwrapPhase(FieldOperation):
    """ Unwrap the phase on the support (scikit-image unwrap_phase), the phase outside the support is kept"""
    OPERATION_NAME = 'Unwrap phase'
    params = [
        {'title': 'Only on support', 'name': 'on_support', 'type': 'bool', 'value': True,
         'tip': 'unwrap only where the amplitude is above the threshold (the noisy phase outside spoils it)'},
    ]

    def apply(self, field: Field, support: np.ndarray) -> Field:
        return self.new_field(field, phase=compute.unwrap(field.phase,
                                                          support if self.settings['on_support'] else None))
