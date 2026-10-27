from typing import Tuple, Union
import numpy as np
from pathlib import Path
from dataclasses import dataclass
from time import perf_counter
from zernpy import ZernPol

from qtpy import QtWidgets, QtCore, QtGui


from pymodaq_data import Q_
from pymodaq.utils.data import DataActuator

from pymodaq_gui.utils.custom_app import CustomApp, Dock, DockArea
from pymodaq_gui.utils.widgets.widget_bkg import WidgetWithBkg

from pymodaq_gui.plotting.data_viewers.viewer2D import Viewer2D
from pymodaq_gui.utils.widgets.spinbox import SpinBox

from pymodaq_plugins_beam_shaping import config as plugin_config
from pymodaq_plugins_beam_shaping.utilities.zernike import (ZernikeUI, SliderSpinBox,
                                                            ZernikeCoeffs)
from pymodaq_plugins_beam_shaping.utilities import sizing

here = Path(__file__).parent

@dataclass()
class CorrectionValues:
    tilt_x: float = 0.
    tilt_y: float = 0.
    focal_length: float = 0.
    zernike: ZernikeCoeffs = ZernikeCoeffs()


beam_fwhm = Q_(np.sqrt(1/2*(
        plugin_config('input', 'gaussian', 'fwhm_x')**2 +
        plugin_config('input', 'gaussian', 'fwhm_y')**2)),
               'mm')


