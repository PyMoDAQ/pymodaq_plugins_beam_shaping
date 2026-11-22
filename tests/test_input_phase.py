"""The phase of the input beam (issue #98): the modulator field is the input field times the SLM field, so its phase
is the input phase plus the SLM phase; the SLM field (what is sent) never holds the input phase. The algorithms see the
true input field, and those that control the output phase (ALGOTYPE not AMPLITUDE) can compensate the input phase in
the target phase (checkbox Compensate input phase, on by default)."""
import numpy as np
import pytest
from qtpy import QtWidgets

from pymodaq_gui.utils.dock import DockArea

from pymodaq_plugins_beam_shaping.field import Field
from pymodaq_plugins_beam_shaping.utilities import headless_algorithms as pg


def prepare(name, modulator_type):
    pg.ensure_qapp()
    app = pg.HeadlessApp(pg.make_shaper(width=128, height=128, pixel_size=8., modulator_type=modulator_type))
    algo = pg.create_algorithm(pg.reload_algorithm(name), app)
    pg.set_fields(algo, pg.load_field('GaussianIntensity', None, app),
                  pg.load_field('ImageFiles', {'phase/load': False}, app))
    return app, algo


def curved_phase(shape, strength=30.):
    """ A defocus like phase, large enough to blur the output if it is ignored"""
    y, x = np.indices(shape)
    return strength * (((x - shape[1] / 2) / shape[1]) ** 2 + ((y - shape[0] / 2) / shape[0]) ** 2)


QUANTUM = 2 * np.pi / 2 ** 8  # the SLM phase is quantised on 8 bits by default


def tilted_phase(shape):
    y, x = np.indices(shape)
    return 2 * np.pi * (3 * x / shape[1] + 2 * y / shape[0])


def same_phase(a, b, where=None, atol=1e-8) -> bool:
    """ Equal modulo 2 pi (where the amplitude is not null if given)"""
    diff = np.exp(1j * a) - np.exp(1j * b)
    if where is not None:
        diff = diff[where]
    return np.allclose(diff, 0., atol=atol)


def physical_output(algo) -> np.ndarray:
    """ The output computed from the input field and the SLM field only (2f: one Fourier transform, as the algorithm)"""
    modulator = Field(amplitude=algo._input_field.amplitude * algo.slm_field.amplitude,
                      phase=algo._input_field.phase + algo.slm_field.phase,
                      pixel_sizes=algo._input_field.pixels_sizes)
    return (modulator.fft2(norm='forward') * np.prod(modulator.shape)).field


def test_the_modulator_phase_is_the_input_phase_plus_the_slm_phase(qapp):
    app, algo = prepare('Gerchberg-Saxton', 'phase')
    algo._input_field.phase = curved_phase(algo.shape)
    slm = tilted_phase(algo.shape) % (2 * np.pi) - np.pi
    algo.set_phase_in_modulator_plane(slm)
    assert same_phase(algo.slm_field.phase, slm)  # the SLM field never holds the input phase
    assert same_phase(algo.modulator_field.phase, algo._input_field.phase + slm)
    assert np.allclose(algo.modulator_field.amplitude, algo._input_field.amplitude)


def test_gerchberg_saxton_with_a_curved_input_corrects_it_on_the_slm(qapp):
    app, algo = prepare('Gerchberg-Saxton', 'phase')
    pg.run_algorithm(algo, 10)
    flat_nrmse = algo.nrmse

    app, algo = prepare('Gerchberg-Saxton', 'phase')
    algo._input_field.phase = curved_phase(algo.shape)
    pg.run_algorithm(algo, 10)
    algo.compute_forward_fft(update_plots=False)  # the output of the last SLM phase
    # the output is the one of the true modulator field: input field times what is sent to the SLM
    assert np.allclose(physical_output(algo), algo.output_field.field, atol=1e-6 * np.abs(algo.output_field.field).max())
    assert same_phase(algo.modulator_field.phase, algo._input_field.phase + algo.slm_field.phase)
    # and the algorithm corrected the input phase: as good as with a flat input
    assert algo.nrmse <= 1.2 * flat_nrmse + 1e-3


def test_the_initial_phase_goes_on_top_of_the_input_phase(qapp):
    app, algo = prepare('Gerchberg-Saxton', 'phase')
    algo._input_field.phase = curved_phase(algo.shape)
    ini = tilted_phase(algo.shape) % (2 * np.pi) - np.pi
    algo.define_input_phase(ini)
    assert same_phase(algo.slm_field.phase, ini)
    assert same_phase(algo.modulator_field.phase, algo._input_field.phase + ini)


