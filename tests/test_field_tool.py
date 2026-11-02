"""Operations of the Field Tool on synthetic fields with known defects, and the Field Tool window itself"""
import numpy as np
import pytest
from qtpy import QtWidgets

from pymodaq_gui.utils.dock import DockArea

from pymodaq_plugins_beam_shaping.field import Field, Q_
from pymodaq_plugins_beam_shaping.field.operations import compute, OperationFactory

SHAPE = (128, 160)


def gaussian(shape=SHAPE, waist=30.):
    y, x = compute.centered_grid(shape)
    return np.exp(-(x ** 2 + y ** 2) / waist ** 2)


def wrap(phase):
    return np.angle(np.exp(1j * phase))


def rms_on(values, support):
    values = values[support]
    return float(np.sqrt(np.mean((values - values.mean()) ** 2)))


def test_operations_are_registered():
    assert {'Remove linear phase', 'Remove Zernike', 'Unwrap phase', 'Wrap phase', 'Log10 amplitude'} <= set(OperationFactory.operations())


@pytest.mark.parametrize('ky, kx', [(0.3, -0.5), (-0.123, 0.789), (0., 0.25)])
def test_linear_phase_fft(ky, kx):
    amplitude = gaussian()
    field = amplitude * np.exp(1j * compute.linear_phase(SHAPE, ky, kx))
    support = compute.support_mask(amplitude, 0.05)
    found_ky, found_kx = compute.linear_phase_fft(field, support, pad_factor=4)
    assert found_ky == pytest.approx(ky, abs=5e-3)
    assert found_kx == pytest.approx(kx, abs=5e-3)


def test_linear_phase_plane():
    amplitude = gaussian()
    phase = 0.7 + compute.linear_phase(SHAPE, 0.21, -0.34)  # several 2pi over the beam: needs the unwrapping
    support = compute.support_mask(amplitude, 0.05)
    piston, ky, kx = compute.linear_phase_plane(wrap(phase), support, amplitude ** 2)
    assert (ky, kx) == pytest.approx((0.21, -0.34), abs=1e-6)
    assert wrap(np.array(piston - 0.7)) == pytest.approx(0, abs=1e-6)


def test_zernike_fit_and_pupil():
    amplitude = gaussian()
    support = compute.support_mask(amplitude, 0.1)
    center, radius = compute.pupil_from_support(amplitude, support)
    assert center == pytest.approx((0, 0), abs=1e-6)
    assert 0 < radius <= min(SHAPE) / 2
    basis = compute.zernike_basis(SHAPE, center, radius)
    expected = {'piston': 0.4, 'tilt_x': 1.5, 'tilt_y': -0.8, 'defocus': 2.}
    phase = sum(value * basis[mode] for mode, value in expected.items())
    coefficients, _ = compute.fit_zernike(wrap(phase), support, center, radius, amplitude ** 2)
    for mode in ('tilt_x', 'tilt_y', 'defocus'):
        assert coefficients[mode] == pytest.approx(expected[mode], abs=1e-6)
    assert wrap(np.array(coefficients['piston'] - expected['piston'])) == pytest.approx(0, abs=1e-6)


def test_unwrap_on_support():
    amplitude = gaussian()
    support = compute.support_mask(amplitude, 0.05)
    phase = 0.002 * (compute.centered_grid(SHAPE)[1] ** 2)
    unwrapped = compute.unwrap(wrap(phase), support)
    difference = unwrapped[support] - phase[support]
    assert np.ptp(difference) == pytest.approx(0, abs=1e-6)  # equal up to a constant 2kpi
    assert np.array_equal(unwrapped[~support], wrap(phase)[~support])


def test_phase_difference_is_wrapped():
    difference = compute.phase_difference(np.array([3., -3.]), np.array([-3., 3.]))
    assert np.all(np.abs(difference) <= np.pi)
    assert difference == pytest.approx([6 - 2 * np.pi, -6 + 2 * np.pi])


@pytest.fixture
def dockarea(qtbot):
    window = QtWidgets.QMainWindow()
    area = DockArea()
    window.setCentralWidget(area)
    qtbot.addWidget(window)
    window.show()
    yield area


