import numpy as np
from typing import Tuple, Iterable, Union
from numbers import Number
from collections.abc import Iterable

from pymodaq_utils.logger import set_logger, get_module_name
from pymodaq_data.data import DataRaw, Axis, DataToExport
from pymodaq.utils.data import DataActuator

from pymodaq_data import Q_

logger = set_logger(get_module_name(__file__))


try:
    import pyfftw
    pyfftw.interfaces.cache.enable()


    def wrap_fft(*args, **kwargs):
        fft2 = pyfftw.interfaces.numpy_fft.fft2(threads=8, *args, **kwargs)
        return fft2


    def wrap_ifft(*args, **kwargs):
        ifft2 = pyfftw.interfaces.numpy_fft.ifft2(threads=8, *args, **kwargs)
        return ifft2


    def wrap_fftshift(*args, **kwargs):
        fftshift = pyfftw.interfaces.numpy_fft.fftshift(*args, **kwargs)
        return fftshift


    def wrap_ifftshift(*args, **kwargs):
        ifftshift = pyfftw.interfaces.numpy_fft.ifftshift(*args, **kwargs)
        return ifftshift


    fft2 = wrap_fft
    ifft2 = wrap_ifft

    fftshift = wrap_fftshift
    ifftshift = wrap_ifftshift

except ImportError:
    fft2 = np.fft.fft2
    ifft2 = np.fft.ifft2
    fftshift = np.fft.fftshift
    ifftshift = np.fft.ifftshift
    print("Warning: using numpy FFT implementation.  "
          "Consider using pyFFTW for faster Fourier transforms.")