def test_a_binary_hologram_keeps_the_input_phase_in_the_modulator_field(qapp):
    app, algo = prepare('Parallel Lee', 'amplitude')
    algo._input_field.phase = curved_phase(algo.shape)
    pg.run_algorithm(algo)
    assert same_phase(algo.modulator_field.phase, algo._input_field.phase)  # the SLM phase of a DMD is null
    assert np.allclose(algo.slm_field.phase, 0.)


def test_the_compensation_of_the_input_phase_is_offered_to_the_algorithms_shaping_the_output_phase(qapp):
    for name, modulator, expected in (('Parallel Lee', 'amplitude', True), ('Superpixel', 'amplitude', True),
                                      ('Binary Threshold', 'amplitude', True), ('Direct', 'both', True),
                                      ('OL2014 - Amplitude-Phase Checkerboard', 'phase', True),
                                      ('Gerchberg-Saxton', 'phase', False)):
        app, algo = prepare(name, modulator)
        assert algo.can_compensate_input_phase is expected, name
        assert algo.compensate_input_phase is expected, name  # on by default where it is offered
        pg.set_compensate_input_phase(app, False)
        assert algo.compensate_input_phase is False


@pytest.mark.parametrize('name, modulator', [('Parallel Lee', 'amplitude'), ('Superpixel', 'amplitude'),
                                             ('Binary Threshold', 'amplitude'),
                                             ('OL2014 - Amplitude-Phase Checkerboard', 'phase')])
def test_compensating_the_input_phase_encodes_the_target_phase_minus_the_input_phase(qapp, name, modulator):
    app, algo = prepare(name, modulator)
    target_phase = tilted_phase(algo.shape) * 0.3
    input_phase = curved_phase(algo.shape)
    algo._target_field.phase = target_phase.copy()
    algo._input_field.phase = input_phase.copy()
    pg.run_algorithm(algo)  # on by default
    compensated = algo.slm_field.deepcopy()

    app, algo = prepare(name, modulator)
    pg.set_compensate_input_phase(app, False)
    algo._target_field.phase = target_phase - input_phase  # what the compensation asks for, with a flat input
    pg.run_algorithm(algo)
    assert np.allclose(compensated.amplitude, algo.slm_field.amplitude)
    assert same_phase(compensated.phase, algo.slm_field.phase)


def test_direct_with_the_compensation_gives_the_target_phase_in_the_modulator_plane(qapp):
    app, algo = prepare('Direct', 'both')
    input_field = algo._input_field.deepcopy()
    input_field.phase = curved_phase(algo.shape)
    target = Field(amplitude=input_field.amplitude.copy(), phase=tilted_phase(algo.shape) * 0.3,
                   pixel_sizes=input_field.pixels_sizes)  # Direct sends the target as is: same shape as the modulator
    pg.set_fields(algo, input_field, target)
    pg.run_algorithm(algo)
    where = algo.modulator_field.amplitude > 1e-6 * algo.modulator_field.amplitude.max()
    assert same_phase(algo.modulator_field.phase, algo._target_field.phase, where, QUANTUM)
    assert same_phase(algo.slm_field.phase, algo._target_field.phase - algo._input_field.phase, where, QUANTUM)

    pg.set_compensate_input_phase(app, False)
    pg.run_algorithm(algo)
    assert same_phase(algo.slm_field.phase, algo._target_field.phase, where, QUANTUM)
    assert same_phase(algo.modulator_field.phase, algo._target_field.phase + algo._input_field.phase, where, QUANTUM)


@pytest.fixture
def dockarea(qtbot):
    window = QtWidgets.QMainWindow()
    area = DockArea()
    window.setCentralWidget(area)
    qtbot.addWidget(window)
    window.show()
    yield area


def test_the_algo_app_shows_the_checkbox_for_the_algorithms_that_can_use_it(qtbot, dockarea, config):
    from pymodaq_plugins_beam_shaping.algorithms.algorithm_app import AlgoApp

    app = AlgoApp(dockarea)
    group = app.settings.child('compensation_group')
    checkbox = group.child('compensate_input_phase')
    for name, shown in (('Parallel Lee', True), ('Direct', True), ('Gerchberg-Saxton', False)):
        app.set_algorithm(name)
        assert checkbox.opts['visible'] is shown, name
        assert group.opts['visible'] is (shown or app.algorithm.INPUT_COMPENSATION is not None), name
    app.set_algorithm('Direct')  # no amplitude compensation: only the checkbox in the group
    assert not group.child('compensation_factory').opts['visible']
    assert app.compensate_input_phase is True
    checkbox.setValue(False)
    assert app.algorithm.compensate_input_phase is False
