"""Smoke test of the script used to try the algorithms outside of the application"""
import numpy as np
import pytest

matplotlib = pytest.importorskip('matplotlib')
matplotlib.use('Agg')

from pymodaq_plugins_beam_shaping.algorithms.utils import ApplyMaskTo  # noqa: E402
from pymodaq_plugins_beam_shaping.utilities import algorithm_playground as pg  # noqa: E402


def prepare(algorithm: str, algo_params=None, **shaper_params):
    pg.ensure_qapp()
    shaper = pg.make_shaper(width=128, height=128, pixel_size=8., **shaper_params)
    app = pg.HeadlessApp(shaper)
    algo = pg.create_algorithm(algorithm, app, algo_params)
    pg.set_fields(algo, pg.load_field('ImageFiles', {'phase.load': False}, app),
                  pg.load_field('LaguerreGaussian', None, app))
    return app, algo


def test_run_and_plot_an_algorithm(qapp):
    app, algo = prepare('Gerchberg-Saxton')
    pg.run_algorithm(algo)
    assert tuple(algo.output_field.shape) == tuple(algo.shape)
    assert np.all(np.isfinite(algo.output_field.amplitude))
    assert pg.plot(algo, show=False) is not None


def test_parameters_are_set_without_widgets_and_masks_applied(qapp):
    app, algo = prepare('DMD Lee', dict(carrier_factor=0.5), modulator_type='amplitude')
    pg.set_mask(app, ApplyMaskTo.INTERMEDIATE, ((-100., 100.), (-100., 100.)))
    pg.run_algorithm(algo)
    assert algo.settings['carrier_factor'] == 0.5
    assert algo.apply_mask(ApplyMaskTo.INTERMEDIATE)


def test_unknown_parameter_lists_the_possible_ones(qapp):
    with pytest.raises(KeyError, match='possible ones'):
        prepare('Projections', dict(nope=1))
