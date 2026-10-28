# -*- coding: utf-8 -*-
"""
Created the 05/12/2022

@author: Sebastien Weber
"""
from typing import List, Tuple, Any, TYPE_CHECKING
import re
import numpy as np

from pymodaq.utils.data import DataActuator
from pymodaq_data import DataDim, DataCalculated, DataRaw

from pymodaq_utils.logger import set_logger, get_module_name
from pymodaq_utils import math_utils as mutils

from pymodaq_data.data import Axis, DataDistribution, DataToExport

from pymodaq.utils.scanner.scan_factory import ScannerFactory, ScannerBase
from pymodaq.utils.scanner.scanners._1d_scanners import Scan1DBase

from pymodaq_plugins_beam_shaping.utilities.sizing import get_slm_size
from pymodaq_plugins_beam_shaping.utilities.data import DataShaper

if TYPE_CHECKING:
    from pymodaq.control_modules.daq_move import DAQ_Move

logger = set_logger(get_module_name(__file__))



@ScannerFactory.register()
class Scan1DCalibration(Scan1DBase):
    """ Defines a linear scan between start and stop values with steps of length defined in the step setting"""

    scan_subtype = 'BeamShapingCalibration'
    do_process_data = True

    params = [
        {'title': 'Grey Start:', 'name': 'start', 'type': 'float', 'value': 0},
        {'title': 'Grey Stop:', 'name': 'stop', 'type': 'float', 'value': 255},
        {'title': 'Grey Step:', 'name': 'step', 'type': 'float', 'value': 1}
        ]

    n_axes = 1
    distribution = DataDistribution.uniform

    def __init__(self, actuators: List['DAQ_Move'] = None, settings=None, **_ignored):
        super().__init__(actuators=actuators, settings=settings)
        self.index_max_fft: int = None

    def process_data(self, dte: DataToExport) -> DataToExport:
        """ Process Acquired data if the boolean class attribute *do_process_data* is set to True

        Here we suppose the dte contains a 1D Horizontal ROI presenting fringes
        """
        ind_lineout = None
        for ind, name in enumerate(dte.get_names()):
            if 'Hlineout' in name:
                ind_lineout = ind
                break


        if ind_lineout is not None:
            dwa_camera_1d = dte[ind_lineout]
        else:
            dwa_camera_1d = dte.get_data_from_dim(DataDim.Data2D)[0].sum(0)
        dwa_to_compute = dwa_camera_1d.deepcopy()
        dwa_to_compute[0] -= np.mean(dwa_to_compute[0][0])
        dwa_to_compute = dwa_to_compute.pad(2**15 - dwa_to_compute.size//2)
        dwa_to_compute.create_missing_axes()
        dwa_to_compute.add_extra_attribute(do_save=False)
        dwa_ft = dwa_to_compute.ft(axis_units='')
        if self.index_max_fft is None:
            self.index_max_fft = np.argmax(np.abs(dwa_ft.isig[dwa_ft.size//2+1000::][0]))

        phase = np.angle(dwa_ft.isig[self.index_max_fft + dwa_ft.size//2+1000][0][0])
        dwa_phase = DataCalculated('Phase', data=[np.atleast_1d(phase)], labels=['Phase'], origin='Scanner')
        dwa_phase.add_extra_attribute(do_save=True)

        dte = DataToExport('Process')
        dte.append(dwa_camera_1d)
        dte.append(dwa_phase)
        return dte

    def data_actuator_at(self, scan_index: int, axis_index=0) -> DataActuator:
        """ Get the DataActuator specified with two indexes (will be used to be sent to the actuators)

        This allows to have a difference between self.positions (simple numbers used to describe the scan, usually the
        actuator values) and the real DataActuator sent to the Actuator (that could be 0D, 1D, 2D Data, see BeamShaping
        plugin)

        To be reimplemented if needed

        """
        shaper_shape = get_slm_size()
        data = np.zeros(shaper_shape, dtype=np.uint8)
        data[:, shaper_shape[1] // 2:] = self.positions[scan_index, axis_index]
        data = data.astype(np.uint8)

        return DataShaper(self.actuators[0].title, data=[data],
                          units = self.actuators[0].units,
                          as_grey_levels=True)

    @property
    def grey_scale(self) -> np.ndarray:
        return mutils.linspace_step(self.settings['start'], self.settings['stop'],
                                          self.settings['step'])

    def set_scan(self):
        self.index_max_fft: int = None

        self.get_info_from_positions(self.grey_scale)

        self.n_axes = 1

        self.n_steps = len(self.positions)

    def evaluate_steps(self) -> int:
        n_steps = int(np.abs((self.settings['stop'] - self.settings['start']) / self.settings['step']) + 1)
        return n_steps

    def get_nav_axes(self) -> List[Axis]:

        return [Axis(label=f'{self.actuators[0].title}',
                     units=f'{self.actuators[0].units}',
                     data=self.grey_scale)]

    def get_scan_shape(self) -> Tuple[int]:
        return len(self.positions),

    def get_indexes_from_scan_index(self, scan_index: int) -> Tuple[int]:
        """To be reimplemented. Calculations of indexes within the scan"""
        return (scan_index,)

