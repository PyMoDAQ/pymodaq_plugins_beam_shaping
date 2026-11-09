"""Helpers of AlgoBase shared by the algorithms (4f propagation, projection step...)"""
import numpy as np
import pytest
from pymodaq_plugins_beam_shaping.algorithms.compensation import Compensations

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


def from_center(algo, slices):
    """ A region given in um around the center of the intermediate plane, in the frame of the extension (the origin is
    the corner of the field)"""
    pixel_sizes = pg.regions.pixel_sizes_in_um(algo.intermediate_pixel_sizes)
    return tuple(slice(_slice.start + n * size / 2, _slice.stop + n * size / 2)
                 for _slice, n, size in zip(slices, algo.shape, pixel_sizes))


def test_intermediate_mask_filters_the_intermediate_field(qapp):
    app, algo = prepare('Binary Threshold', 'amplitude')
    pg.set_mask(app, ApplyMaskTo.INTERMEDIATE, from_center(algo, (slice(-60., 60.), slice(-60., 60.))))
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
    pattern = algo.slm_field.amplitude
    assert algo.slm_amplitude is pattern or np.array_equal(algo.slm_amplitude, pattern)
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
                from_center(algo, tuple(slice((freq - half) * size, (freq + half) * size)
                                        for freq, size in zip(algo.order_frequency(), sizes))))
    pg.set_parameters(algo, {'binarize': False})
    pg.set_compensation(app, 'NoCompensation')
    pg.run_algorithm(algo, verbose=False)
    raw = algo.output_field.amplitude.copy()
    pg.set_compensation(app, 'DivideByInput')
    pg.run_algorithm(algo, verbose=False)
    compensated = algo.output_field.amplitude
    target = algo._target_field.amplitude

    def correlation(output):
        inside = target > 0.2 * target.max()
        return np.corrcoef(output[inside], target[inside])[0, 1]
    assert correlation(compensated) > correlation(raw)
    assert algo.unreachable_mask is not None
    # the pixels below the minimum input level are off, those of the mask of unreachable pixels
    level = app.compensation.settings['min_input_level'] * algo._input_field.amplitude.max()
    assert np.array_equal(algo.unreachable_mask, algo._input_field.amplitude < level)
    pg.set_parameters(algo, {'binarize': True})  # a mirror cannot be grey: the unreachable ones are off
    pg.run_algorithm(algo, verbose=False)
    assert np.all(algo.slm_amplitude[algo.unreachable_mask] == 0)


def test_compensation_can_be_switched_off(qapp):
    app, algo = prepare('Parallel Lee', 'amplitude')
    pg.set_compensation(app, 'NoCompensation')
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


def test_the_slm_field_holds_the_phase_without_correction_and_the_pattern(qapp):
    app, algo = prepare('Gerchberg-Saxton', 'both')
    pg.run_algorithm(algo, 1, verbose=False)
    slm = algo.slm_field
    assert np.allclose(slm.phase, algo.modulator_field.phase)  # the phase sent, nothing added to it
    assert np.all(slm.amplitude == 1)  # a phase algorithm does not shape the amplitude
    assert 'slm/amplitude' in [dwa.get_full_name() for dwa in algo.get_fields_to_plot()]
    app, algo = prepare('Gerchberg-Saxton', 'phase')
    pg.run_algorithm(algo, 1, verbose=False)
    assert 'slm/amplitude' not in [dwa.get_full_name() for dwa in algo.get_fields_to_plot()]


