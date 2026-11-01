import numpy as np

from pymodaq_plugins_beam_shaping.field import Field
from pymodaq_plugins_beam_shaping.field.operations.base import FieldOperation, OperationFactory
from pymodaq_plugins_beam_shaping.field.operations import compute

MODE_TITLES = {'piston': 'Piston', 'tilt_x': 'Tilt X', 'tilt_y': 'Tilt Y', 'defocus': 'Defocus'}


@OperationFactory.register_operation()
class RemoveZernike(FieldOperation):
    """ Remove piston, tilts and/or defocus fitted on a pupil

    The pupil is a disk centered on the barycenter of the intensity (on the support). Its radius is the largest disk
    inside the support if the Radius setting is 0. The four modes are always fitted together (least squares on the
    unwrapped phase, weighted by the intensity if asked), only the checked ones are removed. The coefficients are in
    rad (unit RMS modes on the pupil, Noll normalisation), the piston is shown wrapped in ]-pi, pi]. A wrapped phase
    stays wrapped, an unwrapped one (after Unwrap phase) stays unwrapped.
    """
    OPERATION_NAME = 'Remove Zernike'
    params = [
        {'title': 'Remove', 'name': 'modes', 'type': 'group', 'children': [
            {'title': MODE_TITLES[mode], 'name': mode, 'type': 'bool', 'value': True}
            for mode in compute.ZERNIKE_MODES]},
        {'title': 'Radius (pxl)', 'name': 'radius', 'type': 'float', 'value': 0., 'min': 0.,
         'tip': '0: the largest disk inside the support'},
        {'title': 'Weighted', 'name': 'weighted', 'type': 'bool', 'value': True,
         'tip': 'weight the fit by the intensity'},
    ]
    results = ([{'title': f'{MODE_TITLES[mode]} (rad)', 'name': mode, 'type': 'float', 'value': 0., 'decimals': 4}
                for mode in compute.ZERNIKE_MODES] +
               [{'title': 'Center X (pxl)', 'name': 'center_x', 'type': 'float', 'value': 0., 'decimals': 2},
                {'title': 'Center Y (pxl)', 'name': 'center_y', 'type': 'float', 'value': 0., 'decimals': 2},
                {'title': 'Radius used (pxl)', 'name': 'radius', 'type': 'float', 'value': 0., 'decimals': 2}])

    def apply(self, field: Field, support: np.ndarray) -> Field:
        center, radius = compute.pupil_from_support(field.amplitude, support)
        if self.settings['radius'] > 0:
            radius = self.settings['radius']
        weights = field.intensity if self.settings['weighted'] else None
        coefficients, basis = compute.fit_zernike(field.phase, support, center, radius, weights)

        for mode, value in coefficients.items():
            # the piston of an unwrapped phase is only known modulo 2pi
            self.set_result(mode, float(compute.wrap(value)) if mode == 'piston' else value)
        self.set_result('center_y', center[0])
        self.set_result('center_x', center[1])
        self.set_result('radius', radius)

        to_remove = np.zeros(field.shape)
        for mode in compute.ZERNIKE_MODES:
            if self.settings['modes', mode]:
                to_remove += coefficients[mode] * basis[mode]
        return self.new_field(field, phase=compute.subtract_phase(field.phase, to_remove))
