"""Smoke test of the script used to try the algorithms outside of the application"""
import sys

import numpy as np
import pytest

matplotlib = pytest.importorskip('matplotlib')
matplotlib.use('Agg')

from pymodaq_plugins_beam_shaping.algorithms.utils import ApplyMaskTo  # noqa: E402
from pymodaq_plugins_beam_shaping.utilities import headless_algorithms as pg  # noqa: E402


def prepare(algorithm: str, algo_params=None, **shaper_params):
    pg.ensure_qapp()
    shaper = pg.make_shaper(width=128, height=128, pixel_size=8., **shaper_params)
    app = pg.HeadlessApp(shaper)
    algo = pg.create_algorithm(pg.reload_algorithm(algorithm), app, algo_params)
    pg.set_fields(algo, pg.load_field('ImageFiles', {'phase.load': False}, app),
                  pg.load_field('LaguerreGaussian', None, app))
    return app, algo


def test_run_and_plot_an_algorithm(qapp):
    app, algo = prepare('Gerchberg-Saxton')
    pg.run_algorithm(algo)
    assert tuple(algo.output_field.shape) == tuple(algo.shape)
    assert np.all(np.isfinite(algo.output_field.amplitude))
    assert pg.plot(algo, show=False) is not None


def test_plot_input_and_target_fields(qapp):
    app, algo = prepare('Gerchberg-Saxton')
    target = pg.get_target_field(algo)
    assert pg.plot_field(algo._input_field, 'input', show=False) is not None
    assert pg.plot_field(target, 'target', show=False) is not None


def test_plot_intermediate_field_in_log_scale_and_customized(qapp):
    app, algo = prepare('Parallel Lee', modulator_type='amplitude')
    pg.set_mask(app, ApplyMaskTo.INTERMEDIATE, ((-100., 100.), (-100., 100.)))
    pg.run_algorithm(algo)
    log = pg.log_intensity(algo.intermediate_field, decades=4)
    assert log.data[0].max() - log.data[0].min() <= 4 + 1e-9
    figure = pg.plot_field(algo.intermediate_field, 'intermediate', log=True, clim=(-3, 0), xlim=(-50, 50),
                           ylim=(-20, 30), show=False)
    image_axes = pg._image_axes(figure)
    assert len(image_axes) == 2
    assert all(ax.get_aspect() == 1. for ax in image_axes)
    assert image_axes[0].collections[0].get_clim() == (-3, 0)
    assert np.allclose(image_axes[0].get_xlim(), (-50, 50))  # the axes are in um
    assert np.allclose(image_axes[1].get_ylim(), (-20, 30))


def test_snap_shows_the_intermediate_plane_without_mask_and_keeps_the_masks(qapp):
    app, algo = prepare('Parallel Lee', modulator_type='amplitude')
    mask = ((-100., 100.), (-100., 100.))
    pg.set_mask(app, ApplyMaskTo.INTERMEDIATE, mask)
    snapped = pg.snap(algo)
    assert app.apply_mask(ApplyMaskTo.INTERMEDIATE)  # restored for the next runs
    pg.run_algorithm(algo)
    masked = algo.intermediate_field
    assert np.count_nonzero(snapped.amplitude) > np.count_nonzero(masked.amplitude)
    figure = pg.plot_field(snapped, 'snap', log=True, mask=(mask, 'elliptical'), show=False)
    axes = pg._image_axes(figure)
    assert all(len(ax.patches) == 1 for ax in axes)
    # the axes are centered, as the masks: the outline is around the origin
    assert axes[0].patches[0].center == pytest.approx((0., 0.))
    x = axes[0].collections[0].get_coordinates()[0, :, 0]
    assert x[0] < 0 < x[-1]


def test_plots_are_updated_not_created_again(qapp):
    from matplotlib import pyplot as plt
    app, algo = prepare('Parallel Lee', modulator_type='amplitude')
    snapped = pg.snap(algo)
    figure = pg.plot_field(snapped, 'snap', log=True, show=False)
    n_figures = len(plt.get_fignums())
    for size in (100., 200.):
        updated = pg.plot_field(snapped, 'snap', log=True, mask=(((-size, size), (-size, size)), 'square'),
                                figure=figure, show=False)
        assert updated is figure
        assert len(plt.get_fignums()) == n_figures
        assert [text.get_text() for text in figure.texts] == ['snap']  # the title is replaced, not duplicated
        assert all(len(ax.patches) == 1 for ax in pg._image_axes(figure))  # the previous outline is gone
        assert pg._image_axes(figure)[0].patches[0].get_width() == pytest.approx(2 * size)

    dispatcher = pg.plot_field(snapped, 'snap', log=True, backend='qt')
    for size in (100., 200.):
        updated = pg.plot_field(snapped, 'snap', log=True, mask=(((-size, size), (-size, size)), 'elliptical'),
                                backend='qt', figure=dispatcher)
        assert updated is dispatcher
        assert len(dispatcher.mask_rois) == 2  # one per viewer, the previous ones removed
        roi = dispatcher.mask_rois[0][1]
        assert roi.size()[0] == pytest.approx(2 * size)
        assert not roi.translatable and roi.getHandles() == []  # an outline, it cannot be moved nor resized