class Field(DataRaw):
    def __init__(self, name='', amplitude: np.ndarray = None, phase: np.ndarray = None,
                 pixel_sizes=(Q_(10., 'micron'), Q_(10., 'micron'))):

        self._pixels_sizes: Tuple[Q_, Q_] = None

        super().__init__(name=name, data=[np.ones((2, 2)), np.zeros((2, 2))],)

        self.calibrate_axes(pixel_sizes)

        if amplitude is not None:
            self.amplitude = amplitude
        if phase is not None:
            self.phase = phase

        self.axes = self.get_axes()

    def __mul__(self, other):
        """ multiplication is possible with numbers but then the amplitude is multiplied while the phase is summed"""
        if isinstance(other, Number):
            field = Field(self.name, self.amplitude * np.abs(other), self.phase + np.angle(other),
                          pixel_sizes=self.pixels_sizes)
        else:
            raise TypeError(f"Cannot multiply Field and {type(other)}")
        return field

    def calibrate_axes(self, pixel_sizes: Union[Q_, Iterable[Q_]]):
        """ Specify the size of the underlying 2D array pixels on which the field object is defined

        Parameters
        ----------
        pixel_sizes: Tuple[Quantities, Quantities)
            The pixel sizes corresponding to the array shape in meter
        """
        if not isinstance(pixel_sizes, Iterable):
            pixel_sizes = (pixel_sizes, pixel_sizes)
        self._pixels_sizes = pixel_sizes

    @property
    def pixels_sizes(self) -> Tuple[Q_, Q_]:
        return self._pixels_sizes

    def get_axes(self):
        units = [str(pixel_size.to_base_units().units) for pixel_size in self.pixels_sizes]
        return [Axis('Hor Axis', units[1], scaling=self._pixels_sizes[1].m_as(units[1]), offset=0,
                     index=1, size=self.shape[1]),
                Axis('Ver Axis', units[0], scaling=self._pixels_sizes[0].m_as(units[0]), offset=0,
                     index=0, size=self.shape[0]),]

    @staticmethod
    def init_from_field(field: 'Field') -> 'Field':
        """ Create a field object with flat amplitude and zero phase but with the same shape as
        the field parameter"""
        field_new = Field(field.name, amplitude=field.amplitude)
        field_new.amplitude = np.ones_like(field.amplitude)
        return field_new

    def split_as_dte(self, name: str = 'mydte') -> DataToExport:
        """ The amplitude and the phase as two data objects, e.g. to plot them side by side: field.split_as_dte().plot('qt')

        Reimplemented because the parent method creates objects of the same type with a single array, which a Field
        cannot be (it always holds an amplitude and a phase, and its axes come from its pixel sizes)
        """
        return DataToExport(name, data=[self.amplitude_as_dwa(self.name), self.phase_as_dwa(self.name)])

    def _slicer(self, slices, is_navigation=True, is_index=True):
        dwa = super()._slicer(slices, is_navigation, is_index)
        return Field(self.name, amplitude=dwa[0], phase=dwa[1], pixel_sizes=self.pixels_sizes)

    def pad(self, pad_width: Tuple[Tuple[int, int], Tuple[int, int]], **kwargs) -> 'Field':
        """ Get a Field object similar to self but padded

        see numpy.pad method for the signature and possible named arguments
        """
        return Field(f'{self.name}_padded',
                     amplitude=np.pad(self.amplitude, pad_width, **kwargs),
                     phase=np.pad(self.phase, pad_width, **kwargs),
                     pixel_sizes=self.pixels_sizes)

    def unpad(self, pad_width: Tuple[Tuple[int, int], Tuple[int, int]],
              ini_shape: Tuple[int, int]) -> 'Field':
        """ Get a Field object from a padded Field object

        see numpy.pad method for the signature
        """
        return Field(f'{self.name}_unpadded',
                     self.amplitude[pad_width[0][0] + 1:pad_width[0][0] + 1 + ini_shape[0],
                     pad_width[1][0] + 1:pad_width[1][0] + 1 + ini_shape[1]],
                     self.phase[pad_width[0][0] + 1:pad_width[0][0] + 1 + ini_shape[0],
                     pad_width[1][0] + 1:pad_width[1][0] + 1 + ini_shape[1]],
                     pixel_sizes=self.pixels_sizes)

    def fft2(self, scaling=Q_(1., ''), **kwargs) -> 'Field':
        """ Compute the field being the Fourier Transform of self

        The corresponding "frequency" pixel size is computed  from the total size of the input
        aperture (self.shape and self.pixel_sizes). Eventually a scaling coefficient can be applied
        to this "frequency" pixel size, for instance if the Fourier Transform is made using a lens

        Parameters
        ----------
        scaling: pint.Quantity
            Apply this axis scaling to the transformed field (on pixel_sizes)
        kwargs: variable named parameters passed to numpy fft2 method (norm, ...)
        """
        field_array = fftshift(fft2(fftshift(self.field), **kwargs)) / \
                      np.sqrt(np.prod(self.shape))
        field = Field()
        field.field = field_array
        frequency_pixel_size = [1 / (2 * self.shape[ind] * self.pixels_sizes[ind]) * scaling for ind in range(2)]
        field.calibrate_axes(frequency_pixel_size)
        return field

    def ifft2(self, scaling=Q_(1., ''), **kwargs):
        """ Compute the field being the Inverse Fourier Transform of self

        In this place, self.pixel_sizes are in fact a spatial frequency. The corresponding
        transformed pixel size is computed  from the total size of the input
        aperture (self.shape and self.pixel_sizes). Eventually a scaling coefficient can be applied
        to this transformed pixel size, for instance if the Fourier Transform is made using a lens

        Parameters
        ----------
        scaling: pint.Quantity
            Apply this axis scaling to the transformed field (on pixel_sizes)
        kwargs: variable named parameters passed to numpy ifft2 method (norm, ...)
        """
        field_array = fftshift(ifft2(fftshift(self.field), **kwargs)) / \
                      np.sqrt(np.prod(self.shape))
        field = Field()
        field.field = field_array
        pixel_size = [1 / (2 * self.shape[ind] * self.pixels_sizes[ind]) * scaling for ind in range(2)]
        field.calibrate_axes(pixel_size)
        return field

    @property
    def field(self) -> np.ndarray:
        """ Get set the field as a complex 2D array"""
        return self[0] * np.exp(1j * self[1])

    @field.setter
    def field(self, field_array: np.ndarray):
        self.data = [np.abs(field_array), np.angle(field_array)]
        self.set_axes_manager(self.shape, self.get_axes(), ())

    @property
    def amplitude(self) -> np.ndarray:
        return self[0]

    @amplitude.setter
    def amplitude(self, amp_array: np.ndarray):

        if not self.amplitude.shape == amp_array.shape:
            logger.warning('New amplitude is not coherent with existing phase shape'
                           'Setting the phase to flat zeros')
            phase_array = np.zeros_like(amp_array)
        else:
            phase_array = self.phase

        self.data = [amp_array, phase_array]

    @property
    def intensity(self) -> np.ndarray:
        return np.abs(self.amplitude) ** 2

    @property
    def phase(self) -> np.ndarray:
        return self[1]

    @phase.setter
    def phase(self, phase_array: np.ndarray):
        if not self.phase.shape == phase_array.shape:
            logger.warning('New phase is not coherent with existing amplitude shape'
                           'Setting the amplitude to flat ones')
            amp_array = np.ones_like(phase_array)
        else:
            amp_array = self.amplitude

        self.data = [amp_array, phase_array]

    @property
    def real_field(self) -> np.ndarray:
        """ return the real part of the field as a 2D array"""
        return self.amplitude * np.cos(self.phase)

    @property
    def imag_field(self):
        """ return the imaginary part of the field as a 2D array"""
        return self.amplitude * np.sin(self.phase)


    def amplitude_as_dwa(self, origin_name: str = '', name: str = None):
        if not (name is None or isinstance(name, str)):
            name = 'amplitude'
        return DataActuator('amplitude' if name is None else name, data=[self.amplitude],
                            axes=self.get_axes(), origin=origin_name,
                            labels=['Amplitude'])

    def phase_as_dwa(self, origin_name: str = '', name: str = None):
        if not (name is None or isinstance(name, str)):
            name = 'phase'
        return DataActuator('phase' if name is None else name, data=[self.phase],
                            axes=self.get_axes(), origin=origin_name,
                            labels=['Phase'])

    def intensity_as_dwa(self, origin_name: str = '', name: str = None):
        if not (name is None or isinstance(name, str)):
            name = 'intensity'
        return DataActuator('intensity' if name is None else name, data=[self.intensity],
                            axes=self.get_axes(), origin=origin_name,
                            labels=['Intensity'])

    def normalise_to_one(self) -> 'Field':
        """ A copy of the field normalised on itself: its maximum amplitude, hence its maximum intensity, is 1

        The phase is kept. A null field is returned unchanged (there is nothing to normalise)
        """
        peak = float(np.max(self.amplitude))
        if peak == 0.:
            return Field(self.name, amplitude=self.amplitude.copy(), phase=self.phase.copy(),
                         pixel_sizes=self.pixels_sizes)
        return self * (1. / peak)

    def normalise_to_intensity(self, field: 'Field'):
        """ Normalise a Field object to this input total intensity

        Parameters
        ----------
        field: Field
            the Field to be normalised with respect to the total intensity

        Returns
        -------
        Field
        """
        return field * np.sum(self.intensity) / np.sum(field.intensity)


