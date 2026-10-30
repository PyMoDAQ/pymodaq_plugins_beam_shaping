
from typing import Union, List, Dict

import numpy as np

from pymodaq.control_modules.move_utility_classes import (DAQ_Move_base, comon_parameters_fun,
                                                          main, DataActuatorType, DataActuator)

from pymodaq_utils.utils import ThreadCommand  # object used to send info back to the main thread
from pymodaq_gui.parameter import Parameter

from pymodaq_plugins_beam_shaping.hardware.mock_shaper_camera import ShaperCamera
from pymodaq_plugins_beam_shaping.utilities.shaper import (shaper_params, fill_shaper_settings, get_default_shaper,
                                                            ModulatorType, Shaper)
from pymodaq_plugins_beam_shaping.utilities import sizing


class DAQ_Move_MockShaper(DAQ_Move_base):
    """ Instrument plugin class for an actuator.
    
    This object inherits all functionalities to communicate with PyMoDAQ’s DAQ_Move module through inheritance via
    DAQ_Move_base. It makes a bridge between the DAQ_Move module and the Python wrapper of a particular instrument.

    Attributes:
    -----------
    controller: object
        The particular object that allow the communication with the hardware, in general a python wrapper around the
         hardware library.
         

    """
    is_multiaxes = False
    _axis_names: Union[List[str], Dict[str, int]] = ['']
    _controller_units: Union[str, List[str]] = ''
    _epsilons: Union[float, List[float]] = 0.1
    data_actuator_type = DataActuatorType.DataActuator

    params = shaper_params() + comon_parameters_fun(is_multiaxes, axis_names=_axis_names, epsilon=_epsilons)


    def ini_attributes(self):
        self.controller: ShaperCamera = None

    def set_shaper_geometry(self, shaper: Shaper):
        """Fill the shaper settings groups read by the BeamShaping extension"""
        fill_shaper_settings(self.settings, shaper.name, shaper.width, shaper.height, shaper.pixel_size,
                             modulator_type=shaper.modulator_type,
                             has_internal_calibration=shaper.has_internal_calibration)

    def get_actuator_value(self):
        """Get the current value from the hardware with scaling conversion.

        Returns
        -------
        float: The position obtained after scaling conversion.
        """
        return DataActuator('shaper', data=[self.controller.get_slm_phases()])


    def close(self):
        """Terminate the communication protocol"""
        if self.is_master:
            pass

    def commit_settings(self, param: Parameter):
        """Apply the consequences of a change of value in the detector settings

        Parameters
        ----------
        param: Parameter
            A given parameter (within detector_settings) whose value has been changed by the user
        """
        pass

    def ini_stage(self, controller=None):
        """Actuator communication initialization

        Parameters
        ----------
        controller: (object)
            custom object of a PyMoDAQ plugin (Slave case). None if only one actuator by controller (Master case)

        Returns
        -------
        info: str
        initialized: bool
            False if initialization failed otherwise True
        """
        if self.is_master:  # is needed when controller is master
            shaper = get_default_shaper()  # the mock is a shaper like the one of the preferences
            self.controller = ShaperCamera(shaper)
            self.set_shaper_geometry(shaper)
            initialized = True
        else:
            self.controller = controller
            initialized = True

        info = "Whatever info you want to log"
        return info, initialized

    def move_abs(self, value: DataActuator):
        """ Move the actuator to the absolute target defined by value

        Parameters
        ----------
        value: (float) value of the absolute target positioning
        """

        value = self.check_bound(value)
        self.target_value = value
        value = self.set_position_with_scaling(value)

        if value.shape == (1,):
            value.data = [value[0][0] * np.ones_like(self.controller.get_slm_phases())]

        modulator_type = ModulatorType(self.settings['shaper_properties', 'modulator_type'])
        if modulator_type == ModulatorType.AMPLITUDE:  # one array: the amplitude
            self.controller.apply_amplitude(value[0])
        elif modulator_type == ModulatorType.BOTH and np.iscomplexobj(value[0]):  # one complex array: amplitude * e^(i phase)
            self.controller.apply_amplitude(np.abs(value[0]))
            self.controller.apply_phase(np.angle(value[0]))
        else:  # one array: the phase (or grey levels)
            if 'as_grey_levels' in value.extra_attributes and value.as_grey_levels:
                self.controller.apply_grey_scale(value[0])
            else:
                self.controller.apply_phase(value[0])

        self.current_value = value
        self.emit_status(ThreadCommand('Update_Status', ['SLM Updated']))

    def move_rel(self, value: DataActuator):
        """ Move the actuator to the relative target actuator value defined by value

        Parameters
        ----------
        value: (float) value of the relative target positioning
        """
        value = self.check_bound(self.current_value + value) - self.current_value
        self.target_value = value + self.current_value
        value = self.set_position_relative_with_scaling(value)

        self.move_abs(self.target_value)

    def move_home(self):
        """Call the reference method of the controller"""
        pass

    def stop_motion(self):
        """Stop the actuator and emits move_done signal"""
        pass


if __name__ == '__main__':
    main(__file__)