def test_default_masks_cover_two_thirds_of_the_effective_area_around_the_center(qapp):
    from pymodaq_plugins_beam_shaping.utilities import regions
    app, algo = prepare('Parallel Lee', modulator_type='amplitude')
    for apply_to, pixel_sizes in ((ApplyMaskTo.INTERMEDIATE, algo.intermediate_pixel_sizes),
                                  (ApplyMaskTo.TARGET, algo._target_field.pixels_sizes)):
        region = pg.default_mask(algo, apply_to)
        _, size = regions.get_effective_area(algo.shaper, pixel_sizes)
        for (start, stop), full in zip(region, size):
            assert start == pytest.approx(-stop, abs=1)
            assert stop - start == pytest.approx(full * 2 / 3, abs=2)
    pg.set_mask(app, ApplyMaskTo.INTERMEDIATE, pg.default_mask(algo, ApplyMaskTo.INTERMEDIATE))
    pg.run_algorithm(algo)
    assert np.all(np.isfinite(algo.output_field.amplitude))


def test_overview_is_made_of_subplots_and_updated(qapp):
    from matplotlib import pyplot as plt
    app, algo = prepare('Parallel Lee', modulator_type='amplitude')
    pg.set_mask(app, ApplyMaskTo.INTERMEDIATE, pg.default_mask(algo, ApplyMaskTo.INTERMEDIATE))
    pg.run_algorithm(algo)
    figure = pg.plot(algo, show=False)
    assert len(figure.axes) == 8  # output, modulator, intermediate (amplitude | phase) and the metrics + an empty one
    titles = [ax.get_title() for ax in figure.axes]
    assert 'Output Plane: Amplitude' in titles and 'Intermediate Plane: log10(Intensity)' in titles
    assert 'Metrics' in titles
    n_figures = len(plt.get_fignums())
    assert pg.plot(algo, figure=figure, show=False) is figure
    assert len(plt.get_fignums()) == n_figures and len(figure.axes) == 8


def test_overview_in_the_qt_backend_has_a_dock_per_field(qapp):
    app, algo = prepare('Parallel Lee', modulator_type='amplitude')
    pg.set_mask(app, ApplyMaskTo.INTERMEDIATE, pg.default_mask(algo, ApplyMaskTo.INTERMEDIATE))
    pg.run_algorithm(algo)
    overview = pg.plot(algo, backend='qt')
    assert list(overview.docks) == ['Metrics', 'Modulator Plane', 'Output Plane', 'Intermediate Plane']
    for title in ('Modulator Plane', 'Output Plane', 'Intermediate Plane'):
        assert len(overview.dispatchers[title].viewers) == 2  # amplitude and phase
    assert pg.plot(algo, backend='qt', figure=overview) is overview

    app, algo = prepare('Gerchberg-Saxton')
    pg.run_algorithm(algo)
    assert 'Intermediate Plane' not in pg.plot(algo, backend='qt').docks


def test_snap_without_intermediate_plane(qapp):
    app, algo = prepare('Gerchberg-Saxton')
    assert pg.snap(algo) is None


def test_plot_with_the_qt_viewers(qapp):
    app, algo = prepare('Gerchberg-Saxton')
    pg.run_algorithm(algo)
    dispatcher = pg.plot_field(algo.output_field, 'output', clim=(0., 0.5), xlim=(-50, 50), ylim=(-20, 30),
                               backend='qt')
    amplitude_view = dispatcher.viewers[0].view
    assert amplitude_view.histogrammer.get_histogram('red').getLevels() == pytest.approx((0., 0.5))
    x_range, y_range = amplitude_view.get_view_range()
    # the aspect ratio is locked, so one of the ranges is enlarged around the requested one
    assert x_range[0] <= -50 + 1e-6 and x_range[1] >= 50 - 1e-6  # in um
    assert y_range[0] <= -20 + 1e-6 and y_range[1] >= 30 - 1e-6
    assert min(x_range[1] - x_range[0] - 100, y_range[1] - y_range[0] - 50) == pytest.approx(0., abs=1e-6)


@pytest.mark.parametrize('phase, params', [('FlatPhase', {'phase_value': 0.5}), ('RandomPhase', None),
                                           ('QuadraticPhase', {'quadratic.auto': False, 'shift.auto': False})])
def test_initial_phase_from_the_factory(qapp, phase, params):
    app, algo = prepare('Gerchberg-Saxton')
    ini = pg.initial_phase(algo, phase, params)
    assert ini.shape == tuple(algo.shape)
    if phase == 'FlatPhase':
        assert np.allclose(ini, np.pi / 2)
    pg.run_algorithm(algo, 2, phase, params)
    assert np.all(np.isfinite(algo.output_field.amplitude))