def make_field(phase: np.ndarray) -> Field:
    return Field('output', amplitude=gaussian(), phase=phase, pixel_sizes=(Q_(8., 'um'), Q_(8., 'um')))


def test_field_tool_chain(qtbot, dockarea):
    from pymodaq_plugins_beam_shaping.field.field_tool_app import FieldToolApp

    y, x = compute.centered_grid(SHAPE)
    defocus = 0.004 * (x ** 2 + y ** 2)
    tilted = make_field(wrap(compute.linear_phase(SHAPE, 0.2, -0.3) + defocus))
    tool = FieldToolApp(dockarea, field_sources={'output': lambda: tilted})
    assert tool.settings.child('source').opts['limits'] == ['output', 'file']

    tool.refresh()
    assert tool.field_before is not tilted  # a copy: the tool never changes the field of the algorithm
    assert np.array_equal(tool.field_after.phase, tool.field_before.phase)  # no operation yet

    linear = tool.add_operation('Remove linear phase')
    assert linear.settings['results', 'kx'] == pytest.approx(-0.3, abs=0.02)
    assert linear.settings['results', 'ky'] == pytest.approx(0.2, abs=0.02)
    assert linear.settings['results', 'kx_mm'] == pytest.approx(linear.settings['results', 'kx'] / 8e-3)

    zernike = tool.add_operation('Remove Zernike')
    assert [operation.OPERATION_NAME for operation in tool.chain] == ['Remove linear phase', 'Remove Zernike']
    assert rms_on(compute.unwrap(tool.field_after.phase, tool.support), tool.support) < 0.05
    assert zernike.settings['results', 'defocus'] != 0

    difference = tool.get_difference()
    assert np.all(np.abs(difference[1]) <= np.pi)
    assert np.allclose(difference[0], 0)

    tool.move_operation(zernike.settings.name(), -1)
    assert [operation.OPERATION_NAME for operation in tool.chain] == ['Remove Zernike', 'Remove linear phase']
    tool.move_operation(zernike.settings.name(), -1)  # already the first one
    assert tool.chain[0] is zernike

    zernike.settings.child('enabled').setValue(False)  # recomputed with only the linear phase removed
    assert rms_on(compute.unwrap(tool.field_after.phase, tool.support), tool.support) > 0.1

    tool.remove_operation(linear.settings.name())
    assert tool.chain == [zernike]
    assert np.array_equal(tool.field_after.phase, tool.field_before.phase)


def test_field_tool_follows_source_when_active(qtbot, dockarea):
    from pymodaq_plugins_beam_shaping.field.field_tool_app import FieldToolApp

    fields = {'output': make_field(np.zeros(SHAPE))}
    tool = FieldToolApp(dockarea, field_sources={'output': lambda: fields['output']})
    tool.refresh()
    fields['output'] = make_field(np.ones(SHAPE))
    tool.settings.child('active').setValue(False)
    tool.update_from_source()
    assert np.all(tool.field_before.phase == 0)
    tool.settings.child('active').setValue(True)  # refreshes
    assert np.all(tool.field_before.phase == 1)


def test_field_tool_save_and_load(qtbot, dockarea, tmp_path):
    from pymodaq_plugins_beam_shaping.field.field_tool_app import FieldToolApp, FILE_SOURCE

    tool = FieldToolApp(dockarea, field_sources={'output': lambda: make_field(
        wrap(compute.linear_phase(SHAPE, 0.1, 0.1)))})
    tool.refresh()
    tool.add_operation('Remove linear phase')
    fname = tmp_path / 'field.h5field'
    tool.save_field(fname)

    standalone = FieldToolApp(dockarea)  # on its own: only files
    assert standalone.source == FILE_SOURCE
    standalone.settings.child('file', 'path').setValue(str(fname))
    assert np.allclose(standalone.field_before.phase, tool.field_after.phase)
    assert standalone.field_before.pixels_sizes[0].m_as('um') == pytest.approx(8.)


