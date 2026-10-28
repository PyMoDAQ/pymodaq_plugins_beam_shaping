"""Generate the Scan Manager entry used by the SLM calibration (resources/holography_calibration.scan)

The entry selects the detector named Camera, the actuator named Shaper and the BeamShapingCalibration scanner. Only the
names matter: mock modules are loaded in a Dashboard to create the entry with the Scan Manager itself, so it stays
valid whatever the real camera and SLM are. Run it again if the format of the entries changes with PyMoDAQ.
"""
import sys
import time
from pathlib import Path

from pymodaq.control_modules.enums import DAQTypesEnum
from pymodaq.utils.managers.modules import ModuleType
from pymodaq.utils.managers.modules.loader import PluginInfo

from pymodaq_plugins_beam_shaping.utilities.calibrating import CALIBRATION_ENTRY


def create_dashboard_with_camera_and_shaper(qapp, timeout=20.):
    """ Create a Dashboard with a detector named Camera and an actuator named Shaper (mock ones)"""
    from pymodaq.dashboard import create_load_dashboard

    _, dashboard = create_load_dashboard()
    dashboard.module_creator.load_created_modules([
        [PluginInfo(id=1, name='Shaper', class_name='MockShaper', type=ModuleType.Actuator, do_init=False)],
        [PluginInfo(id=2, name='Camera', class_name='MockShaperCamera', type=ModuleType.Detector, do_init=False,
                    daq_type=DAQTypesEnum.DAQ2D)]])
    start = time.time()
    while time.time() - start < timeout and len(dashboard.modules_manager.modules_all) < 2:
        qapp.processEvents()
    return dashboard


def main(entry_path: Path = CALIBRATION_ENTRY):
    from pymodaq_gui.qt_utils import mkQApp
    from pymodaq.extensions import DAQScan
    from pymodaq.utils.gui_utils.loader_utils import create_extension

    qapp = mkQApp('CalibrationEntry')
    dashboard = create_dashboard_with_camera_and_shaper(qapp)
    _, daq_scan = create_extension(dashboard, DAQScan)

    scan_manager = daq_scan.scan_manager
    modules = scan_manager.modules_manager
    for name, selected in (('detectors', ['Camera']), ('actuators', ['Shaper'])):
        modules.settings[name] = dict(all_items=modules.settings[name]['all_items'], selected=selected)
    scan_manager.scanner.settings.child('scan_type').setValue('Scan1D')
    scan_manager.scanner.settings.child('scan_sub_type').setValue('BeamShapingCalibration')

    entry_path.unlink(missing_ok=True)
    scan_manager.save_entries(entry_path)
    print(f'Entry saved in {entry_path}')


if __name__ == '__main__':
    main()
    sys.exit(0)
