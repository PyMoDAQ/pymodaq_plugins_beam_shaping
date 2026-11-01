"""Numerical functions behind the operations of the Field Tool (no Qt, no Parameter: usable from a script)

Conventions: arrays are 2D (rows = y, columns = x), coordinates are in pixels and centered on the middle of the
array, slopes are in rad/pixel and the phases in rad.
"""
from typing import Optional

import numpy as np
from skimage.restoration import unwrap_phase

ZERNIKE_MODES = ('piston', 'tilt_x', 'tilt_y', 'defocus')


def centered_grid(shape: tuple[int, int]) -> tuple[np.ndarray, np.ndarray]:
    """ y and x coordinates in pixels, with 0 in the middle of the array"""
    y, x = np.indices(shape, dtype=float)
    return y - (shape[0] - 1) / 2, x - (shape[1] - 1) / 2


def support_mask(amplitude: np.ndarray, threshold: float) -> np.ndarray:
    """ Pixels where the amplitude is at least threshold (relative, between 0 and 1) times its maximum"""
    amplitude = np.abs(amplitude)
    amax = np.max(amplitude) if amplitude.size else 0
    if amax == 0:
        return np.zeros(amplitude.shape, dtype=bool)
    return amplitude >= threshold * amax


def unwrap(phase: np.ndarray, support: Optional[np.ndarray] = None) -> np.ndarray:
    """ Unwrap the phase on the support (the whole array if None), the phase outside is kept as it is"""
    if support is None:
        return unwrap_phase(phase)
    if not np.any(support):
        return phase.copy()
    unwrapped = unwrap_phase(np.ma.masked_array(phase, mask=~support))
    out = phase.copy()
    out[support] = np.ma.getdata(unwrapped)[support]
    return out


def _parabolic_offset(left: float, center: float, right: float) -> float:
    """ Sub-pixel position of a peak from three samples (parabola through the log, exact for a gaussian peak)"""
    left, center, right = (np.log(max(value, 1e-300)) for value in (left, center, right))
    denominator = left - 2 * center + right
    if denominator == 0:
        return 0.
    return float(np.clip(0.5 * (left - right) / denominator, -0.5, 0.5))


