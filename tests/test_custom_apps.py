"""Create and use the CustomApp / CustomExt of the package, as the Dashboard does, to catch the incompatibilities with
the PyMoDAQ release (base classes, viewers, ROI API)"""
import pytest
from qtpy import QtWidgets

from pymodaq_gui.utils.dock import DockArea


@pytest.fixture
def dockarea(qtbot):
    window = QtWidgets.QMainWindow()
    area = DockArea()
    window.setCentralWidget(area)
    qtbot.addWidget(window)
    window.show()
    yield area  # the generator keeps the window alive


def test_field_loader_app(qtbot, dockarea):
    from pymodaq_plugins_beam_shaping.field.field_loader_app import FieldLoaderApp

    app = FieldLoaderApp(dockarea, title='loader')
    loaders = [name for name in app.settings.child('loader').opts['limits']
               if name not in ('SavedField', 'Dashboard', 'ImageFiles')]  # these ones ask for a file or a dashboard
    for name in loaders[:3]:
        app.settings.child('loader').setValue(name)
        app.load_field()
        qtbot.wait(10)
        assert app.field.amplitude.shape == (app.settings['needed_size', 'height'],
                                             app.settings['needed_size', 'width'])


def test_field_loader_app_mask(qtbot, dockarea):
    from pymodaq_plugins_beam_shaping.field.field_loader_app import FieldLoaderApp

    app = FieldLoaderApp(dockarea, title='loader')
    app.settings.child('loader').setValue('GaussianIntensity')
    app.load_field()
    show_mask = app.settings.child('utils', 'masking', 'show_mask')

    show_mask.setValue(True)
    assert app.mask is not None
    assert app.get_mask_as_slices() is not None

    show_mask.setValue(False)
    assert app.mask is None


def test_algo_app(qtbot, dockarea):
    from pymodaq_plugins_beam_shaping.algorithms.algorithm_app import AlgoApp

    app = AlgoApp(dockarea)
    assert app.module_and_data_saver is None


def test_correction_app(qtbot, dockarea):
    from pymodaq_plugins_beam_shaping.utilities.corrections import Correction

    Correction(dockarea)


def test_extension_on_empty_dashboard(qtbot):
    from pymodaq.dashboard import create_load_dashboard
    from pymodaq.utils.gui_utils.loader_utils import create_extension
    from pymodaq_plugins_beam_shaping.extensions.spatial_beam_shaping import BeamShaping

    _, dashboard = create_load_dashboard()
    win_ext, extension = create_extension(dashboard, BeamShaping)
    assert extension.quit_fun()
