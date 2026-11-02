"""The carrier of the order selected in the Fourier plane is removed from the field computed by the binary holograms"""
import types

import numpy as np
import pytest

from pymodaq_plugins_beam_shaping.algorithms.algorithms.binary_holograms import (
    BinaryThreshold, ParallelLee, Superpixel, superpixel_table, CARRIER_FROM)
from pymodaq_plugins_beam_shaping.field.operations.compute import remove_linear_phase, spectrum_centroid
from pymodaq_plugins_beam_shaping.algorithms.utils import ApplyMaskTo
from pymodaq_plugins_beam_shaping.utilities.masking import MaskType


def _tilted(shape, ky, kx):
    """Field of a given carrier, as given by Field.ifft2 (origin at the index N // 2)"""
    y = np.arange(shape[0])[:, None] - shape[0] // 2
    x = np.arange(shape[1])[None, :] - shape[1] // 2
    return np.exp(2j * np.pi * (ky * y / shape[0] + kx * x / shape[1]))


@pytest.mark.parametrize('shape', [(48, 64), (47, 65)])
@pytest.mark.parametrize('carrier', [(0., 0.), (5., -3.), (-7.4, 11.3)])
def test_remove_linear_phase(shape, carrier):
    field = remove_linear_phase(_tilted(shape, *carrier) * np.exp(0.3j), *carrier)
    assert np.allclose(field, field[0, 0])  # only a constant phase remains
    assert np.allclose(np.abs(field), 1.)


def test_it_is_a_shift_of_the_spectrum():
    shape, carrier = (32, 40), (3, -5)
    rng = np.random.default_rng(0)
    spectrum = rng.normal(size=shape) + 1j * rng.normal(size=shape)
    to_field = lambda spec: np.fft.fftshift(np.fft.ifft2(np.fft.fftshift(spec)))  # as Field.ifft2
    field = remove_linear_phase(to_field(spectrum), *carrier)
    shifted = np.roll(spectrum, (-carrier[0], -carrier[1]), axis=(0, 1))
    assert np.allclose(field, to_field(shifted) * (field[0, 0] / to_field(shifted)[0, 0]))


class _Stub:
    """A binary hologram without the application: the mask of the intermediate plane is set by ``mask_slices``"""
    mask_slices = None

    def __init__(self):
        super().__init__(parent=None)
        self._target_field.amplitude = np.ones(self.shape)  # modulation depth of 1 everywhere
        self.settings.child('px').setValue(5)  # a period of 5 pixels along x and y
        self.settings.child('py').setValue(5)

    def apply_mask(self, apply_to):
        return apply_to == ApplyMaskTo.INTERMEDIATE and self.mask_slices is not None

    def get_mask_slices(self, apply_to):
        return self.mask_slices

    def get_mask_type(self, apply_to):
        return MaskType.ELLIPTICAL

    def value_changed(self, param):
        pass  # asks the application to compute again


class _Lee(_Stub, ParallelLee):
    pass


class _Threshold(_Stub, BinaryThreshold):
    pass


