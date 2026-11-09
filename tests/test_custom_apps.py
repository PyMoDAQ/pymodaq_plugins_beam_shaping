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


def test_algo_app_continuous_saving(qtbot, dockarea, tmp_path):
    """ The modulator phase and the metrics of each output, enlarged along the steps (the format the playground
    script reuses)"""
    from pymodaq_data.h5modules.data_saving import DataLoader
    from pymodaq_plugins_beam_shaping.algorithms.algorithm_app import AlgoApp
    from pymodaq_plugins_beam_shaping.utilities import headless_algorithms as pg

    shaper = pg.make_shaper(width=64, height=64, pixel_size=8.)
    headless = pg.HeadlessApp(shaper)
    algo = pg.create_algorithm(pg.reload_algorithm('Gerchberg-Saxton'), headless)
    pg.set_fields(algo, pg.load_field('GaussianIntensity', None, headless),
                  pg.load_field('LaguerreGaussian', None, headless))

    app = AlgoApp(dockarea)
    app.h5_manager.get_h5saver().init_file(addhoc_file_path=tmp_path / 'continuous.h5')  # the file of the app
    app.do_save_continuous(True)
    flushed = []
    app.h5saver.flush = lambda: flushed.append(True)  # the file is flushed at each step, to browse it while paused
    for _ in range(2):
        pg.run_algorithm(algo)
        n_flushes = len(flushed)
        app.save_continuous(algo.get_fields_to_plot())
        assert len(flushed) > n_flushes
    del app.h5saver.flush
    assert app.run_saver.file_path == tmp_path / 'continuous.h5'
    app._finalize_saving()  # as when the algorithm is paused: the attributes of the arrays are up to date
    from test_algorithm_playground import check_enlarged_nodes
    check_enlarged_nodes(tmp_path / 'continuous.h5', 2)
    app.close_file()

    with DataLoader(tmp_path / 'continuous.h5') as loader:
        assert loader.get_node('/RawData/Shaping000').attrs['title'] == 'BeamShaping'
    from test_algorithm_playground import load_saved
    saved = load_saved(tmp_path / 'continuous.h5')
    assert set(saved) == {'modulator/phase', 'AlgoData/metrics'}
    assert all(dwa.shape[0] == 2 for dwa in saved.values())


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
    # in the units of the axes (m), displayed with SI prefix and rounded to the micron
    assert [group[name] for name in ('x', 'y', 'width', 'height')] == pytest.approx(geometry(phase), abs=0.5e-6)
    assert all(round(group[name], 6) == group[name] for name in ('x', 'y', 'width', 'height'))
    assert all(group.child(name).opts['suffix'] == 'm' and group.child(name).opts['siPrefix']
               for name in ('x', 'y', 'width', 'height'))

    # resized in the amplitude viewer
    amp.ROIselect.set_width(4.)
    assert phase.ROIselect.width() == pytest.approx(4.)

    # the settings drive both, and who listens to the viewers (the extension) is told
    infos = []
    app.amp_viewer.roi_select_signal.connect(infos.append)
    group.child('x').setValue(150e-6)
    assert infos
    assert amp.ROIselect.center()[0] == pytest.approx(150e-6) and phase.ROIselect.center()[0] == pytest.approx(150e-6)

    # hidden from the phase button: hidden in both, and placed again nowhere when shown again
    before = geometry(amp)
    phase.get_action('ROIselect').trigger()
    assert not amp.is_action_checked('ROIselect') and not amp.ROIselect.isVisible()
    phase.get_action('ROIselect').trigger()
    assert amp.ROIselect.isVisible() and geometry(phase) == pytest.approx(before) == geometry(amp)


@pytest.mark.parametrize('modulator_type, expected', [('phase', {'modulator/phase'}),
                                                      ('amplitude', {'slm/amplitude'}),
                                                      ('both', {'slm/amplitude', 'modulator/phase'})])
def test_algo_app_saves_what_is_sent_to_the_shaper(qtbot, dockarea, tmp_path, modulator_type, expected):
    """ The modulator phase for a phase modulator, the amplitude (binary holograms) for an amplitude one"""
    from pymodaq_data.h5modules.data_saving import DataLoader
    from pymodaq_plugins_beam_shaping.algorithms.algorithm_app import AlgoApp
    from pymodaq_plugins_beam_shaping.utilities import headless_algorithms as pg

    headless = pg.HeadlessApp(pg.make_shaper(width=64, height=64, pixel_size=8., modulator_type=modulator_type))
    algo = pg.create_algorithm(pg.reload_algorithm('Gerchberg-Saxton'), headless)
    pg.set_fields(algo, pg.load_field('GaussianIntensity', None, headless),
                  pg.load_field('LaguerreGaussian', None, headless))
    pg.run_algorithm(algo)

    app = AlgoApp(dockarea, shaper=headless.shaper)
    app.h5_manager.get_h5saver().init_file(addhoc_file_path=tmp_path / 'sent.h5')
    app.do_save_continuous(True)
    app.save_continuous(algo.get_fields_to_plot())
    app.close_file()
    from test_algorithm_playground import load_saved
    saved = set(load_saved(tmp_path / 'sent.h5'))
    assert saved == expected | {'AlgoData/metrics'}


