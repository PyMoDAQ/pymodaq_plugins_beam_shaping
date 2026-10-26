import sys
from typing import Union, TYPE_CHECKING
from pathlib import Path

import numpy as np
from scipy.interpolate import make_interp_spline, BSpline
from scipy.signal import savgol_filter

from qtpy import QtWidgets, QtCore


from pymodaq_utils.config import get_set_path, get_set_local_dir
from pymodaq_utils.logger import set_logger, get_module_name

from pymodaq_data import DataWithAxes
from pymodaq_data.h5modules.data_saving import DataLoader, DataSaverLoader

from pymodaq_gui.utils import DockArea
from pymodaq_gui.messenger import messagebox, dialog
from pymodaq_gui.plotting.data_viewers import Viewer1D

from pymodaq.extensions.scan.daq_scan import DAQScan


from pymodaq_plugins_beam_shaping.utilities.data import DataShaper


if TYPE_CHECKING:
    from pymodaq.dashboard import DashBoard


logger = set_logger(get_module_name(__file__))


# TODO: the xml file resources/holography_calibration.xml was a scan configuration of the pymodaq < 5.3 scanner manager
# (ScanManager.get_scanner_folder no longer exists). It has to be rewritten as an entry of the scan manager of 5.3
# (folder given by ScanManager.get_entry_folder) before BeamShapingCalibration can be used again.


def check_monotonic(phases: np.ndarray) -> bool:
    return np.all(np.diff(phases) >= 0.)


class Calibration(QtCore.QObject):

    def __init__(self):
        super().__init__()
        self._calibration_dwa: DataWithAxes = None
        self._interpolator: BSpline = None
        self._valid_phase_range: tuple[float, float] = None

        self.phase_viewer = Viewer1D(title='Phase')
        self.phase_viewer.parent.setVisible(False)

    @property
    def dwa(self) -> DataWithAxes:
        """ Get the DataWithAxes object storing the calibration curve"""
        if self._calibration_dwa is None:
            self._calibration_dwa = self.get_calibration_dwa()
        return self._calibration_dwa

    @property
    def valid_phase_range(self) -> tuple[float, float]:
        return self._valid_phase_range

    @property
    def interpolator(self) -> BSpline:
        if self._interpolator is None:
            phases = self.dwa[0]
            for ind in range(5, 11, 2):
                if check_monotonic(phases):
                    break
                else:
                    phases = savgol_filter(phases, window_length=ind, polyorder=3)
            if not check_monotonic(phases):
                raise ValueError('The calibration phases is not monotonically increasing.'
                                 'It should be to create BSplines')
            self._valid_phase_range = (phases.min(), phases.max())
            greys =  self.dwa.axes[0].get_data()
            self._interpolator = make_interp_spline(phases, greys)
        return self._interpolator


    def get_grey_from_phase(self, phase_array: np.ndarray) -> np.ndarray:
        """ get the Grey levels from the Bspline interpolation

        Valid phase range is between 0 and 2pi mapped to [0-255] grey levels
        """
        phase_array = phase_array % (2*np.pi)

        return np.rint(self.interpolator(phase_array)).astype(np.uint8)

    def calibrate_phase_to_grey(self, phase_array: np.ndarray) -> DataShaper:
        return DataShaper('phase_as_grey_levels',
                          data=self.get_grey_from_phase(phase_array),
                          as_grey_levels=True)

    @classmethod
    def get_calibration_dwa(cls) -> DataWithAxes:
        if cls.get_calibration_filepath().is_file():
            with DataLoader(cls.get_calibration_filepath()) as saver:
                dwa = saver.load_data_from_name_origin(where=saver.raw_group,
                                                       name='Phase',
                                                       origin='Calibration')
            return dwa
        else:
            raise NameError('Calibration file not found.')

    @classmethod
    def get_local_folder(cls, user=False) -> Path:
        """ Create a local User or system wide folder to store things about this object"""
        return get_set_path(get_set_local_dir(user=user), 'BeamShaping')

    @classmethod
    def get_calibration_folder(cls, user=False) -> Path:
        return cls.get_local_folder(user=user)

    @classmethod
    def get_calibration_filepath(cls) -> Path:
        return cls.get_calibration_folder().joinpath('calibration.h5')

    def show_calibration(self, show=True, calibration: DataWithAxes = None):
        if calibration is None:
            try:
                calibration = self.get_calibration_dwa()
            except NameError:
                messagebox(title='Calibration Data',
                           text='Could not load calibration data, '
                                'you should do a new calibration')
                return

        self.phase_viewer.setVisible(show)
        if show:
            self.phase_viewer.show_data(calibration)


