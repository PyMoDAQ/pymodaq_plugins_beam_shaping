"""The outline of the region the target cannot be obtained in, drawn on the 2D viewers of the target and the output"""
import numpy as np
import pytest
import pyqtgraph as pg
from qtpy import QtWidgets

from pymodaq_data import DataToExport
from pymodaq_data.data import DataRaw
from pymodaq_gui.plotting.data_viewers.viewer import ViewerDispatcher
from pymodaq_gui.utils.dock import DockArea

from pymodaq_plugins_beam_shaping.field import Field
from pymodaq_plugins_beam_shaping.utilities.region_outline import RegionOutline


@pytest.fixture
def dispatcher(qtbot):
    window = QtWidgets.QMainWindow()
    area = DockArea()
    window.setCentralWidget(area)
    qtbot.addWidget(window)
    window.show()
    dispatcher = ViewerDispatcher(area, title='Output')
    field = Field('output', amplitude=np.ones((32, 48)), phase=np.zeros((32, 48)))
    dispatcher.show_data(DataToExport('Output', data=[field.amplitude_as_dwa(), field.phase_as_dwa()]))
    yield dispatcher
    window.close()


def outlines(dispatcher):
    """The isocurve items that are children of the image items of the viewers"""
    found = []
    for viewer in dispatcher.viewers:
        image = viewer.view.data_displayer.get_image('red')
        found.append([child for child in image.childItems() if isinstance(child, pg.IsocurveItem)])
    return found


def disk(shape=(32, 48), radius=10):
    y, x = np.indices(shape)
    return (y - shape[0] / 2) ** 2 + (x - shape[1] / 2) ** 2 > radius ** 2  # outside: not reachable


def test_the_outline_is_drawn_on_every_2d_viewer_with_the_mask(dispatcher):
    outline = RegionOutline()
    mask = disk()
    outline.show(dispatcher, mask)
    items = outlines(dispatcher)
    assert len(items) == 2 and all(len(viewer_items) == 1 for viewer_items in items)  # amplitude and phase views
    for viewer_items in items:
        assert viewer_items[0].isVisible()
        assert viewer_items[0].level == 0.5
        assert np.array_equal(viewer_items[0].data, mask.astype(float))


def test_a_new_mask_replaces_the_previous_outline(dispatcher):
    outline = RegionOutline()
    outline.show(dispatcher, disk(radius=10))
    outline.show(dispatcher, disk(radius=5))
    for viewer_items in outlines(dispatcher):
        assert len(viewer_items) == 1  # not one more each time
        assert np.array_equal(viewer_items[0].data, disk(radius=5).astype(float))


@pytest.mark.parametrize('mask', [None, np.zeros((32, 48), dtype=bool)])
def test_no_outline_without_unreachable_region(dispatcher, mask):
    outline = RegionOutline()
    outline.show(dispatcher, disk())
    outline.show(dispatcher, mask)
    for viewer_items in outlines(dispatcher):
        assert all(not item.isVisible() for item in viewer_items)


def test_the_outline_follows_the_image_item_when_the_viewer_rebuilds_it(dispatcher):
    outline = RegionOutline()
    outline.show(dispatcher, disk())
    field = Field('output', amplitude=np.ones((32, 48)), phase=np.zeros((32, 48)))
    dispatcher.show_data(DataToExport('Output', data=[field.intensity_as_dwa(), field.amplitude_as_dwa(),
                                                      field.phase_as_dwa()]))  # another number of images
    outline.show(dispatcher, disk())
    for viewer_items in outlines(dispatcher):
        assert len(viewer_items) == 1 and viewer_items[0].isVisible()


def test_the_extension_outlines_the_unreachable_region_on_the_target_and_the_output(qtbot):
    """ The data of the algorithm go to the viewers: the region the target cannot be obtained in is an outline on the
    target and the output views, not one more image"""
    import functools
    import types
    from pymodaq_plugins_beam_shaping.extensions.spatial_beam_shaping import BeamShaping
    from pymodaq_plugins_beam_shaping.utilities import headless_algorithms as pg_algo

    headless = pg_algo.HeadlessApp(pg_algo.make_shaper(width=64, height=64, pixel_size=8., modulator_type='amplitude'))
    algo = pg_algo.create_algorithm(pg_algo.reload_algorithm('Parallel Lee'), headless)
    pg_algo.set_fields(algo, pg_algo.load_field('GaussianIntensity', None, headless),
                       pg_algo.load_field('LaguerreGaussian', None, headless))
    ny, nx = algo.shape
    y, x = np.indices((ny, nx))
    algo._input_field.amplitude = np.exp(-(((y - ny / 2) / (ny / 4)) ** 2 + ((x - nx / 2) / (nx / 4)) ** 2))
    pg_algo.run_algorithm(algo, verbose=False)
    assert algo.unreachable_mask is not None and algo.unreachable_mask.any()

    window = QtWidgets.QMainWindow()
    area = DockArea()
    window.setCentralWidget(area)
    qtbot.addWidget(window)
    window.show()
    extension = types.SimpleNamespace(
        target_viewers=ViewerDispatcher(area, title='Target'), output_viewers=ViewerDispatcher(area, title='Output'),
        modulator_viewers=ViewerDispatcher(area, title='Modulator'), other_viewers=ViewerDispatcher(area, title='Other'),
        metrics_viewer=ViewerDispatcher(area, title='Metrics'), intermediate_viewer=types.SimpleNamespace(
            show_data=lambda dwa: None),
        is_action_checked=lambda name: True, region_outline=RegionOutline(), _unreachable=None,
        _target_field_loader=types.SimpleNamespace(set_region=lambda region: None),
        _input_field_loader=types.SimpleNamespace(set_region=lambda region: None))
    BeamShaping.plot_target(extension, algo._target_field)
    BeamShaping.plot_fields(extension, algo.get_fields_to_plot())

    for dispatcher in (extension.target_viewers, extension.modulator_viewers, extension.output_viewers):
        for viewer_items in outlines(dispatcher):
            assert len(viewer_items) == 1 and viewer_items[0].isVisible()
            assert np.array_equal(viewer_items[0].data, algo.unreachable_mask.astype(float))
    assert len(extension.other_viewers.viewers) == 1  # the pattern sent (slm), the mask is only the outline


