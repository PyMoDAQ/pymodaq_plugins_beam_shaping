from qtpy import QtWidgets, QtCore

import numpy as np
import sys

from pymodaq.scripting import Detector, Actuator, Dashboard
from pymodaq.utils.data import DataActuator
from pymodaq_data import DataToExport
from pymodaq_gui.plotting.data_viewers import ViewerDispatcher
from pymodaq_gui.utils.utils import mkQApp
from pymodaq_gui.utils.widgets.window import make_window

from pymodaq_plugins_beam_shaping.utilities.shaper import get_default_shaper
from pymodaq_plugins_beam_shaping.utilities.sizing import get_slm_size





if __name__ == "__main__":
    dashboard = Dashboard()
    assert 'Shaper' in dashboard.get_devices().result()['actuators']

    qapp = mkQApp('Calibration')

    win, area = make_window(title='Calibration', flags=None)
    win.setMinimumSize(QtCore.QSize(1000, 1000))
    dispatcher = ViewerDispatcher(area)
    win.show()

    shaper = Actuator('Shaper')
    camera = Detector('Camera')

    shaper_shape = get_slm_size(get_default_shaper())  # the scripting Actuator does not give the settings of the plugin

    qapp.processEvents()


    for ind in range(0, 20, 5):
        data = np.zeros(shaper_shape)
        data[:, shaper_shape[1] // 2:] = ind
        shaper.move_abs(DataActuator('Shaper', data=[data])).result()

        dwa_camera = camera.snap().result()[0].sum(0)
        dwa_camera.create_missing_axes()
        dwa_ft = dwa_camera.ft(axis_units='')

        dte = DataToExport('Process')
        dte.append(dwa_camera)
        dte.append(dwa_ft.abs())

        dispatcher.show_data(dte)
        qapp.processEvents()

    sys.exit(qapp.exec())