class BeamShapingCalibration(DAQScan):
    def __init__(self, parent: Union[DockArea, QtWidgets.QWidget, QtWidgets.QMainWindow],
                 dashboard: 'DashBoard'):

        self.phase_viewer: Viewer1D = None
        super().__init__(parent, dashboard)
        if dashboard is not None and self.experiment_manager is not None and self.experiment_manager.entry_applied:
            self.do_things_after_experiment_set(self.experiment_manager.entry)
    @classmethod
    def get_local_folder(cls, user=False) -> Path:
        """ Create a local User or system wide folder to store things about this extension"""
        return Calibration.get_local_folder(user)

    @classmethod
    def get_calibration_folder(cls, user=False) -> Path:
        return Calibration.get_calibration_folder(user)

    @classmethod
    def get_calibration_filepath(cls) -> Path:
        return Calibration.get_calibration_filepath()

    def do_things_after_ui_setup(self):
        super().do_things_after_ui_setup()
        self.show_widgets(False)

    def show_widgets(self, show=True):
        for widget in (self.ui.dock_command, self.ui.get_toolbar('scan_manager')):
            widget.setVisible(show)

    def do_things_after_experiment_set(self, experiment_name: str):
        super().do_things_after_experiment_set(experiment_name)

        if not ('Shaper' in self.modules_manager.actuators_name and
                'Camera' in self.modules_manager.detectors_name):
            messagebox(title='Control Modules',
                       text='To perform Calibration, you should have an actuator '
                            'named Shaper and a camera named Camera in the DashBoard')
            return

        if hasattr(self, 'scan_manager'):  #could happen because base class calls do_things_after_experiment_set before
            # scan_manager is set
            self.scan_manager.entry = 'holography_calibration'
            self.scan_manager.execute_entry()

            QtWidgets.QApplication.processEvents()

            self.connect_start_stop_step()

    def connect_start_stop_step(self):
        self.connect_action('start_val', self.scanner.scanner.settings.child('start').setValue,
                            signal_name='valueChanged')
        self.connect_action('start_val', lambda: self.scanner.settings.child('calculate_positions').setValue(True),
                            signal_name='valueChanged')
        self.connect_action('stop_val', self.scanner.scanner.settings.child('stop').setValue,
                            signal_name='valueChanged')
        self.connect_action('stop_val', lambda: self.scanner.settings.child('calculate_positions').setValue(True),
                            signal_name='valueChanged')
        self.connect_action('step_val', self.scanner.scanner.settings.child('step').setValue,
                            signal_name='valueChanged')
        self.connect_action('step_val', lambda: self.scanner.settings.child('calculate_positions').setValue(True),
                            signal_name='valueChanged')

    def setup_docks_and_widgets(self):
        super().setup_docks_and_widgets()

        self.phase_viewer = Viewer1D(title='Phase')
        self.phase_viewer.parent.setVisible(False)

    def setup_actions(self):
        super().setup_actions()
        self.toolbar.addSeparator()
        self.add_widget('start_val', QtWidgets.QSpinBox(minimum=0, maximum=255, value=0),
                        tip='Start value of the calibration')
        self.add_widget('stop_val', QtWidgets.QSpinBox(minimum=0, maximum=255, value=255),
                        tip='Stop value of the calibration')
        self.add_widget('step_val', QtWidgets.QSpinBox(minimum=0, maximum=255, value=1),
                        tip='Step value of the calibration')
        self.toolbar.addSeparator()
        self.add_action('show_options', 'Show Scanner Options', 'build_circle', tip='Show options', checkable=True)
        self.toolbar.addSeparator()
        self.add_action('show_calibration', 'Show Calibration', 'visibility',
                        tip='Show/Hide the Calibration Viewer', checkable=True,
                        icon_color=self.get_theme().green,
                        icon_checked='visibility_off',
                        icon_checked_color=self.get_theme().red)

    def connect_things(self):
        super().connect_things()
        self.connect_action('show_options', self.show_widgets)
        self.connect_action('show_calibration', self.show_calibration)
        self.scan_done_signal.connect(self.save_calibration)

    def save_calibration(self):
        with DataLoader(self.h5saver) as loader:
            try:
                dwa_calibration = loader.load_data_from_name_origin(
                    name='Phase', origin='Scanner')

                #rename origin
                dwa_calibration.origin = 'Calibration'
                # unwrap between 0 and 2pi
                dwa_calibration[0] = np.abs(np.unwrap(dwa_calibration[0] -dwa_calibration[0][0]))
                # remove nav indexes
                dwa_calibration.nav_indexes = ()  # empty tuple

                for ind in range(5, 11, 2):
                    if check_monotonic(dwa_calibration[0]):
                        break
                    else:
                        logger.warning('Your calibration is not monotonically increasing.\n'
                                       'smoothing it to attempt to get it monotonical')
                        dwa_calibration[0] = savgol_filter(dwa_calibration[0], window_length=ind, polyorder=3)
                if not check_monotonic(dwa_calibration[0]):
                    messagebox(title='',
                               text='Your calibration is not monotonically increasing.\n'
                                    'Cannot save it')
                    do_save = False
                else:
                    do_save = True
                if self.get_calibration_filepath().is_file():
                    do_save = dialog(title='Calibration File Overwrite',
                                 message='Calibration file exists, do you want '
                                         'to overwrite it?')
                    if do_save:
                        self.get_calibration_filepath().unlink(missing_ok=True)
                if do_save:
                    with DataSaverLoader(self.get_calibration_filepath(),
                                         new_file=True) as saver:
                        saver.add_data(where=saver.raw_group, data=dwa_calibration)
            except NameError:
                pass
        self.show_calibration(show=True, calibration_dwa=dwa_calibration)

    @classmethod
    def get_calibration_dwa(cls) -> DataWithAxes:
        return Calibration.get_calibration_dwa()

    @staticmethod
    def show_calibration(show=True, calibration_dwa: DataWithAxes = None):
        calibration = Calibration()
        calibration.show_calibration(show=show, calibration=calibration_dwa)


def main():
    from pymodaq_gui.qt_utils import mkQApp
    from pymodaq.dashboard import load_dashboard_with_arguments
    from pymodaq.utils.gui_utils.loader_utils import create_extension

    qapp = mkQApp('SLMCalibration')

    win, dashboard, _ = load_dashboard_with_arguments(show_dashboard=False, load_extension=False)
    win.mainwindow.setVisible(False)

    win_ext, scan = create_extension(dashboard, BeamShapingCalibration, show_extension=True)

    sys.exit(qapp.exec())


if __name__ == "__main__":
    main()