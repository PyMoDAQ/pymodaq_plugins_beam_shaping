"""Helpers of AlgoBase shared by the algorithms (4f propagation, projection step...)"""
import numpy as np
import pytest

from pymodaq_data import Q_
from pymodaq_plugins_beam_shaping.algorithms.utils import ApplyMaskTo
from pymodaq_plugins_beam_shaping.utilities import headless_algorithms as pg
from pymodaq_plugins_beam_shaping.utils import Config

plugin_config = Config()


def prepare(name, modulator_type):
    pg.ensure_qapp()
    app = pg.HeadlessApp(pg.make_shaper(width=128, height=128, pixel_size=8., modulator_type=modulator_type))
    algo = pg.create_algorithm(pg.reload_algorithm(name), app)
    pg.set_fields(algo, pg.load_field('GaussianIntensity', None, app),
                  pg.load_field('ImageFiles', {'phase.load': False}, app))
    return app, algo


def test_4f_helpers_conserve_energy_and_calibrate_the_output(qapp):
    app, algo = prepare('SuperPixels', 'amplitude')
    algo.set_amplitude_in_modulator_plane(np.random.default_rng(0).uniform(size=algo.shape))
    intermediate = algo.compute_intermediate_field()
    assert algo.intermediate_field is intermediate
    output = algo.compute_output_from_intermediate()
    assert algo.output_field is output
    assert np.allclose(output.field, algo.modulator_field.field)  # no mask: identity
    assert np.isclose(intermediate.intensity.sum(), algo.modulator_field.intensity.sum())

    # the pixel size of the target plane is the one of the explicit 4f formula, wavelength times focal over extent
    focals = plugin_config('setup', '4f', 'focals')
    expected = [(Q_(plugin_config('setup', 'wavelength_nm'), 'nm') * Q_(focals[1], 'mm') /
                 (algo.intermediate_pixel_sizes[ind] * algo.shape[ind])).to('um') for ind in range(2)]
    for size, ref in zip(output.pixels_sizes, expected):
        assert np.isclose(size.m_as('um'), ref.m_as('um'))


def test_intermediate_mask_filters_the_intermediate_field(qapp):
    app, algo = prepare('SuperPixels', 'amplitude')
    pg.set_mask(app, ApplyMaskTo.INTERMEDIATE, ((-60., 60.), (-60., 60.)))
    algo.set_amplitude_in_modulator_plane(np.random.default_rng(0).uniform(size=algo.shape))
    filtered = algo.compute_intermediate_field()
    unfiltered = algo.compute_intermediate_field(use_mask=False)
    assert filtered.intensity.sum() < unfiltered.intensity.sum()


def test_back_propagate_amplitude_sets_a_phase_of_the_modulator(qapp):
    app, algo = prepare('Gerchberg-Saxton', 'phase')
    pg.run_algorithm(algo, 1)
    before = algo.modulator_field.phase.copy()
    algo.back_propagate_amplitude(np.ones(algo.shape))
    assert algo.modulator_field.phase.shape == before.shape
    assert not np.allclose(algo.modulator_field.phase, before)


def test_the_centered_grid_is_centered(qapp):
    app, algo = prepare('SuperPixels', 'amplitude')
    xx, yy = algo.compute_grid()
    assert xx.shape == algo.shape and np.isclose(xx.mean(), 0) and np.isclose(yy.mean(), 0)