class Correction(CustomApp):

    correction_changed = QtCore.Signal(CorrectionValues)
    phase_changed = QtCore.Signal(DataActuator)

    _plugin_config = plugin_config

    def __init__(self, parent: DockArea, beam_fwhm=beam_fwhm, **kwargs):
        super().__init__(parent, **kwargs)

        self._zernike_ui: ZernikeUI = None
        self._zernike_coeffs = ZernikeCoeffs()
        self.zernike_values: dict[str, np.ndarray] = {}
        self.setup_ui()

        self.beam_fwhm_sb.setValue(beam_fwhm.m_as('mm'))

        self.timing = perf_counter()
        self.compute_zernike_base()

    @property
    def beam_fwhm(self) -> Q_:
        """ Get/Set the beam FWHM in intensity as a Quantity"""
        return Q_(self.beam_fwhm_sb.value(), 'mm')

    @beam_fwhm.setter
    def beam_fwhm(self, fwhm: Q_):
        if fwhm.is_compatible_with(self.beam_fwhm):
            self.beam_fwhm_sb.setValue(fwhm.m_as('mm'))

    def get_corrections(self) -> CorrectionValues:
        return CorrectionValues(self.tilt_x.value(),
                                self.tilt_y.value(),
                                self.focal_length.value(),
                                self._zernike_coeffs)

    def emit_corrections(self):
        corrections = self.get_corrections()
        self.correction_changed.emit(corrections)
        self.phase_changed.emit(self.compute_corrections(corrections))
        print(perf_counter() - self.timing)
        self.timing = perf_counter()

    def update_zernike(self, n: int, m: int, value: float):
        self._zernike_coeffs.set(n, m, value)
        self.emit_corrections()

    def setup_docks(self):

        self.docks['corrections'] = Dock('Corrections')
        self.dockarea.addDock(self.docks['corrections'])

        self.set_toolbar(QtWidgets.QToolBar())
        self.unit_radius_sb = SpinBox(value=2.0)
        self.unit_radius_sb.setMaximumWidth(100)

        self.beam_fwhm_sb = SpinBox(value=plugin_config('input', 'gaussian', 'fwhm_x'),
                                    suffix = 'mm')
        self.beam_fwhm_sb.setMaximumWidth(100)

        main_widget = QtWidgets.QWidget()
        self.docks['corrections'].addWidget(main_widget)

        main_widget.setLayout(QtWidgets.QVBoxLayout())
        main_widget.layout().addWidget(self._toolbar)
        widget_main_correction = QtWidgets.QWidget()
        widget_main_correction.setLayout(QtWidgets.QGridLayout())

        self.tilt_x = SliderSpinBox(value=0., bounds=(-20, 20))
        self.tilt_y = SliderSpinBox(value=0., bounds=(-20, 20))
        self.focal_length = SliderSpinBox(value=0., bounds=(-1000, 1000))

        widget_main_correction.layout().addWidget(QtWidgets.QLabel('Shift X (mm)'), 0, 0)
        widget_main_correction.layout().addWidget(self.tilt_x, 1, 0)

        widget_main_correction.layout().addWidget(QtWidgets.QLabel('Shift Y (mm)'), 0, 1)
        widget_main_correction.layout().addWidget(self.tilt_y, 1, 1)

        widget_main_correction.layout().addWidget(QtWidgets.QLabel('Focal Length (cm)'), 0, 2)
        widget_main_correction.layout().addWidget(self.focal_length, 1, 2)

        main_widget.layout().addWidget(widget_main_correction)

        widget_zernike = QtWidgets.QWidget()
        widget_zernike.setLayout(QtWidgets.QHBoxLayout())

        widget = WidgetWithBkg(here.parent.joinpath('resources/zernike.png'))
        self._zernike_ui = ZernikeUI(widget)

        main_widget.layout().addWidget(widget_zernike)
        widget_zernike.layout().addWidget(widget)

        self.viewer_widget = QtWidgets.QWidget()
        self.viewer2D = Viewer2D(self.viewer_widget)
        widget_zernike.layout().addWidget(self.viewer_widget)
        self.viewer_widget.setVisible(False)

    def set_focal_length(self, focal: Q_ | float):
        """ Programmatically set the focal length using a Quantity or explicit float as cm"""
        if isinstance(focal, Q_):
            self.focal_length.setValue(focal.m_as('cm'))
        else:
            self.focal_length.setValue(focal)

    def set_zernike_polynomial(self, n: int, m: int, value: float):
        """ Programmatically set the Zernike Polynomials by updating the UI"""
        self._zernike_ui.sliders[f'{n}{m}'].setValue(value)

    def setup_actions(self):
        self.add_action('show_phase', 'Show Phase', 'visibility', tip='Display the correction phase in a 2D Viewer',
                        checkable=True, toolbar=self._toolbar, icon_checked='visibility_off')
        self.add_widget('beam_fwhm_label', QtWidgets.QLabel('Beam FWHM: '), toolbar=self._toolbar)
        self.add_widget('beam_fwhm', self.beam_fwhm_sb, toolbar=self._toolbar,
                        tip='Input beam FWHM in Intensity')
        self.add_widget('unity_radius_label', QtWidgets.QLabel('Unity Radius: '), toolbar=self._toolbar)
        self.add_widget('unity_radius', self.unit_radius_sb, toolbar=self._toolbar,
                        tip='Unity radius for Zernike polynomials, '
                            'expressed as a multiple factor of the Input Beam FWHM')
        self.add_action('reset', 'Reset', 'refresh')

    def connect_things(self):
        self._zernike_ui.slider_changed_sig.connect(self.update_zernike)
        self.tilt_x.valueChanged.connect(self.emit_corrections)
        self.tilt_y.valueChanged.connect(self.emit_corrections)
        self.focal_length.valueChanged.connect(self.emit_corrections)

        self.connect_action('show_phase', lambda show:self.viewer_widget.setVisible(show))
        self.connect_action('reset', self.reset)

        self.connect_action('unity_radius', self.compute_zernike_base,
                            signal_name='sigValueChanged')
        self.connect_action('beam_fwhm', self.compute_zernike_base,
                            signal_name='sigValueChanged')

    def reset(self):
        self.tilt_y.setValue(0.)
        self.tilt_x.setValue(0.)
        self.focal_length.setValue(0.)
        self._zernike_ui.reset()

    def compute_corrections(self, correction: CorrectionValues) -> DataActuator:
        quad_phase_array = self.compute_focal_phase(correction.focal_length)
        linear_phase_array = self.compute_linear_phase(correction.tilt_x, correction.tilt_y)
        zernike_phase = self.compute_zernike_phase(correction.zernike)

        phase = DataActuator('Correction phase',
                             data=[quad_phase_array+linear_phase_array+zernike_phase])

        if self.is_action_checked('show_phase'):
            self.viewer2D.show_data(phase)

        return phase

    def compute_zernike_phase(self, zernike: ZernikeCoeffs) -> np.ndarray[float, float]:
        """

        Parameters
        ----------
        zernike

        Returns
        -------

        """
        zernike_phase = np.zeros(self.shape)

        for n in range(zernike.order_max):
            for m in range(-n, n+2, 2):
                if np.abs(zernike.get(n, m)) > 0.001:
                    zernike_phase += zernike.get(n, m) * self.zernike_values[f'{n}{m}']
        return zernike_phase * 2 * np.pi

    def compute_zernike_base(self):
        pixel_size = Q_(sizing.get_effective_slm_pixel_size(), 'um')
        unity_radius = self.unit_radius_sb.value() * self.beam_fwhm

        xlin, ylin = self._get_xy()
        xlin *= pixel_size
        ylin *= pixel_size
        yy, xx = np.meshgrid(ylin, xlin, indexing='ij')

        r = (np.sqrt(xx**2 + yy**2) / unity_radius).to_base_units().magnitude
        r[r>=1.] = 0.
        theta = np.angle(xx.magnitude + 1j*yy.magnitude)

        for n in range(self._zernike_ui.order_max):
            for m in range(-n, n+2, 2):
                zern_pol = ZernPol(n=n, m=m)
                self.zernike_values[f'{n}{m}'] = zern_pol.polynomial_value(r, theta)

    def _get_xy(self) -> tuple[np.ndarray, np.ndarray]:
        """ Get the pixel indexes from the selected SLM centered on the center of the SLM

        Return:
        -------
        x: np.ndarray
        y: np.ndarray
        """
        shape = self.shape
        return  (np.linspace(-shape[1] // 2, shape[1] // 2, shape[1], endpoint=True),
                 np.linspace(-shape[0] // 2, shape[0] // 2, shape[0], endpoint=True),
                 )

    def compute_focal_phase(self, focal_value: float) -> np.ndarray[float, float]:
        """ compute the phase to send to the SLM to achieve this focal length

        Parameters
        ----------
        focal_value: float
            required focal length value in cm
        """
        if np.abs(focal_value) < 0.01:
            coeff = 0.
        else:
            focal_length = Q_(focal_value, 'cm')
            pixel_size = Q_(sizing.get_effective_slm_pixel_size(), 'um')
            wavelength = Q_(self._plugin_config('setup', 'wavelength_nm'), 'nm')

            coeff =  float((pixel_size ** 2 / (wavelength * focal_length) * np.pi).to_reduced_units().magnitude)

        xlin, ylin = self._get_xy()
        yquad = coeff * ylin ** 2
        xquad = coeff * xlin ** 2

        yy, xx = np.meshgrid(yquad, xquad, indexing='ij')
        return yy + xx

    def compute_linear_phase(self, tiltx: float, tilty: float) -> np.ndarray[float, float]:
        xlin, ylin = self._get_xy()
        #todo: specify the algorithm/setup use because for now the linear shift will be done only for 2f setups

        shift_x = Q_(tiltx, 'mm')
        shift_y = Q_(tilty, 'mm')
        pixel_SLM = Q_(sizing.get_effective_slm_pixel_size(), 'um')
        setup_type = self._plugin_config('setup', 'setup_type')[0]
        focal_postSLM = Q_(self._plugin_config('setup', setup_type, 'focals')[0], 'mm')
        wavelength = Q_(self._plugin_config('setup', 'wavelength_nm'), 'nm')

        coeff = (2*np.pi / (wavelength * focal_postSLM))
        ylin *= (shift_y * coeff * pixel_SLM).to_reduced_units().magnitude
        xlin *= (shift_x * coeff * pixel_SLM).to_reduced_units().magnitude
        yy, xx = np.meshgrid(ylin, xlin, indexing='ij')

        return yy + xx

    @property
    def shape(self) -> tuple[int, int]:
        """ Get the effective shape of the fields in the plane of the SLM"""
        return sizing.get_effective_needed_field_size()[0], sizing.get_effective_needed_field_size()[1]


def main():
    from pymodaq_gui.qt_utils import mkQApp

    def print_corrections(corrections: CorrectionValues):
        print(corrections)

    app = mkQApp('Optical Shaping')

    area = DockArea()
    area.show()

    correction = Correction(area)
    correction.correction_changed.connect(print_corrections)

    app.exec()


if __name__ == '__main__':
    main()