"""The carrier of the order selected in the Fourier plane is removed from the field computed by DMD Lee"""
import numpy as np
import pytest

from pymodaq_plugins_beam_shaping.algorithms.algorithms.dmd_lee import DmDLee, remove_linear_phase, spectrum_centroid, CARRIER_FROM
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


class _Lee(DmDLee):
    """DMD Lee without the application: a circular mask around the first order of the pattern"""
    mask_slices = None

    def __init__(self):
        super().__init__(parent=None)
        self._target_field.amplitude = np.ones(self.shape)  # modulation depth of 1 everywhere

    def apply_mask(self, apply_to):
        return apply_to == ApplyMaskTo.INTERMEDIATE and self.mask_slices is not None

    def get_mask_slices(self, apply_to):
        return self.mask_slices

    def get_mask_type(self, apply_to):
        return MaskType.ELLIPTICAL

    def value_changed(self, param):
        pass  # asks the application to compute again


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
    period = lee.settings['super_pixel']
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
    period = lee.settings['super_pixel']
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
    lee.settings.child('super_pixel').setValue(20)  # the width of the stripes is a whole number of pixels: wide period
    ny, nx = lee.shape
    amplitude = np.full((ny, nx), 1.)
    amplitude[:, nx // 2:] = depth  # normalised to the maximum: the right half has a depth of `depth`
    lee._target_field.amplitude = amplitude
    lee._target_field.phase = np.zeros((ny, nx))

    pattern = lee.compute_amplitude_pattern()
    assert set(np.unique(pattern)) <= {0., 1.}

    xx, yy = lee.compute_grid()
    first_order = np.exp(-2j * np.pi * (xx - yy) / lee.settings['super_pixel'])  # the carrier of the order +1
    halves = (slice(0, nx // 2), slice(nx // 2, nx))
    amplitudes = [2 * abs(np.mean(pattern[:, half] * first_order[:, half])) for half in halves]
    # the first order of a binary grating of relative width w has the amplitude 2 sin(pi w) / pi, at most 2 / pi
    assert amplitudes[0] == pytest.approx(2 / np.pi, abs=0.05)
    assert amplitudes[1] / amplitudes[0] == pytest.approx(depth, abs=0.1)


def test_the_binarization_by_threshold_loses_the_amplitude_of_the_target(qapp):
    lee = _Lee()
    ny, nx = lee.shape
    amplitude = np.full((ny, nx), 1.)
    amplitude[:, nx // 2:] = 0.25
    lee._target_field.amplitude = amplitude
    lee.settings.child('binarize_method').setValue('Threshold')  # at 0.5, whatever the depth: on where cos(phase) > 0
    pattern = lee.compute_amplitude_pattern()
    assert pattern[:, :nx // 2].mean() == pytest.approx(pattern[:, nx // 2:].mean(), abs=0.02)


def test_the_selected_order_carries_the_phase_of_the_target_whichever_side_it_is(qapp):
    """The two first orders of the grating carry opposite phases: the sign of the target phase in the pattern follows
    the order selected by the mask"""
    lee = _Lee()
    lee.settings.child('binarize').setValue(False)
    lee._target_field.phase = np.full(lee.shape, 0.7)
    ny, nx = lee.shape
    patterns = []
    for columns in (slice(nx // 2 + 10, nx // 2 + 20), slice(nx // 2 - 20, nx // 2 - 10)):
        lee.mask_slices = (slice(ny // 2 - 5, ny // 2 + 5), columns)
        patterns.append(lee.compute_amplitude_pattern())
    xx, yy = lee.compute_grid()
    theta = 2 * np.pi * (xx - yy) / lee.settings['super_pixel']
    assert lee.order_sign() == 1  # the mask on the negative frequency side
    assert np.allclose(patterns[1], 0.5 * (1 + np.cos(theta - 0.7)))
    assert np.allclose(patterns[0], 0.5 * (1 + np.cos(theta + 0.7)))