def test_the_default_compensation_keeps_the_dynamic_range_of_the_pattern_modest(qapp):
    """ With the default settings, a flat target through a Gaussian beam does not need a transmission at the border
    of the beam more than a few times the one of the centre: the centre would otherwise be left with almost nothing
    to the binary pattern (what a full area target showed on the app)"""
    app, algo = prepare('Parallel Lee', 'amplitude')
    ny, nx = algo.shape
    y, x = np.indices((ny, nx))
    algo._input_field.amplitude = np.exp(-(((y - ny / 2) / (ny / 3)) ** 2 + ((x - nx / 2) / (nx / 3)) ** 2))
    algo._target_field.amplitude = np.ones(algo.shape)
    encoded = algo.encoded_amplitude()
    assert encoded.max() == pytest.approx(1.)
    assert encoded[ny // 2, nx // 2] >= 1 / 5.5


def test_a_target_not_on_the_shape_of_the_input_is_not_compensated_and_says_so(qapp, caplog):
    """ The target and the input share their shape by construction (the field loaders): if not, say it"""
    app, algo = prepare('Parallel Lee', 'amplitude')
    algo._target_field.amplitude = np.ones((algo.shape[0] // 2, algo.shape[1] // 2))
    with caplog.at_level('WARNING'):
        encoded = algo.encoded_amplitude()
    assert encoded.shape == algo._target_field.amplitude.shape and algo.unreachable_mask is None
    assert 'compensat' in caplog.text


def flat_target_through_a_gaussian_beam(algo):
    ny, nx = algo.shape
    y, x = np.indices((ny, nx))
    algo._input_field.amplitude = np.exp(-(((y - ny / 2) / (ny / 3)) ** 2 + ((x - nx / 2) / (nx / 3)) ** 2))
    algo._target_field.amplitude = np.ones(algo.shape)


def test_the_checkerboard_uses_the_compensation_too(qapp):
    """ The phases of the checkerboard give an amplitude cos(beta) multiplied by the beam: the output is the target
    only for a target divided by the beam"""
    app, algo = prepare('OL2014 - Amplitude-Phase Checkerboard', 'phase')
    flat_target_through_a_gaussian_beam(algo)
    inside = algo._input_field.amplitude > 0.5 * algo._input_field.amplitude.max()
    sizes = pg.regions.pixel_sizes_in_um(algo.intermediate_pixel_sizes)
    pg.set_mask(app, ApplyMaskTo.INTERMEDIATE, tuple(slice(-3 * size, 3 * size) for size in sizes))  # around the zero order

    def flatness():
        pg.run_algorithm(algo, verbose=False)
        output = algo.output_field.amplitude[inside]
        return output.std() / output.mean()

    pg.set_compensation(app, 'NoCompensation')
    raw = flatness()
    assert algo.unreachable_mask is None
    pg.set_compensation(app, 'DivideByInput')
    compensated = flatness()
    assert algo.unreachable_mask is not None and algo.unreachable_mask.any()
    assert compensated < raw / 2


def test_the_unreachable_region_is_known_before_any_run(qapp):
    """ What the app shows as soon as the compensation is chosen: the region of the run, without a run"""
    app, algo = prepare('Parallel Lee', 'amplitude')
    flat_target_through_a_gaussian_beam(algo)
    preview = algo.preview_unreachable()
    assert preview is not None and preview.any()
    pg.run_algorithm(algo, verbose=False)
    assert np.array_equal(preview, algo.unreachable_mask)
    pg.set_compensation(app, 'NoCompensation')
    assert algo.preview_unreachable() is None


def test_an_algorithm_without_compensation_has_no_unreachable_region(qapp):
    """ Gerchberg-Saxton propagates the beam: the compensation does not apply to it, whatever the app says"""
    app, algo = prepare('Gerchberg-Saxton', 'phase')
    assert algo.INPUT_COMPENSATION is None  # no default compensation: it does not use one
    assert algo.preview_unreachable() is None


def test_the_superpixel_preview_follows_its_blocks(qapp):
    app, algo = prepare('Superpixel', 'amplitude')
    flat_target_through_a_gaussian_beam(algo)
    n = algo.settings['px']
    preview = algo.preview_unreachable()
    assert np.all(preview[:n, :n] == preview[0, 0])  # one value per superpixel


@pytest.mark.parametrize('name, modulator_type', [('Gerchberg-Saxton', 'phase'), ('Gerchberg-Saxton', 'both'),
                                                  ('Parallel Lee', 'amplitude')])
def test_the_phase_sent_to_the_slm_is_in_the_fields_for_every_modulator_type(qapp, name, modulator_type):
    """ slm/phase is the phase of the SLM field (what is sent, without the corrections), next to slm/amplitude: the
    modulator phase will not be it anymore once the input phase is kept in the modulator field"""
    app, algo = prepare(name, modulator_type)
    pg.run_algorithm(algo, 1, verbose=False)
    dte = algo.get_fields_to_plot()
    phase = dte.get_data_from_full_name('slm/phase')
    assert phase is not None
    assert np.array_equal(phase[0], algo.slm_field.phase)
    if modulator_type == 'amplitude':
        assert np.all(phase[0] == 0)  # an amplitude modulator has no phase
    else:
        assert np.allclose(phase[0], algo.modulator_field.phase)


def test_the_default_compensation_of_the_algorithm_is_used_without_the_app(qapp, monkeypatch):
    """ INPUT_COMPENSATION is the name of the compensation the algorithm starts with (None: it does not use one)"""
    app, algo = prepare('Parallel Lee', 'amplitude')
    app.compensation = None  # the app has not chosen
    assert type(algo.compensation).__name__ == 'DivideByInput'
    monkeypatch.setattr(type(algo), 'INPUT_COMPENSATION', Compensations.NoCompensation)
    assert type(algo.compensation).__name__ == 'NoCompensation'
