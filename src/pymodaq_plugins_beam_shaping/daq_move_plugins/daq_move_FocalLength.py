
from typing import Union, List, Dict, TYPE_CHECKING
from pymodaq.control_modules.move_utility_classes import (DAQ_Move_base, comon_parameters_fun,
                                                          main, DataActuatorType, DataActuator)

from pymodaq_utils.utils import ThreadCommand  # object used to send info back to the main thread
from pymodaq_gui.parameter import Parameter

if TYPE_CHECKING:
    from pymodaq_plugins_beam_shaping.utilities.corrections import Correction


class DAQ_Move_FocalLength(DAQ_Move_base):
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
    _axis_names: Union[List[str], Dict[str, int]] = ['Focal']
    _controller_units: Union[str, List[str]] = 'cm'
    _epsilons: Union[float, List[float]] = 0.1
    data_actuator_type = DataActuatorType.DataActuator

    params = [] + comon_parameters_fun(is_multiaxes, axis_names=_axis_names, epsilon=_epsilons)

    def ini_attributes(self):
        self.controller: 'Correction' = None

    def get_actuator_value(self):
        """Get the current value from the hardware with scaling conversion.

        Returns
        -------
        DataActuator: The position obtained after scaling conversion.
        """
        return self.target_value

    def ini_stage(self, controller: 'Correction' = None):
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
        self.controller: 'Correction' = controller

        info = "Focal Length Move initialized"
        initialized = True
        return info, initialized

    def move_abs(self, value: DataActuator):
        """ Move the actuator to the absolute target defined by value

        Parameters
        ----------
        value: (float) value of the absolute target positioning
        """

        value = self.check_bound(value)  #if user checked bounds, the defined bounds are applied here
        self.target_value = value
        value = self.set_position_with_scaling(value)  # apply scaling if the user specified one

        self.controller.set_focal_length(value.value(units=self.axis_unit))

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

    def close(self):
        pass

if __name__ == '__main__':
    main(__file__, init=False)
