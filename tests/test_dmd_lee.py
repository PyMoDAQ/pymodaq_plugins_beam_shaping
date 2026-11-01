"""The carrier of the order selected in the Fourier plane is removed from the field computed by DMD Lee"""
import numpy as np
import pytest

from pymodaq_plugins_beam_shaping.algorithms.algorithms.dmd_lee import DmDLee, remove_linear_phase
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