def test_unknown_initial_phase_parameter_lists_the_possible_ones(qapp):
    app, algo = prepare('Gerchberg-Saxton')
    with pytest.raises(KeyError, match='phase_value'):
        pg.initial_phase(algo, 'FlatPhase', {'wrong': 1.})


def test_parameters_are_set_without_widgets_and_masks_applied(qapp):
    app, algo = prepare('Parallel Lee', dict(carrier_factor=0.5), modulator_type='amplitude')
    pg.set_mask(app, ApplyMaskTo.INTERMEDIATE, ((-100., 100.), (-100., 100.)))
    pg.run_algorithm(algo)
    assert algo.settings['carrier_factor'] == 0.5
    assert algo.apply_mask(ApplyMaskTo.INTERMEDIATE)


def test_unknown_parameter_lists_the_possible_ones(qapp):
    with pytest.raises(KeyError, match='possible ones'):
        prepare('Projections', dict(nope=1))


def test_reload_algorithm_takes_the_changes_into_account(qapp, tmp_path, monkeypatch):
    code = """
from pymodaq_plugins_beam_shaping.algorithms.algorithms.direct import Direct
from pymodaq_plugins_beam_shaping.algorithms.factory import AlgorithmFactory


@AlgorithmFactory.register_algorithm()
class TmpReload(Direct):
    ALGO_NAME = 'TmpReload'
    VERSION = {version}
"""
    module_file = tmp_path / 'tmp_reload_algo.py'
    module_file.write_text(code.format(version=1))
    monkeypatch.syspath_prepend(str(tmp_path))
    import importlib
    module = importlib.import_module('tmp_reload_algo')
    try:
        assert pg.AlgorithmFactory.get_algorithm('TmpReload').VERSION == 1
        module_file.write_text(code.format(version=22))
        reloaded = pg.reload_algorithm('TmpReload')
        assert reloaded.VERSION == 22  # other length, the bytecode cache compares sizes and times
        assert pg.AlgorithmFactory.get_algorithm('TmpReload') is reloaded

        module_file.write_text('raise RuntimeError("broken")')
        with pytest.raises(RuntimeError):
            pg.reload_algorithm('TmpReload')
        assert pg.AlgorithmFactory.get_algorithm('TmpReload') is reloaded  # still usable
    finally:
        pg.AlgorithmFactory.algorithms_registry.pop('TmpReload', None)
        sys.modules.pop('tmp_reload_algo', None)



def load_saved(path, group='/RawData/Shaping000'):
    from pymodaq_data.h5modules.data_saving import DataLoader
    with DataLoader(path) as loader:
        return {dwa.get_full_name(): dwa for dwa in loader.load_all(group)}


def test_no_saving_by_default(qapp):
    app, algo = prepare('Gerchberg-Saxton')
    pg.run_algorithm(algo, 2)
    assert not hasattr(algo, 'saved_h5file')


@pytest.mark.parametrize('fields, metrics, expected', [
    (True, False, {'output/amplitude', 'output/phase', 'modulator/amplitude', 'modulator/phase'}),
    (False, True, {'AlgoData/metrics'}),
    (True, True, {'output/amplitude', 'output/phase', 'modulator/amplitude', 'modulator/phase', 'AlgoData/metrics'}),
    (('modulator/phase',), True, {'modulator/phase', 'AlgoData/metrics'}),
])
def test_fields_and_metrics_saved_at_each_iteration(qapp, tmp_path, fields, metrics, expected):
    app, algo = prepare('Gerchberg-Saxton')
    path = tmp_path / 'run.h5'
    pg.run_algorithm(algo, 3, save_fields=fields, save_metrics=metrics, h5file=path)
    assert algo.saved_h5file == path
    saved = load_saved(path)
    assert set(saved) == expected
    for dwa in saved.values():
        assert dwa.shape[0] == 3  # enlarged along the 'step' axis, one step per iteration
    if 'modulator/phase' in saved:
        assert np.allclose(saved['modulator/phase'][0][-1], algo.modulator_field.phase)


def test_intermediate_field_saved(qapp, tmp_path):
    app, algo = prepare('Parallel Lee', modulator_type='amplitude')
    pg.run_algorithm(algo, save_fields=True, h5file=tmp_path / 'run.h5')
    assert 'intermediate/intensity' in load_saved(tmp_path / 'run.h5')


def test_runs_added_to_the_same_file(qapp, tmp_path):
    app, algo = prepare('Gerchberg-Saxton')
    path = tmp_path / 'runs.h5'
    pg.run_algorithm(algo, 1, save_metrics=True, h5file=path)
    pg.run_algorithm(algo, 2, save_metrics=True, h5file=path)
    assert load_saved(path, '/RawData/Shaping000')['AlgoData/metrics'].shape[0] == 1
    assert load_saved(path, '/RawData/Shaping001')['AlgoData/metrics'].shape[0] == 2
