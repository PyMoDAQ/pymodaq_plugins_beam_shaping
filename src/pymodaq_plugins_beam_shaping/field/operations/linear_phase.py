import numpy as np

from pymodaq_utils.enums import StrEnum

from pymodaq_plugins_beam_shaping.field import Field
from pymodaq_plugins_beam_shaping.field.operations.base import FieldOperation, OperationFactory
from pymodaq_plugins_beam_shaping.field.operations import compute


class LinearPhaseMethod(StrEnum):
    FFT = 'fft'
    PLANE = 'plane'


@OperationFactory.register_operation()
class RemoveLinearPhase(FieldOperation):
    """ Remove the linear phase (tilt, carrier) of the field

    * fft: slopes from the sub-pixel peak of the spectrum of the field (on the support), works on the wrapped phase
    * plane: plane fitted by least squares on the unwrapped phase of the support, weighted by the intensity

    A wrapped phase stays wrapped, an unwrapped one (after Unwrap phase) stays unwrapped.
    """
    OPERATION_NAME = 'Remove linear phase'
    params = [
        {'title': 'Method', 'name': 'method', 'type': 'list', 'value': LinearPhaseMethod.FFT.name,
         'limits': LinearPhaseMethod.names(),
         'tip': 'FFT: peak of the spectrum; PLANE: least squares plane on the unwrapped phase'},
        {'title': 'FFT padding', 'name': 'pad_factor', 'type': 'int', 'value': 2, 'min': 1, 'max': 8,
         'tip': 'zero padding factor of the FFT (method FFT only)'},
        {'title': 'Weighted', 'name': 'weighted', 'type': 'bool', 'value': True,
         'tip': 'weight the fit by the intensity (method PLANE only)'},
    ]
    results = [
        {'title': 'kx (rad/pxl)', 'name': 'kx', 'type': 'float', 'value': 0., 'decimals': 6},
        {'title': 'ky (rad/pxl)', 'name': 'ky', 'type': 'float', 'value': 0., 'decimals': 6},
        {'title': 'kx (rad/mm)', 'name': 'kx_mm', 'type': 'float', 'value': 0., 'decimals': 4},
        {'title': 'ky (rad/mm)', 'name': 'ky_mm', 'type': 'float', 'value': 0., 'decimals': 4},
    ]

    def apply(self, field: Field, support: np.ndarray) -> Field:
        if LinearPhaseMethod[self.settings['method']] == LinearPhaseMethod.FFT:
            ky, kx = compute.linear_phase_fft(field.field, support, pad_factor=self.settings['pad_factor'])
        else:
            weights = field.intensity if self.settings['weighted'] else None
            _, ky, kx = compute.linear_phase_plane(field.phase, support, weights)
        self.set_result('kx', kx)
        self.set_result('ky', ky)
        pixel_y, pixel_x = (pixel.m_as('mm') for pixel in field.pixels_sizes)
        self.set_result('kx_mm', kx / pixel_x)
        self.set_result('ky_mm', ky / pixel_y)
        return self.new_field(field, phase=compute.subtract_phase(field.phase,
                                                            compute.linear_phase(field.shape, ky, kx)))
