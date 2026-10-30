import numpy as np

from pymodaq_utils.math_utils import find_index
from pymodaq_utils.utils import ThreadCommand
from pymodaq_data.data import DataToExport, Axis
from pymodaq_gui.parameter import Parameter

from pymodaq.control_modules.viewer_utility_classes import DAQ_Viewer_base, comon_parameters, main
from pymodaq.utils.data import DataFromPlugins

from pymodaq_plugins_beam_shaping.hardware.mock_shaper_camera import ShaperCamera


class DAQ_2DViewer_MockShaperCamera(DAQ_Viewer_base):
    """ Instrument plugin class for a 2D viewer.
    
    This object inherits all functionalities to communicate with PyMoDAQ’s DAQ_Viewer module through inheritance via
    DAQ_Viewer_base. It makes a bridge between the DAQ_Viewer module and the Python wrapper of a particular instrument.

    Attributes:
    -----------
    controller: object
        The particular object that allow the communication with the hardware, in general a python wrapper around the
         hardware library.
    """
    params = comon_parameters + [
        {'title': 'Gaussian FWHM (µm)', 'name': 'gaussian_width', 'type': 'float',
         'value': ShaperCamera.gaussian_width_ini},
        {'title': 'Calibration', 'name': 'calibration', 'type': 'group', 'children':[
            {'title': 'Insert slits', 'name': 'insert_slits', 'type': 'bool', 'value': False},
            {'title': 'Slit Width (µm)', 'name': 'slit_width', 'type': 'float', 'value': 100},
            {'title': 'Slit Spacing (µm)', 'name': 'slit_spacing', 'type': 'float', 'value': 500},
        ],},
    ]

    def ini_attributes(self):
        self.controller: ShaperCamera = None

    def commit_settings(self, param: Parameter):
        """Apply the consequences of a change of value in the detector settings

        Parameters
        ----------
        param: Parameter
            A given parameter (within detector_settings) whose value has been changed by the user
        """
        if param.name() == "gaussian_width":
            self.controller.gaussian_width = param.value()

    def get_mask_from_slits(self):
        xx, yy = self.controller.get_slm_grid()
        x_axis = xx[0]
        mask = np.zeros(xx.shape)
        ind_slit_11 = find_index(x_axis, - self.settings['calibration', 'slit_spacing'] / 2 -
                                 self.settings['calibration', 'slit_width'])[0][0]
        ind_slit_12 = find_index(x_axis, - self.settings['calibration', 'slit_spacing'] / 2 )[0][0]
        ind_slit_21 = find_index(x_axis, self.settings['calibration', 'slit_spacing'] / 2)[0][0]
        ind_slit_22 = find_index(x_axis, self.settings['calibration', 'slit_spacing'] / 2  +
                                 self.settings['calibration', 'slit_width'])[0][0]

        mask[:, ind_slit_11: ind_slit_12] = 1
        mask[:, ind_slit_21: ind_slit_22] = 1

        return mask

    def ini_detector(self, controller=None):
        """Detector communication initialization

        Parameters
        ----------
        controller: (object)
            custom object of a PyMoDAQ plugin (Slave case). None if only one actuator/detector by controller
            (Master case)

        Returns
        -------
        info: str
        initialized: bool
            False if initialization failed otherwise True
        """
        if self.is_master:
            self.controller = ShaperCamera()
            initialized = True
        else:
            self.controller = controller
            initialized = True

        info = ""
        return info, initialized

    def close(self):
        """Terminate the communication protocol"""
        pass

    def grab_data(self, Naverage=1, **kwargs):
        """Start a grab from the detector

        Parameters
        ----------
        Naverage: int
            Number of hardware averaging (if hardware averaging is possible, self.hardware_averaging should be set to
            True in class preamble and you should code this implementation)
        kwargs: dict
            others optionals arguments
        """

        data_array = self.controller.get_camera(self.get_mask_from_slits()
                                                if self.settings['calibration', 'insert_slits'] else None)
        self.dte_signal.emit(DataToExport('FFT data',
                                          data=[DataFromPlugins(name='Mock1', data=[data_array],
                                                                dim='Data2D', labels=['FFT data'])]))



    def stop(self):
        """Stop the current grab hardware wise if necessary"""
        pass


if __name__ == '__main__':
    main(__file__)
