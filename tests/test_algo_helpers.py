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
                  pg.load_field('ImageFiles', {'phase/load': False}, app))
    return app, algo


def test_4f_helpers_conserve_energy_and_calibrate_the_output(qapp):
    app, algo = prepare('Binary Threshold', 'amplitude')
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
    app, algo = prepare('Binary Threshold', 'amplitude')
    pg.set_mask(app, ApplyMaskTo.INTERMEDIATE, ((-60., 60.), (-60., 60.)))
    algo.set_amplitude_in_modulator_plane(np.random.default_rng(0).uniform(size=algo.shape))
    filtered = algo.compute_intermediate_field()
    unfiltered = algo.compute_intermediate_field(use_mask=False)
    assert filtered.intensity.sum() < unfiltered.intensity.sum()


def test_efficiency_is_the_output_power_over_the_incident_power_filter_included(qapp):
    # a phase modulator in a 2f setup loses nothing
    app, algo = prepare('Gerchberg-Saxton', 'phase')
    pg.run_algorithm(algo, 2, verbose=False)
    assert algo.efficiency == pytest.approx(1.)
    assert algo.input_power == pytest.approx(algo._input_field.intensity.sum())

    # a binary hologram: the mirrors that are off and the filter of the intermediate plane lose power. The input beam
    # is in the modulator field, so the incident power is the one of the input field
    app, algo = prepare('Parallel Lee', 'amplitude')
    pg.run_algorithm(algo, verbose=False)
    power = algo._input_field.intensity.sum()
    assert algo.input_power == pytest.approx(power)
    unfiltered = algo.efficiency
    assert unfiltered == pytest.approx(algo.output_field.intensity.sum() / power)
    assert unfiltered == pytest.approx(algo.modulator_field.intensity.sum() / power)  # nothing filtered yet
    pg.set_mask(app, ApplyMaskTo.INTERMEDIATE, pg.default_mask(algo, ApplyMaskTo.INTERMEDIATE))
    pg.run_algorithm(algo, verbose=False)
    assert algo.efficiency < unfiltered
    assert algo.efficiency == pytest.approx(algo.output_field.intensity.sum() / power)


def test_the_amplitude_pattern_sent_to_the_slm_is_binary_and_the_modulator_field_has_the_beam(qapp):
    app, algo = prepare('Parallel Lee', 'amplitude')
    pg.run_algorithm(algo, verbose=False)
    pattern = algo.slm_amplitude
    assert set(np.unique(pattern)) <= {0., 1.}
    assert np.allclose(algo.modulator_field.amplitude, algo._input_field.amplitude * pattern)


def test_the_input_beam_is_compensated_for_the_amplitude_modulators(qapp):
    """The output of a binary hologram is the target and not the target times the beam profile (compensation on)"""
    app, algo = prepare('Parallel Lee', 'amplitude')
    ny, nx = algo.shape
    y, x = np.indices((ny, nx))
    algo._input_field.amplitude = np.exp(-(((y - ny / 2) / (ny / 3)) ** 2 + ((x - nx / 2) / (nx / 3)) ** 2))  # not flat
    sizes = pg.regions.pixel_sizes_in_um(algo.intermediate_pixel_sizes)
    half = np.hypot(*algo.order_frequency()) / 3
    pg.set_mask(app, ApplyMaskTo.INTERMEDIATE,  # around the filtered order, in um from the center
                tuple(slice((freq - half) * size, (freq + half) * size)
                      for freq, size in zip(algo.order_frequency(), sizes)))
    pg.set_parameters(algo, {'binarize': False, 'compensate_input': False})
    pg.run_algorithm(algo, verbose=False)
    raw = algo.output_field.amplitude.copy()
    pg.set_parameters(algo, {'compensate_input': True})
    pg.run_algorithm(algo, verbose=False)
    compensated = algo.output_field.amplitude
    target = algo._target_field.amplitude

    def correlation(output):
        inside = target > 0.2 * target.max()
        return np.corrcoef(output[inside], target[inside])[0, 1]
    assert correlation(compensated) > correlation(raw)
    assert algo.unreachable_mask is not None
    # the pixels below the minimum input level are off, those of the mask of unreachable pixels
    level = algo.settings['min_input_level'] * algo._input_field.amplitude.max()
    assert np.array_equal(algo.unreachable_mask, algo._input_field.amplitude < level)
    pg.set_parameters(algo, {'binarize': True})  # a mirror cannot be grey: the unreachable ones are off
    pg.run_algorithm(algo, verbose=False)
    assert np.all(algo.slm_amplitude[algo.unreachable_mask] == 0)


def test_compensation_can_be_switched_off(qapp):
    app, algo = prepare('Parallel Lee', 'amplitude')
    pg.set_parameters(algo, {'compensate_input': False})
    pg.run_algorithm(algo, verbose=False)
    assert algo.unreachable_mask is None
    assert algo.unreachable_fraction == 0.


def test_back_propagate_amplitude_sets_a_phase_of_the_modulator(qapp):
    app, algo = prepare('Gerchberg-Saxton', 'phase')
    pg.run_algorithm(algo, 1)
    before = algo.modulator_field.phase.copy()
    algo.back_propagate_amplitude(np.ones(algo.shape))
    assert algo.modulator_field.phase.shape == before.shape
    assert not np.allclose(algo.modulator_field.phase, before)


def test_the_centered_grid_is_centered(qapp):
    app, algo = prepare('Gerchberg-Saxton', 'phase')
    xx, yy = algo.compute_grid()
    assert xx.shape == algo.shape and np.isclose(xx.mean(), 0) and np.isclose(yy.mean(), 0)
