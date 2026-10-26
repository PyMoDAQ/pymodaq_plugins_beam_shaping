from pymodaq_gui.utils.widgets.widget_bkg import WidgetWithBkg
from qtpy import QtWidgets, QtCore


from pymodaq_gui.utils.custom_app import CustomApp
from pymodaq_gui.parameter.pymodaq_ptypes import SliderSpinBox
from pymodaq_plugins_beam_shaping.utils import Config

plugin_config = Config()


class ZernikeCoeffs:
    order_max = plugin_config('corrections', 'zernike', 'order_max')
    def __init__(self, zernike_coeffs: dict = None):
        if zernike_coeffs is None:
            zernike_coeffs = {}
            for n in range(self.order_max):
                for m in range(-n, n+2, 2):
                    zernike_coeffs[f'{n}{m}'] = 0.
        self._zernike_coeffs = zernike_coeffs
        
    def get(self, n:int, m: int):
        return self._zernike_coeffs.get(f'{n}{m}', None)

    def set(self, n: int, m: int, value: float):
        self._zernike_coeffs[f'{n}{m}'] = value

    def __repr__(self):
        return f'{self._zernike_coeffs}'


class ZernikeUI(CustomApp):

    slider_changed_sig = QtCore.Signal(int, int, float)

    def __init__(self, parent):
        super().__init__(parent)

        self.order_max = 5
        self.bounds = (-10, 10)

        self.setup_ui()

    def setup_docks_and_widgets(self):
        self.grid_layout = QtWidgets.QGridLayout()
        self.parent.setLayout(self.grid_layout)

        self.sliders = {}
        for n in range(self.order_max):
            for m in range(-n, n+2, 2):
                self.sliders[f'{n}{m}'] = SliderSpinBox(value=0., bounds=self.bounds)
                self.sliders[f'{n}{m}'].valueChanged.connect(self.create_lambda(n, m))
                self.parent.layout().addWidget(self.sliders[f'{n}{m}'], n, m+self.order_max,
                                               QtCore.Qt.AlignmentFlag.AlignHCenter|QtCore.Qt.AlignmentFlag.AlignBottom)

    def reset(self):
        for slider in self.sliders:
            self.sliders[slider].setValue(0.0)

    def create_lambda(self, n, m):
        return lambda: self.slider_changed(n, m)

    def slider_changed(self, n: int, m: int):
        self.slider_changed_sig.emit(n, m, self.sliders[f'{n}{m}'].value())

    def setup_actions(self):
        pass

    def connect_things(self):
        pass



def main():
    from pymodaq_gui.qt_utils import mkQApp

    def print_info(n, m, value):
        print(f'Slider {n},{m} has a value of  {value}')

    app = mkQApp('Optical Shaping')

    widget = WidgetWithBkg('../resources/zernike.png')
    widget.show()

    zernike_ui = ZernikeUI(widget)

    zernike_ui.slider_changed_sig.connect(print_info)

    app.exec()


if __name__ == '__main__':
    main()