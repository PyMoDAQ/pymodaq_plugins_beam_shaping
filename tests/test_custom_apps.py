"""Create and use the CustomApp / CustomExt of the package, as the Dashboard does, to catch the incompatibilities with
the PyMoDAQ release (base classes, viewers, ROI API)"""
import types

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

    extension._target_field_loader.load_field()
    # the target ROI starts on the default region: 2/3 of the effective area, in the units of the axes (m)
    from pymodaq_plugins_beam_shaping.utilities import regions, sizing
    roi = extension._target_field_loader.amp_viewer.view.ROIselect
    pixel_sizes = extension._algorithm.get_plane_pixel_sizes('target_mask')
    pos, size = regions.get_effective_area(extension.shaper, pixel_sizes)  # um, (y, x)
    assert roi.size()[0] * 1e6 == pytest.approx(2 / 3 * size[1], rel=1e-3)
    assert roi.size()[1] * 1e6 == pytest.approx(2 / 3 * size[0], rel=1e-3)
    assert roi.pos()[0] * 1e6 == pytest.approx(pos[1] + size[1] / 6, rel=1e-3)

    assert extension.quit_fun()


def test_extension_updates_the_fields_from_the_shaper(qtbot):
    from pymodaq.dashboard import create_load_dashboard
    from pymodaq.utils.gui_utils.loader_utils import create_extension
    from pymodaq_plugins_beam_shaping.extensions.spatial_beam_shaping import BeamShaping
    from pymodaq_plugins_beam_shaping.utilities.shaper import (ModulatorType, shaper_params,
                                                               fill_shaper_settings)
    from pymodaq_gui.parameter import Parameter
    from pymodaq_plugins_beam_shaping.utilities import sizing

    _, dashboard = create_load_dashboard()
    win_ext, extension = create_extension(dashboard, BeamShaping)
    try:
        before = extension.input_field.shape

        # a Shaper actuator that tells what the shaper is, as the extension reads it once initialized
        actuator = types.SimpleNamespace(_hw_settings_name='actuator_settings', settings=Parameter.create(
            name='settings', type='group', children=[
                {'name': 'actuator_settings', 'type': 'group', 'children': shaper_params()}]))
        fill_shaper_settings(actuator.settings.child('actuator_settings'), 'Other', 512, 256, 12.,
                             modulator_type=ModulatorType.PHASE)
        extension._shaper_actuator = actuator
        extension.update_from_shaper()

        assert extension.shaper.name == 'Other'
        assert sizing.get_slm_size(extension.shaper) == (256, 512)
        # every part of the extension follows the same shaper
        assert extension._algorithm.shaper == extension.shaper == extension._corrections.shaper
        assert extension._input_field_loader.shaper == extension._target_field_loader.shaper == extension.shaper
        assert extension.slm_shape == (256 // 2, 512 // 2)  # binned
        assert extension.input_field.shape != before
        assert extension.input_field.shape == sizing.get_effective_needed_field_size(extension.shaper)
    finally:
        extension.quit_fun()


def test_roi_select_is_the_same_in_both_viewers(qtbot, dockarea):
    from pymodaq_plugins_beam_shaping.field.field_loader_app import FieldLoaderApp

    app = FieldLoaderApp(dockarea)
    amp, phase = (viewer.view for viewer in (app.amp_viewer, app.phase_viewer))
    group = app.settings.child('utils', 'roi_select')

    amp.get_action('ROIselect').trigger()  # as the button does: shown, placed by the viewer the first time
    assert phase.is_action_checked('ROIselect') and phase.ROIselect.isVisible()
    assert group['show'] and group['width'] > 0

    def geometry(view):
        return [view.ROIselect.center()[0], view.ROIselect.center()[1], view.ROIselect.width(), view.ROIselect.height()]

    assert geometry(amp) == pytest.approx(geometry(phase))

    # moved in the phase viewer: follows in the amplitude viewer and in the settings
    phase.ROIselect.setPos((phase.ROIselect.pos()[0] + 3., phase.ROIselect.pos()[1] + 2.))
    assert geometry(amp) == pytest.approx(geometry(phase))
    assert [group[name] for name in ('x', 'y', 'width', 'height')] == pytest.approx(geometry(phase))

    # resized in the amplitude viewer
    amp.ROIselect.set_width(4.)
    assert phase.ROIselect.width() == pytest.approx(4.)

    # the settings drive both, and who listens to the viewers (the extension) is told
    infos = []
    app.amp_viewer.roi_select_signal.connect(infos.append)
    group.child('x').setValue(1.5)
    assert infos
    assert amp.ROIselect.center()[0] == pytest.approx(1.5) and phase.ROIselect.center()[0] == pytest.approx(1.5)

    # hidden from the phase button: hidden in both, and placed again nowhere when shown again
    before = geometry(amp)
    phase.get_action('ROIselect').trigger()
    assert not amp.is_action_checked('ROIselect') and not amp.ROIselect.isVisible()
    phase.get_action('ROIselect').trigger()
    assert amp.ROIselect.isVisible() and geometry(phase) == pytest.approx(before) == geometry(amp)
