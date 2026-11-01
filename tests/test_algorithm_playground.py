"""Smoke test of the script used to try the algorithms outside of the application"""
import numpy as np
import pytest

matplotlib = pytest.importorskip('matplotlib')
matplotlib.use('Agg')

from pymodaq_plugins_beam_shaping.scripts import algorithm_playground as playground  # noqa: E402


@pytest.fixture
def small_shaper(qapp, monkeypatch):
    monkeypatch.setattr(playground, 'SHAPER_PARAMS', dict(width=128, height=128, pixel_size=8.))
    monkeypatch.setattr(playground, 'SHOW_PLOTS', False)


def test_run_and_plot_an_algorithm(small_shaper):
    algo = playground.run('Gerchberg-Saxton')
    assert tuple(algo.output_field.shape) == tuple(algo.shape)
    assert np.all(np.isfinite(algo.output_field.amplitude))
    assert playground.plot(algo) is not None


def test_parameters_are_set_without_widgets(small_shaper, monkeypatch):
    monkeypatch.setattr(playground, 'SHAPER_PARAMS', dict(width=128, height=128, pixel_size=8., modulator_type='amplitude'))
    monkeypatch.setattr(playground, 'ALGORITHM_PARAMS', dict(carrier_factor=0.5))
    monkeypatch.setattr(playground, 'APPLY_INTERMEDIATE_MASK', True)
    monkeypatch.setattr(playground, 'INTERMEDIATE_MASK', ((-100., 100.), (-100., 100.)))
    algo = playground.run('DMD Lee')
    assert algo.settings['carrier_factor'] == 0.5
    assert algo.apply_mask('intermediate_mask')


def test_unknown_parameter_lists_the_possible_ones(small_shaper, monkeypatch):
    monkeypatch.setattr(playground, 'ALGORITHM_PARAMS', dict(nope=1))
    with pytest.raises(KeyError, match='possible ones'):
        playground.run('Projections')
