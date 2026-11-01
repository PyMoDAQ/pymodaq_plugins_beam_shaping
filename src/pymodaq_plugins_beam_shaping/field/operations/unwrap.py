import numpy as np

from pymodaq_utils.enums import StrEnum

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


class WrapRange(StrEnum):
    SYMMETRIC = ']-pi, pi]'
    POSITIVE = '[0, 2pi['


@OperationFactory.register_operation()
class WrapPhase(FieldOperation):
    """ Wrap the phase on the whole field, in ]-pi, pi] (SYMMETRIC) or [0, 2pi[ (POSITIVE)"""
    OPERATION_NAME = 'Wrap phase'
    params = [
        {'title': 'Range', 'name': 'range', 'type': 'list', 'value': WrapRange.SYMMETRIC.name,
         'limits': WrapRange.names(), 'tip': 'SYMMETRIC: ]-pi, pi]; POSITIVE: [0, 2pi['},
    ]

    def apply(self, field: Field, support: np.ndarray) -> Field:
        if WrapRange[self.settings['range']] == WrapRange.SYMMETRIC:
            return self.new_field(field, phase=compute.wrap(field.phase))
        return self.new_field(field, phase=compute.wrap_positive(field.phase))
