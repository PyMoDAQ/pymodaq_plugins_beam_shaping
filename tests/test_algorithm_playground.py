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
    app, algo = prepare('DMD Lee', modulator_type='amplitude')
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
    assert np.allclose(image_axes[0].get_xlim(), (-50e-6, 50e-6))  # the axes are in m
    assert np.allclose(image_axes[1].get_ylim(), (-20e-6, 30e-6))


def test_plot_with_the_qt_viewers(qapp):
    app, algo = prepare('Gerchberg-Saxton')
    pg.run_algorithm(algo)
    assert pg.plot_field(algo.output_field, 'output', backend='qt') is not None
    assert pg.plot(algo, backend='qt') is not None


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
    app, algo = prepare('DMD Lee', dict(carrier_factor=0.5), modulator_type='amplitude')
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
