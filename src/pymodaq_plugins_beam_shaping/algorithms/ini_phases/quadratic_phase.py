from dataclasses import dataclass

import numpy as np

from pymodaq_utils.math_utils import my_moment

from pymodaq_data import Q_

from pymodaq_plugins_beam_shaping.algorithms.ini_phase import PhaseFactory, PhaseBase
from pymodaq_plugins_beam_shaping.utils import Config
from pymodaq_plugins_beam_shaping.utilities import sizing
from pymodaq_plugins_beam_shaping.algorithms.utils import LensSetup, ApplyMaskTo
from pymodaq_plugins_beam_shaping.field import Field

plugin_config = Config()


@dataclass
class FieldSize:
    x_size: float = None
    y_size: float = None

    def __init__(self, field: Field):
        self.x_size = my_moment(field.get_axis_from_index(1)[0].get_data(),
                                np.sum(field.amplitude, axis=0))[1]
        self.y_size = my_moment(field.get_axis_from_index(0)[0].get_data(),
                                np.sum(field.amplitude, axis=1))[1]



@PhaseFactory.register_phase()
class QuadraticPhase(PhaseBase):
    """ The phase is built from this expression: R (p**2 + q**2) + D (p cos θ + q sin θ) where p and q are
    the normalized pixel indexes

    see https://doi.org/10.1364/OE.25.011692
    """
    params = [
        {'title': 'Quadratic Amplitude', 'name': 'quadratic', 'type': 'group', 'children': [
            {'title': 'Auto: ', 'name': 'auto', 'type': 'bool', 'value': True,
             'tip': 'If True, the X and Y quadratic phase amplitude are computed/updated from the target mask size '},
            {'title': 'X Quad. (1/µm)² ', 'name': 'x_quad', 'type': 'float', 'value': 1.},
            {'title': 'Y Quad. (1/µm)²', 'name': 'y_quad', 'type': 'float', 'value': 1.},
            {'title': 'Coeff', 'name': 'coeff', 'type': 'float', 'value': 1.,
             'tip': 'A multiplicative coefficient to adjust the initial size in the output plane while still using the '
                    'Auto mode'},
        ]},
        {'title': 'Linear Shift', 'name': 'shift', 'type': 'group', 'children': [
            {'title': 'Auto: ', 'name': 'auto', 'type': 'bool', 'value': True,
             'tip': 'If True, the X and Y shift are computed/updated from the target mask position '},
            {'title': 'X Shift (1/µm) ', 'name': 'x_shift', 'type': 'float', 'value': 0.},
            {'title': 'Y shift (1/µm)', 'name': 'y_shift', 'type': 'float', 'value': 0.},
        ]},
    ]

    def get_input_output_size(self) -> tuple[FieldSize, FieldSize]:

        return FieldSize(self.algo.modulator_field), FieldSize(self.algo.target_field_pixels_sizes[0])

    def compute_phase(self, **kwargs) -> np.ndarray:
        binning = plugin_config('sizing', 'binning')
        pixel_sizes = Q_(np.array([self.algo.input_field_pixels_sizes[ind].magnitude / binning for ind in range(2)]),
                         self.algo.input_field_pixels_sizes[0].units)

        ny, nx = self.algo.shape
        xlin_um = (np.linspace(-nx // 2, nx // 2, nx, endpoint=True) * pixel_sizes[1]).to('um').magnitude
        ylin_um = (np.linspace(-ny // 2, ny // 2, ny, endpoint=True) * pixel_sizes[0]).to('um').magnitude

        if self.settings['quadratic', 'auto']:
            self._compute_quadratic_factor()

        yy_quad, xx_quad = np.meshgrid(self.settings['quadratic', 'y_quad'] / 2 * ylin_um ** 2,
                                       self.settings['quadratic', 'x_quad'] / 2 * xlin_um ** 2, indexing='ij')
        phase = xx_quad + yy_quad

        if self.settings['shift', 'auto']:
            self._compute_linear_factor()  # approximated from lens computation

        yylin, xxlin = np.meshgrid(self.settings['shift', 'y_shift'] * ylin_um,
                                   self.settings['shift', 'x_shift'] * xlin_um, indexing='ij')
        phase += xxlin + yylin
        return phase

    def _compute_quadratic_factor(self):
        if self.algo.apply_mask(ApplyMaskTo.TARGET):
            _slices = self.algo.get_mask_slices(ApplyMaskTo.TARGET)
            size = [(_slice.stop - _slice.start)
                    // (_slice.step if _slice.step is not None else 1) + 1 for _slice in _slices]
        else:
            size = self.algo.shape

        pixel_SLM = Q_(sizing.get_effective_slm_pixel_size(self.algo.shaper), 'um')

        slm_size = [slm_size * pixel_SLM for slm_size in sizing.get_effective_slm_size(self.algo.shaper)]
        mask_size_um = Q_.from_list([size[0] * self.algo.target_field_pixels_sizes[0],
                                     size[1] * self.algo.target_field_pixels_sizes[1]])

        setup_type = plugin_config('setup', 'setup_type')[0]
        focal_postSLM = Q_(plugin_config('setup', setup_type, 'focals')[0], 'mm')
        wavelength = Q_(plugin_config('setup', 'wavelength_nm'), 'nm')

        fft_limited_size = Q_.from_list([focal_postSLM * np.tan(
            np.asin(wavelength / (2 * slm_size[ind]))) for ind in range(2)])

        dk0 = 2* np.pi / wavelength * np.sin(np.atan2(fft_limited_size, focal_postSLM))
        dkc =  2* np.pi / wavelength * np.sin(np.atan2(mask_size_um, focal_postSLM))

        add_hoc_coeff = 0.175 * sizing.get_binning()

        quad_phase = add_hoc_coeff * self.settings['quadratic', 'coeff'] * (
                2 * dk0 ** 2 * np.sqrt((dkc / dk0) ** 2 - 1 )).to('1/um**2').magnitude

        self.settings.child('quadratic', 'x_quad').setValue(quad_phase[1])
        self.settings.child('quadratic', 'y_quad').setValue(quad_phase[0])

    def _compute_linear_factor(self):
        if self.algo.apply_mask(ApplyMaskTo.TARGET):
            _slices = self.algo.get_mask_slices(ApplyMaskTo.TARGET)
            shift_y, shift_x = tuple([(_slice.stop + _slice.start) / 2 - self.algo.shape[ind] / 2
                                      for ind, _slice in enumerate(_slices)])
        else:
            shift_y, shift_x = (0., 0.)
        shifts = (shift_y, shift_x)
        setup_type = plugin_config('setup', 'setup_type')[0]
        focal_postSLM = Q_(plugin_config('setup', setup_type, 'focals')[0], 'mm')
        wavelength = Q_(plugin_config('setup', 'wavelength_nm'), 'nm')

        coeffs_um_inv = [(2 * np.pi / wavelength *
                          np.sin(np.atan2(shifts[ind] * self.algo.target_field_pixels_sizes[ind], focal_postSLM)))
                         .to('1/um').magnitude for ind in range(2)]

        self.settings.child('shift', 'x_shift').setValue(coeffs_um_inv[1])
        self.settings.child('shift', 'y_shift').setValue(coeffs_um_inv[0])