def linear_phase_fft(field: np.ndarray, support: Optional[np.ndarray] = None,
                     pad_factor: int = 2) -> tuple[float, float]:
    """ Slopes (ky, kx) in rad/pixel of the linear phase of a complex field, from the peak of its spectrum

    The field is set to zero outside the support, zero padded by pad_factor, and the peak is located to the
    sub-pixel by a parabolic interpolation of the logarithm of the spectrum intensity.
    """
    data = field if support is None else np.where(support, field, 0)
    shape = tuple(int(max(1, pad_factor) * size) for size in data.shape)
    spectrum = np.abs(np.fft.fftshift(np.fft.fft2(data, s=shape))) ** 2
    iy, ix = np.unravel_index(np.argmax(spectrum), shape)
    dy = _parabolic_offset(spectrum[(iy - 1) % shape[0], ix], spectrum[iy, ix], spectrum[(iy + 1) % shape[0], ix])
    dx = _parabolic_offset(spectrum[iy, (ix - 1) % shape[1]], spectrum[iy, ix], spectrum[iy, (ix + 1) % shape[1]])
    fy = (iy + dy - shape[0] // 2) / shape[0]  # in cycles/pixel
    fx = (ix + dx - shape[1] // 2) / shape[1]
    return 2 * np.pi * fy, 2 * np.pi * fx


def _weighted_lstsq(basis: list[np.ndarray], values: np.ndarray, weights: np.ndarray) -> np.ndarray:
    sqrt_w = np.sqrt(weights)
    matrix = np.stack([b * sqrt_w for b in basis], axis=1)
    coefficients, *_ = np.linalg.lstsq(matrix, values * sqrt_w, rcond=None)
    return coefficients


def linear_phase_plane(phase: np.ndarray, support: np.ndarray,
                       weights: Optional[np.ndarray] = None) -> tuple[float, float, float]:
    """ Piston (rad) and slopes (ky, kx) in rad/pixel of the plane fitted (weighted least squares) to the
    unwrapped phase on the support"""
    if not np.any(support):
        return 0., 0., 0.
    weights = np.ones(phase.shape) if weights is None else weights
    unwrapped = unwrap(phase, support)
    y, x = centered_grid(phase.shape)
    piston, ky, kx = _weighted_lstsq([np.ones(np.count_nonzero(support)), y[support], x[support]],
                                     unwrapped[support], weights[support])
    return float(piston), float(ky), float(kx)


def linear_phase(shape: tuple[int, int], ky: float, kx: float) -> np.ndarray:
    """ The phase ky * y + kx * x (centered coordinates)"""
    y, x = centered_grid(shape)
    return ky * y + kx * x


def pupil_from_support(amplitude: np.ndarray, support: np.ndarray) -> tuple[tuple[float, float], float]:
    """ Center (y, x in centered pixels) = barycenter of the intensity on the support, and radius (pixels) = the
    largest disk around it inside the support and the array"""
    shape = amplitude.shape
    y, x = centered_grid(shape)
    weights = np.abs(amplitude) ** 2 * support
    total = np.sum(weights)
    if total == 0:
        return (0., 0.), float(min(shape)) / 2
    yc, xc = float(np.sum(weights * y) / total), float(np.sum(weights * x) / total)
    radius = min(yc - y.min() + 0.5, y.max() - yc + 0.5, xc - x.min() + 0.5, x.max() - xc + 0.5)
    outside = ~support
    if np.any(outside):
        radius = min(radius, float(np.min(np.hypot(y[outside] - yc, x[outside] - xc))))
    return (yc, xc), max(radius, 1.)


def zernike_basis(shape: tuple[int, int], center: tuple[float, float], radius: float) -> dict[str, np.ndarray]:
    """ Piston, tilts and defocus (Noll normalisation: unit RMS on the unit disk), evaluated on the whole array"""
    y, x = centered_grid(shape)
    yn, xn = (y - center[0]) / radius, (x - center[1]) / radius
    rho2 = xn ** 2 + yn ** 2
    return {'piston': np.ones(shape),
            'tilt_x': 2 * xn,
            'tilt_y': 2 * yn,
            'defocus': np.sqrt(3) * (2 * rho2 - 1)}


def fit_zernike(phase: np.ndarray, support: np.ndarray, center: tuple[float, float], radius: float,
                weights: Optional[np.ndarray] = None) -> tuple[dict[str, float], dict[str, np.ndarray]]:
    """ Coefficients (rad) of piston, tilts and defocus fitted (weighted least squares) to the unwrapped phase
    inside the pupil and the support. All four are fitted together, the caller removes the ones it wants.

    Returns the coefficients and the basis (to build the phase to remove)."""
    basis = zernike_basis(phase.shape, center, radius)
    y, x = centered_grid(phase.shape)
    region = support & (np.hypot(y - center[0], x - center[1]) <= radius)
    if np.count_nonzero(region) < len(ZERNIKE_MODES):
        return {mode: 0. for mode in ZERNIKE_MODES}, basis
    weights = np.ones(phase.shape) if weights is None else weights
    unwrapped = unwrap(phase, region)
    coefficients = _weighted_lstsq([basis[mode][region] for mode in ZERNIKE_MODES], unwrapped[region],
                                   weights[region])
    return {mode: float(c) for mode, c in zip(ZERNIKE_MODES, coefficients)}, basis


def wrap(phase: np.ndarray) -> np.ndarray:
    """ The phase wrapped in ]-pi, pi]"""
    return np.angle(np.exp(1j * np.asarray(phase)))


def is_wrapped(phase: np.ndarray) -> bool:
    """ True if the values span at most 2pi (wrapped in ]-pi, pi], [0, 2pi]...), up to rounding"""
    return bool(phase.size == 0 or np.ptp(phase) <= 2 * np.pi + 1e-9)


def subtract_phase(phase: np.ndarray, to_remove: np.ndarray) -> np.ndarray:
    """ phase - to_remove, wrapped again if phase was wrapped (an unwrapped phase stays unwrapped)"""
    result = phase - to_remove
    return wrap(result) if is_wrapped(phase) else result


def phase_difference(phase_after: np.ndarray, phase_before: np.ndarray) -> np.ndarray:
    """ angle(E_after * conj(E_before)): the difference wrapped in ]-pi, pi]"""
    return np.angle(np.exp(1j * (phase_after - phase_before)))