def test_field_tool_in_extension(qtbot):
    from pymodaq.dashboard import create_load_dashboard
    from pymodaq.utils.gui_utils.loader_utils import create_extension
    from pymodaq_plugins_beam_shaping.extensions.spatial_beam_shaping import BeamShaping

    _, dashboard = create_load_dashboard()
    win_ext, extension = create_extension(dashboard, BeamShaping)
    try:
        tool = extension._field_tool
        assert tool.settings.child('source').opts['limits'] == ['output', 'modulator', 'intermediate', 'target',
                                                                'input', 'file']
        extension.get_action('field_tool').trigger()  # opens the window and reads the field
        assert extension._field_tool_dockarea.isVisible()
        for source in ('input', 'target', 'modulator', 'output'):
            tool.settings.child('source').setValue(source)
            assert tool.field_before is not None
            assert tool.field_before.shape == tool.field_after.shape
        tool.add_operation('Remove Zernike')

        extension._input_field_loader.load_field(notify=True)  # a new input: the tool follows
        tool.settings.child('source').setValue('input')
        assert np.allclose(tool.field_before.amplitude, extension._algorithm.algorithm._input_field.amplitude)
        extension.get_action('field_tool').trigger()
        assert not extension._field_tool_dockarea.isVisible()
    finally:
        extension.quit_fun()


def test_subtract_phase_keeps_the_wrapping():
    phase = compute.linear_phase(SHAPE, 0.2, 0.1)  # spans much more than 2pi
    to_remove = compute.linear_phase(SHAPE, 0.05, 0.)
    assert np.allclose(compute.subtract_phase(phase, to_remove), phase - to_remove)  # unwrapped stays unwrapped
    wrapped = compute.subtract_phase(wrap(phase), to_remove)
    assert compute.is_wrapped(wrapped) and np.all(np.abs(wrapped) <= np.pi)
    assert np.allclose(np.exp(1j * wrapped), np.exp(1j * (phase - to_remove)))


def test_unwrap_then_wrap_in_the_chain(qtbot, dockarea):
    from pymodaq_plugins_beam_shaping.field.field_tool_app import FieldToolApp

    phase = compute.linear_phase(SHAPE, 0.2, 0.1)
    tool = FieldToolApp(dockarea, field_sources={'output': lambda: make_field(wrap(phase))})
    tool.refresh()
    tool.add_operation('Unwrap phase')
    assert not compute.is_wrapped(tool.field_after.phase[tool.support])
    wrap_op = tool.add_operation('Wrap phase')
    assert np.all((tool.field_after.phase > -np.pi - 1e-12) & (tool.field_after.phase <= np.pi + 1e-12))
    assert np.allclose(np.exp(1j * tool.field_after.phase), np.exp(1j * tool.field_before.phase))
    wrap_op.settings.child('range').setValue('POSITIVE')
    assert np.all((tool.field_after.phase >= 0) & (tool.field_after.phase < 2 * np.pi))
    assert np.allclose(np.exp(1j * tool.field_after.phase), np.exp(1j * tool.field_before.phase))


def test_log10_amplitude():
    amplitude = np.array([[0., 1e-6, 1e-2, 2.]])
    result = compute.log10_amplitude(amplitude, floor=1e-4)
    assert result == pytest.approx(np.log10([[1e-4, 1e-4, 5e-3, 1.]]))
    assert np.all(compute.log10_amplitude(np.zeros((2, 2))) == -4)  # null field: only the floor


def test_log10_amplitude_in_the_chain(qtbot, dockarea):
    from pymodaq_plugins_beam_shaping.field.field_tool_app import FieldToolApp

    tool = FieldToolApp(dockarea, field_sources={'output': lambda: make_field(np.zeros(SHAPE))})
    tool.refresh()
    operation = tool.add_operation('Log10 amplitude')
    assert np.max(tool.field_after.amplitude) == pytest.approx(0.)
    assert operation.settings['results', 'min'] == pytest.approx(-4.)
    assert np.array_equal(tool.field_after.phase, tool.field_before.phase)
    operation.settings.child('floor').setValue(1e-2)
    assert np.min(tool.field_after.amplitude) == pytest.approx(-2.)