def test_the_target_keeps_its_outline_when_it_is_plotted_after_the_fields(qtbot):
    """ The target is plotted when it changes, which can be after the fields of a run: the outline must stay"""
    import types
    from pymodaq_plugins_beam_shaping.extensions.spatial_beam_shaping import BeamShaping

    window = QtWidgets.QMainWindow()
    area = DockArea()
    window.setCentralWidget(area)
    qtbot.addWidget(window)
    window.show()
    mask = disk()
    extension = types.SimpleNamespace(target_viewers=ViewerDispatcher(area, title='Target'),
                                      region_outline=RegionOutline(), _unreachable=None)
    field = Field('target', amplitude=np.ones((32, 48)), phase=np.zeros((32, 48)))
    BeamShaping.plot_target(extension, field)
    extension._unreachable = mask  # what plot_fields keeps
    extension.region_outline.show(extension.target_viewers, mask)
    BeamShaping.plot_target(extension, field)  # the target is plotted again, with new image items
    for viewer_items in outlines(extension.target_viewers):
        assert len(viewer_items) == 1 and viewer_items[0].isVisible()


def test_plot_fields_without_intermediate_nor_unreachable_data(qtbot):
    """ An algorithm without filter in the intermediate plane nor unreachable region gives no such data: nothing to plot"""
    import types
    from pymodaq_plugins_beam_shaping.extensions.spatial_beam_shaping import BeamShaping
    from pymodaq_plugins_beam_shaping.utilities import headless_algorithms as pg_algo

    headless = pg_algo.HeadlessApp(pg_algo.make_shaper(width=64, height=64, pixel_size=8.))
    algo = pg_algo.create_algorithm(pg_algo.reload_algorithm('Direct'), headless)
    pg_algo.set_fields(algo, pg_algo.load_field('GaussianIntensity', None, headless),
                       pg_algo.load_field('LaguerreGaussian', None, headless))
    pg_algo.run_algorithm(algo, verbose=False)
    dte = algo.get_fields_to_plot()
    dte.append(DataRaw('other', data=[np.zeros(4)]))  # what remains once the fields are taken, as for iterative algos
    names = [dwa.origin + '/' + dwa.name for dwa in dte]
    assert 'intermediate/intensity' not in names and 'unreachable/amplitude' not in names

    window = QtWidgets.QMainWindow()
    area = DockArea()
    window.setCentralWidget(area)
    qtbot.addWidget(window)
    window.show()
    shown = []
    extension = types.SimpleNamespace(
        target_viewers=ViewerDispatcher(area, title='Target'), output_viewers=ViewerDispatcher(area, title='Output'),
        modulator_viewers=ViewerDispatcher(area, title='Modulator'), other_viewers=ViewerDispatcher(area, title='Other'),
        metrics_viewer=ViewerDispatcher(area, title='Metrics'),
        intermediate_viewer=types.SimpleNamespace(show_data=shown.append),
        is_action_checked=lambda name: True, region_outline=RegionOutline(), _unreachable=None,
        _target_field_loader=types.SimpleNamespace(set_region=lambda region: None),
        _input_field_loader=types.SimpleNamespace(set_region=lambda region: None))
    BeamShaping.plot_fields(extension, dte)
    assert shown == [] and extension._unreachable is None


def _loader_outlines(app):
    found = []
    for viewer in (app.amp_viewer, app.phase_viewer):
        image = viewer.view.data_displayer.get_image('red')
        found.append([child for child in image.childItems() if isinstance(child, pg.IsocurveItem)])
    return found


def test_the_field_loader_outlines_a_region_on_its_amplitude_and_phase_viewers(qtbot):
    from pymodaq_plugins_beam_shaping.field.field_loader_app import FieldLoaderApp

    area = DockArea()
    qtbot.addWidget(area)
    area.show()
    app = FieldLoaderApp(area, title='loader')
    app.settings.child('loader').setValue('GaussianIntensity')
    app.load_field()
    mask = disk(app.field.amplitude.shape)
    app.set_region(mask)
    for viewer_items in _loader_outlines(app):
        assert len(viewer_items) == 1 and viewer_items[0].isVisible()
        assert np.array_equal(viewer_items[0].data, mask.astype(float))

    app.load_field()  # the field is shown again: the region stays
    for viewer_items in _loader_outlines(app):
        assert len(viewer_items) == 1 and viewer_items[0].isVisible()

    app.set_region(None)
    for viewer_items in _loader_outlines(app):
        assert all(not item.isVisible() for item in viewer_items)


def test_the_extension_sends_the_region_to_the_field_loaders(qtbot):
    import types
    from pymodaq_plugins_beam_shaping.extensions.spatial_beam_shaping import BeamShaping

    regions = []
    loader = types.SimpleNamespace(set_region=regions.append)
    mask = disk()
    BeamShaping.show_region(types.SimpleNamespace(
        target_viewers=types.SimpleNamespace(viewers=[]), modulator_viewers=types.SimpleNamespace(viewers=[]),
        output_viewers=types.SimpleNamespace(viewers=[]), region_outline=RegionOutline(),
        _target_field_loader=loader, _input_field_loader=loader), mask)
    assert len(regions) == 2 and all(region is mask for region in regions)