@pytest.mark.parametrize('modulator_type, algo_name', [('phase', 'Gerchberg-Saxton'),
                                                       ('amplitude', 'Parallel Lee'),
                                                       ('both', 'Gerchberg-Saxton')])
def test_algo_app_emits_the_slm_field(qtbot, dockarea, modulator_type, algo_name):
    """ What the extension sends to the modulator is a full field: the amplitude is 1 for a phase-only modulator,
    the phase is 0 for an amplitude-only one, and the amplitude is a 0 / 1 pattern for a binary hologram, never the
    input beam"""
    import numpy as np
    from pymodaq_plugins_beam_shaping.algorithms.algorithm_app import AlgoApp
    from pymodaq_plugins_beam_shaping.utilities import headless_algorithms as pg

    headless = pg.HeadlessApp(pg.make_shaper(width=64, height=64, pixel_size=8., modulator_type=modulator_type))
    algo = pg.create_algorithm(pg.reload_algorithm(algo_name), headless)
    pg.set_fields(algo, pg.load_field('GaussianIntensity', None, headless),
                  pg.load_field('LaguerreGaussian', None, headless))
    pg.run_algorithm(algo)

    app = AlgoApp(dockarea, shaper=headless.shaper)
    app._input_field = algo._input_field
    emitted = []
    app.slm_field_signal.connect(emitted.append)
    app.process_output(algo.get_fields_to_plot())

    assert len(emitted) == 1
    field = emitted[0]
    assert field.amplitude.shape == field.phase.shape == algo.shape
    if modulator_type == 'phase':
        assert np.all(field.amplitude == 1)
        assert np.allclose(field.phase, algo.slm_field.phase)
    elif modulator_type == 'amplitude':
        assert np.all(field.phase == 0)
        assert set(np.unique(field.amplitude)) <= {0., 1.}
        assert not np.allclose(field.amplitude, algo._input_field.amplitude)
    else:
        assert np.all(field.amplitude == 1)  # a phase algorithm: nothing to shape in amplitude
        assert np.allclose(field.phase, algo.slm_field.phase)


def test_algo_app_saves_the_pattern_of_an_amplitude_modulator_in_the_slm_node(qtbot, dockarea, tmp_path):
    """ The file of the extension (loaded again by it) holds the 0 / 1 pattern as the 'slm' amplitude, next to the
    modulator one that contains the beam"""
    import numpy as np
    from pymodaq_data.h5modules.data_saving import DataLoader
    from pymodaq_plugins_beam_shaping.algorithms.algorithm_app import AlgoApp
    from pymodaq_plugins_beam_shaping.utilities import headless_algorithms as pg

    headless = pg.HeadlessApp(pg.make_shaper(width=64, height=64, pixel_size=8., modulator_type='amplitude'))
    algo = pg.create_algorithm(pg.reload_algorithm('Parallel Lee'), headless)
    pg.set_fields(algo, pg.load_field('GaussianIntensity', None, headless),
                  pg.load_field('LaguerreGaussian', None, headless))
    pg.run_algorithm(algo)

    app = AlgoApp(dockarea, shaper=headless.shaper)
    app._algorithm = algo
    app.save(tmp_path / 'file.h5')
    with DataLoader(tmp_path / 'file.h5') as loader:
        origins = {}
        for node in loader.walk_nodes('/RawData/Shaping/Final/Data2D/'):
            if 'ARRAY' in node.attrs['CLASS']:
                origins[(node.attrs.get('origin', ''), node.title)] = loader.load_data(node.path)[0]
    with DataLoader(tmp_path / 'file.h5') as loader:  # the layout of the Save: Shaping, not indexed, with its sub groups
        assert 'Shaping' in loader.h5saver.get_children(loader.h5saver.get_node('/RawData'))
        assert 'Final' in loader.h5saver.get_children(loader.h5saver.get_node('/RawData/Shaping'))
        assert loader.get_node('/RawData/Shaping').attrs['settings']
    assert set(np.unique(origins[('slm', 'amplitude')])) <= {0., 1.}
    assert not np.allclose(origins[('modulator', 'amplitude')], origins[('slm', 'amplitude')])
    assert np.allclose(origins[('modulator', 'amplitude')], algo._input_field.amplitude * origins[('slm', 'amplitude')])
