import numpy as np

from pymodaq.utils.data import DataActuator

from pymodaq_plugins_beam_shaping.utilities.sizing import get_slm_size, get_effective_slm_pixel_size


N_PI = 2.2  # dynamic range of the SLM in units of pi


def gaussian_fwhm(x: np.ndarray, x0: float, fwhm: float) -> np.ndarray:
    """ Get a Gaussian amplitude distribution centered in x0 with a full width at half maximum in intensity of fwhm

    Parameters
    ----------
    x: np.ndarray
        distribution on which the gaussian is evaluated (in microns)
    x0: float
        center of the gaussian distribution (in micron)
    fwhm: float
        full width at half maximum in intensity expressed (in micron)

    Returns
    -------
    np.ndarray
    """
    return np.exp(- 2 * np.log(2) * ((x - x0) / fwhm) ** 2)


def compute_grid() -> tuple[np.ndarray, np.ndarray]:
    """ Compute the centered positions on the grid in microns given the value of the pixel width"""

    n_pixel_height, n_pixel_width = get_slm_size()
    pixel_height, pixel_width = (get_effective_slm_pixel_size(), get_effective_slm_pixel_size())

    x = np.arange(0, n_pixel_width, 1) * pixel_width   #um
    x = x-np.mean(x)
    y = np.arange(0, n_pixel_height, 1) * pixel_height  #um
    y = y - np.mean(y)
    xx, yy = np.meshgrid(x, y)
    return xx, yy


class ShaperCamera:

    gaussian_width_ini = 7e3

    def __init__(self):
        self._slm_values: np.ndarray = np.zeros(get_slm_size())
        self._slm_amplitudes: np.ndarray = np.ones(get_slm_size())

        self._gaussian_width: float = None
        self._amplitude: np.ndarray = None

        self.gaussian_width = self.gaussian_width_ini

    def get_slm_phases(self) -> np.ndarray:
        return self._slm_values

    @staticmethod
    def get_slm_grid() -> tuple[np.ndarray, np.ndarray]:
        return compute_grid()

    @property
    def gaussian_width(self) -> float:
        return self._gaussian_width

    @gaussian_width.setter
    def gaussian_width(self, value: float):
        xx, yy = compute_grid()
        self._gaussian_width = value
        self._amplitude = (gaussian_fwhm(xx, 0, self._gaussian_width) *
                           gaussian_fwhm(yy, 0, self._gaussian_width))

    def apply_grey_scale(self, value: np.ndarray):
        self._slm_values = value * N_PI * np.pi / 256

    def apply_phase(self, value: np.ndarray):
        self._slm_values = value

    def get_slm_amplitudes(self) -> np.ndarray:
        return self._slm_amplitudes

    def apply_amplitude(self, value: np.ndarray):
        """Transmission (between 0 and 1) of each pixel of an amplitude modulator"""
        self._slm_amplitudes = value

    def get_camera(self, amplitude_mask: np.ndarray = None) -> np.ndarray:
        field = self._amplitude * self._slm_amplitudes * np.exp(1j * self._slm_values)
        if amplitude_mask is not None and amplitude_mask.shape == field.shape:
            field *= amplitude_mask
        return np.abs(np.fft.fftshift(np.fft.fft2(np.fft.fftshift(field))) /
                      np.sqrt(np.prod(self._slm_values.shape))) ** 2
