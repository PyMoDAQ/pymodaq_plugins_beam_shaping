"""The SLM calibration is a DAQScan whose scan configuration comes from a Scan Manager entry"""
import numpy as np
import pytest

from pymodaq_data import DataRaw, DataToExport


def test_calibration_scanner_phase_from_fringes(qtbot):
    from types import SimpleNamespace
    from pymodaq.utils.scanner.scanner import Scanner
    import pymodaq_plugins_beam_shaping.scanners.calibration  # registers the scanner  # noqa: F401

    shaper = SimpleNamespace(title='Shaper', units='')
    scanner = Scanner(actuators=[shaper], selected_actuators=[shaper])
    scanner.settings.child('scan_type').setValue('Scan1D')
    scanner.settings.child('scan_sub_type').setValue('BeamShapingCalibration')
    calibration = scanner.scanner
    assert calibration.n_steps == 256

    data = calibration.data_actuator_at(100)  # grey level on the right half of the SLM
    assert data.as_grey_levels
    assert set(np.unique(data[0])) == {0, 100}

    x = np.arange(1024)
    phases = []
    for grey in range(0, 256, 32):
        fringes = 100 + 50 * np.cos(2 * np.pi * x / 16 + grey / 255 * 3 * np.pi)
        dwa = DataRaw('Camera', data=[np.tile(fringes, (50, 1))])
        phase = calibration.process_data(DataToExport('Camera', data=[dwa])).get_data_from_name('Phase')
        phases.append(phase[0][0])
    assert np.unwrap(np.array(phases) - phases[0])[-1] == pytest.approx(224 / 255 * 3 * np.pi, rel=1e-2)


def test_calibration_extension_uses_scan_manager_entry(qtbot, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # the DAQScan creates its h5 file with a relative path on Linux
    from pymodaq_gui.qt_utils import mkQApp
    from pymodaq.utils.gui_utils.loader_utils import create_extension
    from pymodaq_plugins_beam_shaping.scripts.make_calibration_entry import create_dashboard_with_camera_and_shaper
    from pymodaq_plugins_beam_shaping.utilities.calibrating import BeamShapingCalibration, CALIBRATION_ENTRY

    assert CALIBRATION_ENTRY.is_file()
    dashboard = create_dashboard_with_camera_and_shaper(mkQApp('tests'))
    win, calibration = create_extension(dashboard, BeamShapingCalibration)
    calibration.do_things_after_experiment_set('test')

    assert calibration.scan_manager.settings is not None
    assert calibration.scanner.settings['scan_type'] == 'Scan1D'
    assert calibration.scanner.settings['scan_sub_type'] == 'BeamShapingCalibration'
    assert calibration.modules_manager.selected_actuators_name == ['Shaper']
    assert calibration.modules_manager.selected_detectors_name == ['Camera']