def test_carrier_is_the_center_of_the_mask(qapp):
    lee = _Lee()
    ny, nx = lee.shape
    lee.mask_slices = (slice(ny // 2 + 4, ny // 2 + 12), slice(nx // 2 - 20, nx // 2 - 10))
    assert lee.get_carrier() == pytest.approx((8 - 0.5, -15 - 0.5))  # centers of the pixels 4..11 and -20..-11
    lee.mask_slices = None
    assert lee.get_carrier() is None


def test_the_carrier_of_the_selected_order_is_removed(qapp):
    lee = _Lee()
    ny, nx = lee.shape
    period = lee.settings['px']
    # the pattern cos(2 pi (x - y) / period) puts its orders at +- (ny / period, -nx / period) cycles
    cy, cx = ny // 2 + ny / period, nx // 2 - nx / period
    radius = 6
    lee.mask_slices = (slice(int(cy - radius), int(cy + radius + 1)), slice(int(cx - radius), int(cx + radius + 1)))
    lee._target_field.phase = np.zeros((ny, nx))

    def phase_spread():
        lee.compute_phase_and_or_amplitude()
        center = lee.output_field.field[ny // 2 - 20:ny // 2 + 20, nx // 2 - 20:nx // 2 + 20]
        return np.std(np.angle(center * np.conj(center[20, 20])))

    lee.settings.child('remove_carrier').setValue(False)
    assert phase_spread() > 1.  # a ramp of several radians
    lee.settings.child('remove_carrier').setValue(True)
    assert phase_spread() < 0.2  # flat: the target phase is null


def test_spectrum_centroid():
    spectrum = np.zeros((40, 50), dtype=complex)
    spectrum[20 + 3, 25 - 7] = 2.  # relative to the zero frequency at (N // 2)
    spectrum[20 + 4, 25 - 7] = 2.
    assert spectrum_centroid(spectrum) == pytest.approx((3.5, -7.))
    with pytest.raises(ValueError):
        spectrum_centroid(np.zeros((4, 4)))


def _lee_with_off_center_mask(qapp):
    lee = _Lee()
    ny, nx = lee.shape
    period = lee.settings['px']
    cy, cx = ny // 2 + ny / period, nx // 2 - nx / period
    radius = 20
    # the mask is shifted by a few pixels from the real order, but still contains it
    lee.mask_slices = (slice(int(cy - radius + 5), int(cy + radius + 6)), slice(int(cx - radius - 4), int(cx + radius - 3)))
    lee._target_field.phase = np.zeros((ny, nx))
    return lee


def _phase_spread(lee):
    ny, nx = lee.shape
    lee.compute_phase_and_or_amplitude()
    center = lee.output_field.field[ny // 2 - 20:ny // 2 + 20, nx // 2 - 20:nx // 2 + 20]
    return np.std(np.angle(center * np.conj(center[20, 20])))


def test_the_real_peak_removes_what_the_center_of_the_mask_leaves(qapp):
    lee = _lee_with_off_center_mask(qapp)
    lee.settings.child('carrier_from').setValue(CARRIER_FROM[0])
    from_mask = _phase_spread(lee)
    lee.settings.child('carrier_from').setValue(CARRIER_FROM[1])
    from_peak = _phase_spread(lee)
    assert from_mask > 0.3  # a linear component remains
    assert from_peak < 0.1 < from_mask


def test_carrier_factor(qapp):
    lee = _lee_with_off_center_mask(qapp)
    lee.settings.child('carrier_factor').setValue(0.)
    nothing_removed = _phase_spread(lee)
    lee.settings.child('remove_carrier').setValue(False)
    assert nothing_removed == pytest.approx(_phase_spread(lee))

    lee.settings.child('carrier_factor').setValue(1.)
    full = lee.get_carrier()
    lee.settings.child('carrier_factor').setValue(0.5)
    assert lee.get_carrier() == pytest.approx(tuple(value / 2 for value in full))


def test_the_pattern_is_binarized_or_not_and_follows_the_target_amplitude(qapp):
    lee = _Lee()
    ny, nx = lee.shape
    lee._target_field.amplitude = np.linspace(0., 5., ny * nx).reshape(ny, nx)  # any scale: the peak gets a depth of 1
    assert set(np.unique(lee.compute_amplitude_pattern())) <= {0., 1.}  # binarized by default

    lee.settings.child('binarize').setValue(False)
    pattern = lee.compute_amplitude_pattern()
    assert 0. <= pattern.min() and pattern.max() <= 1.
    assert len(np.unique(pattern)) > 2
    # where the target is null the pattern is flat (0.5), where it is the brightest the modulation is full
    flat, full = pattern[0, :5], pattern[-1, -5:]
    assert np.allclose(flat, 0.5, atol=0.01) and (full.max() - full.min()) > 0.5


@pytest.mark.parametrize('depth', [0.5, 0.75, 1.])
def test_binary_width_modulation_gives_a_first_order_of_the_amplitude_of_the_target(qapp, depth):
    lee = _Lee()
    lee.settings.child('px').setValue(20)
    lee.settings.child('py').setValue(20)  # the width of the stripes is a whole number of pixels: wide period
    ny, nx = lee.shape
    amplitude = np.full((ny, nx), 1.)
    amplitude[:, nx // 2:] = depth  # normalised to the maximum: the right half has a depth of `depth`
    lee._target_field.amplitude = amplitude
    lee._target_field.phase = np.zeros((ny, nx))

    pattern = lee.compute_amplitude_pattern()
    assert set(np.unique(pattern)) <= {0., 1.}

    xx, yy = lee.compute_grid()
    first_order = np.exp(-1j * lee.carrier_phase())  # the carrier of the order +1
    halves = (slice(0, nx // 2), slice(nx // 2, nx))
    amplitudes = [2 * abs(np.mean(pattern[:, half] * first_order[:, half])) for half in halves]
    # the first order of a binary grating of relative width w has the amplitude 2 sin(pi w) / pi, at most 2 / pi
    assert amplitudes[0] == pytest.approx(2 / np.pi, abs=0.05)
    assert amplitudes[1] / amplitudes[0] == pytest.approx(depth, abs=0.1)


def test_the_binary_threshold_loses_the_amplitude_of_the_target(qapp):
    threshold = _Threshold()
    ny, nx = threshold.shape
    amplitude = np.full((ny, nx), 1.)
    amplitude[:, nx // 2:] = 0.25
    threshold._target_field.amplitude = amplitude
    pattern = threshold.compute_amplitude_pattern()  # at 0.5, whatever the depth: on where cos(phase) > 0
    assert set(np.unique(pattern)) <= {0., 1.}
    assert pattern[:, :nx // 2].mean() == pytest.approx(pattern[:, nx // 2:].mean(), abs=0.02)
    assert BinaryThreshold.ALGOTYPE != ParallelLee.ALGOTYPE  # phase only against amplitude and phase


def test_the_binary_threshold_unbinarized_is_the_grey_off_axis_hologram(qapp):
    threshold = _Threshold()
    threshold.settings.child('binarize').setValue(False)
    threshold._target_field.phase = np.full(threshold.shape, 0.4)
    pattern = threshold.compute_amplitude_pattern()
    assert np.allclose(pattern, 0.5 * (1 + np.cos(threshold.carrier_phase() - 0.4)))


def test_the_period_py_is_a_multiple_of_px(qapp):
    lee = ParallelLee()
    lee.parent_app = types.SimpleNamespace(compute_phase_and_or_amplitude=lambda: None)  # the real value_changed
    assert (lee.settings['px'], lee.settings['py']) == (4, 16)  # the default of the review, py = px ** 2
    lee.settings.child('py').setValue(18)  # not a multiple: corrected
    assert lee.settings['py'] == 16
    lee.settings.child('px').setValue(5)  # py = 16 is not a multiple of 5 any more
    assert lee.settings['py'] % 5 == 0
    lee.settings.child('py').setValue(0)  # aligned grating: allowed
    assert lee.settings['py'] == 0 and lee.order_frequency()[0] == 0.


def test_the_carrier_follows_px_and_py(qapp):
    lee = _Lee()
    lee.settings.child('px').setValue(4)
    lee.settings.child('py').setValue(16)
    xx, yy = lee.compute_grid()
    assert np.allclose(lee.carrier_phase(), 2 * np.pi * (xx / 4 - yy / 16))
    lee.settings.child('py').setValue(0)
    assert np.allclose(lee.carrier_phase(), 2 * np.pi * xx / 4)
    lee.settings.child('px').setValue(4)
    lee.settings.child('py').setValue(8)
    ny, nx = lee.shape
    assert lee.order_frequency() == pytest.approx((ny / 8, -nx / 4))


def test_the_order_position_text_tells_where_to_put_the_mask(qapp):
    lee = _Lee()
    lee.update_order_position()
    text = lee.settings['order_position']
    ny, nx = lee.shape
    assert f'{ny / lee.settings["py"]:.1f}' in text and f'{-nx / lee.settings["px"]:.1f}' in text


@pytest.mark.parametrize('phase', [0.7, -1.2, 2.5])
def test_the_selected_order_carries_the_phase_of_the_target(qapp, phase):
    lee = _Lee()
    lee.settings.child('px').setValue(4)
    lee.settings.child('py').setValue(16)
    ny, nx = lee.shape
    ry, rx = lee.order_frequency()
    cy, cx = ny // 2 + ry, nx // 2 + rx
    lee.mask_slices = (slice(int(cy - 5), int(cy + 6)), slice(int(cx - 5), int(cx + 6)))

    def centre_phase(target_phase):
        lee._target_field.phase = np.full((ny, nx), target_phase)
        lee.compute_phase_and_or_amplitude()
        return np.angle(lee.output_field.field[ny // 2 - 5:ny // 2 + 5, nx // 2 - 5:nx // 2 + 5].mean())

    difference = np.angle(np.exp(1j * (centre_phase(phase) - centre_phase(0.))))
    # the phase of the target (not its opposite), with the quantization of the position of the fringes on the pixels
    assert np.angle(np.exp(1j * (difference - phase))) == pytest.approx(0., abs=0.4)


@pytest.mark.parametrize('phase', [0.7, -1.2])
def test_the_output_field_has_the_phase_of_the_target_without_offset(qapp, phase):
    lee = _Lee()
    lee.settings.child('carrier_from').setValue(CARRIER_FROM[0])
    lee.settings.child('px').setValue(4)
    lee.settings.child('py').setValue(16)
    ny, nx = lee.shape
    ry, rx = lee.order_frequency()
    cy, cx = ny // 2 + ry, nx // 2 + rx
    lee.mask_slices = (slice(int(cy - 5), int(cy + 6)), slice(int(cx - 5), int(cx + 6)))
    lee._target_field.phase = np.full((ny, nx), phase)
    lee.compute_phase_and_or_amplitude()
    centre = lee.output_field.field[ny // 2 - 50:ny // 2 + 50, nx // 2 - 50:nx // 2 + 50].mean()
    # the origin of the carrier is the one of the removal: no constant phase of the carrier is left, up to the
    # quantization of the position of the fringes on the pixels
    assert np.angle(np.exp(1j * (np.angle(centre) - phase))) == pytest.approx(0., abs=0.4)


@pytest.mark.parametrize('n, distinct', [(3, 343), (4, 6561)])
def test_the_superpixel_table_has_the_values_of_the_reference(n, distinct):
    # Goorden et al., Opt. Express 22, 17999 (2014): 343 distinct fields for n = 3, 6561 for n = 4
    tree, codes, values, reach = superpixel_table(n)
    assert len(values) == len(codes) == distinct
    assert np.abs(values).max() == pytest.approx(0.32, abs=0.01)  # half of the mirrors on, 10.3 % in intensity
    assert 0.15 < reach < 0.32  # the disk in which any phase is available
    for state, value in zip(codes[:50], values[:50]):  # the value is the sum of the phasors of the mirrors on
        mirrors = np.arange(n * n)
        phasors = np.exp(2j * np.pi * (mirrors % n / n - mirrors // n / n ** 2))
        assert value == pytest.approx((state * phasors).sum() / n ** 2)


class _SuperpixelStub(_Stub, Superpixel):
    def __init__(self):
        super(_Stub, self).__init__(parent=None)
        self._target_field.amplitude = np.ones(self.shape)


def test_the_superpixel_period_py_is_imposed(qapp):
    superpixel = Superpixel()
    superpixel.parent_app = types.SimpleNamespace(compute_phase_and_or_amplitude=lambda: None)
    assert (superpixel.settings['px'], superpixel.settings['py']) == (4, 16)
    assert superpixel.settings.child('py').opts['readonly']
    superpixel.settings.child('px').setValue(3)
    assert superpixel.settings['py'] == 9
    assert (superpixel.settings.child('px').opts['min'], superpixel.settings.child('px').opts['max']) == (2, 4)


def test_the_superpixel_pattern_is_binary(qapp):
    superpixel = _SuperpixelStub()
    assert set(np.unique(superpixel.compute_amplitude_pattern())) <= {0., 1.}


def test_the_superpixel_output_is_the_target_field(qapp):
    superpixel = _SuperpixelStub()
    superpixel.settings.child('carrier_from').setValue(CARRIER_FROM[0])
    ny, nx = superpixel.shape
    ry, rx = superpixel.order_frequency()
    cy, cx = ny // 2 + ry, nx // 2 + rx
    superpixel.mask_slices = (slice(int(cy - 6), int(cy + 7)), slice(int(cx - 6), int(cx + 7)))

    y, x = np.indices((ny, nx))
    amplitude = np.exp(-(((y - ny / 2) / (ny / 4)) ** 2 + ((x - nx / 2) / (nx / 4)) ** 2))
    phase = 1.5 * np.sin(2 * np.pi * (x - nx / 2) / nx) + 2 * (y - ny / 2) / ny
    superpixel._target_field.amplitude = amplitude
    superpixel._target_field.phase = phase
    superpixel.compute_phase_and_or_amplitude()

    window = (slice(ny // 4, 3 * ny // 4), slice(nx // 4, 3 * nx // 4))
    target = (amplitude / amplitude.max() * np.exp(1j * phase))[window]
    output = superpixel.output_field.field[window]
    coherence = np.vdot(target, output) / np.linalg.norm(target) / np.linalg.norm(output)
    assert abs(coherence) > 0.99  # the complex field, amplitude and phase, is the target
    assert np.angle(coherence) == pytest.approx(0., abs=0.05)  # without constant phase
    ratio = np.abs(output).mean() / np.abs(target).mean()  # the efficiency: the target is scaled to the reach of the table
    assert ratio == pytest.approx(superpixel_table(4)[3], rel=0.05)
