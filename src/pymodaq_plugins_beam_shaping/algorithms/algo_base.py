from abc import ABCMeta
from typing import Optional, Union, Tuple, TYPE_CHECKING

import numpy as np
from scipy.ndimage.filters import gaussian_filter

from pymodaq_utils.warnings import deprecation_msg
from pyqtgraph.parametertree import Parameter
from qtpy import QtWidgets

from pymodaq_plugins_beam_shaping.utilities.shaper import Shaper, ModulatorType, get_default_shaper
from pymodaq_utils.math_utils import gauss2D
from pymodaq_data import Q_, DataRaw, DataToExport
from pymodaq_gui.managers.parameter_manager import ParameterManager

from pymodaq_plugins_beam_shaping.algorithms.utils import (AlgoType, ApplyMaskTo,
                                                           LensSetup, CrossTalk, PhaseManipulation)
from pymodaq_plugins_beam_shaping.field import Field
from pymodaq_plugins_beam_shaping.utilities import sizing
from pymodaq_plugins_beam_shaping.utilities.masking import MaskType

from pymodaq_plugins_beam_shaping.utils import Config

if TYPE_CHECKING:
    from pymodaq_plugins_beam_shaping.algorithms.algorithm_app import AlgoApp


plugin_config = Config()


class AlgoParameterManager(ParameterManager):
    settings_name = 'algo_settings'

    def __init__(self):
        super().__init__()
        self.settings_tree.header().setVisible(True)
        self.settings_tree.header().setSectionResizeMode(
            QtWidgets.QHeaderView.ResizeMode.Interactive)
        self.settings_tree.header().setMinimumSectionSize(150)
        self.settings_tree.setMinimumHeight(150)


class AlgoBase(AlgoParameterManager, metaclass=ABCMeta):
    """
    Here goes the abstract methods and shared properties/attributes of all algorithms used to
    calculate amplitude/phase shaping
    """

    ALGO_NAME: str = None  # to be reimplemented
    SETUP_TYPE: LensSetup = None # to be reimplemented
    ALGOTYPE = AlgoType.AMPLITUDE
    # the modulators the algorithm can compute a mask for (a shaper modulating both accepts any algorithm)
    MODULATOR_TYPES: tuple[ModulatorType] = (ModulatorType.PHASE, )
    INI_PHASE = True  # if True, the algorithm will init an initial phase
    ITERATIVE = False
    MANUAL_LOOP = True
    params = []


    def __init__(self, parent: 'AlgoApp' = None,
                 crosstalk = CrossTalk(),
                 phase_wrap = PhaseManipulation(), ):

        super().__init__()

        self._running = False
        self.fitness_name: str = ''

        self._crosstalk: CrossTalk = crosstalk
        self._phase_wrap: PhaseManipulation = phase_wrap

        self.parent_app = parent
        self._shaper: Optional[Shaper] = None  # only used without parent app, see the shaper property
        self._target_field = Field(amplitude=np.zeros(sizing.get_effective_needed_field_size(self.shaper)))
        self._input_field = Field(amplitude=np.zeros(sizing.get_effective_needed_field_size(self.shaper)))
        self.intermediate_field: Optional[Field] = None

        self._modulator_field = Field(amplitude=np.zeros(sizing.get_effective_needed_field_size(self.shaper)))
        self._modulator_field.calibrate_axes(self._input_field.pixels_sizes)
        self._output_field = Field(amplitude=np.zeros(sizing.get_effective_needed_field_size(self.shaper)))

        self.update_mask = True

    @classmethod
    def supports(cls, modulator_type: ModulatorType) -> bool:
        """True if the algorithm can be used with a shaper of this modulation type"""
        return ModulatorType(modulator_type) == ModulatorType.BOTH or modulator_type in cls.MODULATOR_TYPES

    @property
    def shaper(self) -> Shaper:
        """The shaper the algorithm computes for: the one of the parent app, else the default shaper"""
        if self.parent_app is not None and getattr(self.parent_app, 'shaper', None) is not None:
            return self.parent_app.shaper
        return self._shaper if self._shaper is not None else get_default_shaper()

    @shaper.setter
    def shaper(self, shaper: Shaper):
        self._shaper = shaper

    @property
    def crosstalk(self) -> CrossTalk:
        return  self._crosstalk

    @crosstalk.setter
    def crosstalk(self, crosstalk: CrossTalk):
        self._crosstalk = crosstalk

    @property
    def phase_manipulation(self) -> PhaseManipulation:
        return  self._phase_wrap

    @phase_manipulation.setter
    def phase_manipulation(self, phase_wrap: PhaseManipulation):
        self._phase_wrap = phase_wrap

    def quit(self):
        """ to reimplement if necessary"""
        pass

    def apply_mask(self, apply_to: Union[ApplyMaskTo, str]) -> bool:
        return self.parent_app.apply_mask(apply_to)

    def get_mask_slices(self, apply_to: Union[ApplyMaskTo, str]) -> tuple[slice, slice]:
        """ Get the slices defined in the settings depending on the field it should apply to"""
        return self.parent_app.get_mask_as_slices(apply_to)

    def get_mask_field(self, apply_to: Union[ApplyMaskTo, str], inner_value=1, outer_value=0) -> Field:
        """ Return a Field to be used to mask fields within the algorithm

        To be reimplemented if needed
        """
        if self.apply_mask(apply_to):
            mask = Field.init_from_field(self._target_field).amplitude * outer_value
            slices = self.get_mask_slices(apply_to)

            if self.get_mask_type(apply_to) == MaskType.SQUARE:
                mask[tuple(slices)] = inner_value
            else:
                x = np.arange(0, self._target_field.shape[1], 1)
                y = np.arange(0, self._target_field.shape[0], 1)
                y0, x0 = tuple([(_slice.stop + _slice.start) / 2 for _slice in slices])
                ry, rx = tuple([(_slice.stop - _slice.start) / 2 for _slice in slices])

                xx, yy = np.meshgrid(x, y)
                mask[
                    (xx - x0) ** 2 / rx ** 2 + (yy - y0) ** 2 / ry ** 2 <= 1] = inner_value
        else:
            mask = Field.init_from_field(self._target_field).amplitude
        return Field(amplitude=mask)

    def get_mask_type(self, apply_to: Union[ApplyMaskTo, str]) -> MaskType:
        return self.parent_app.get_mask_type(apply_to)

    @property
    def output_field(self) -> Field:
        return self._output_field

    @property
    def modulator_field(self) -> Field:
        return self._modulator_field

    @property
    def target_field_pixels_sizes(self) -> tuple[Q_, Q_]:
        return self._target_field.pixels_sizes

    @property
    def input_field_pixels_sizes(self) -> tuple[Q_, Q_]:
        return self._input_field.pixels_sizes

    @property
    def shape(self):
        return sizing.get_effective_needed_field_size(self.shaper)

    def set_input_field(self, field: Field):
        self._input_field = field
        self.do_things_after_set_input()

    def define_input_phase(self, phase):
        phase = (phase + np.pi) % (2 * np.pi) - np.pi
        self.set_phase_in_modulator_plane(phase)

    def compute_forward_fft(self, update_plots = True):
        """ Compute the forward fft usnig the "forward nomalization and the shape prefactor"""
        self._output_field = self._modulator_field.fft2(norm='forward') * np.prod(self._modulator_field.shape)
        self._output_field = self.scale_target_with_geometry(self._output_field)

        if update_plots and self.parent_app is not None:
            self.parent_app.fields_to_plot.emit(self.get_fields_to_plot())

    def compute_backward_fft(self, field: Field) -> Field:
        return field.ifft2(norm='forward')

    @staticmethod
    def normalize_wrt(field: Field, ref_field: Field) -> Field:
        """ Make sure the intensities are normalized """
        field.amplitude  = field.amplitude * np.sqrt(np.sum(np.abs(ref_field.amplitude) ** 2) /
                                                     np.sum(np.abs(field.amplitude) ** 2))
        return field

    def stop(self):
        self._running = False

    def start(self):
        self._running = True

    def set_modulator_field(self, field: Field):
        self._modulator_field = field
        self.do_things_after_set_modulator()

    def set_target_field(self, field: Field):
        self._target_field = self.normalize_wrt(field, self._input_field)
        self._output_field = Field.init_from_field(self._target_field)
        self.do_things_after_set_target()

    def set_target_intensity(self, intensity: np.ndarray):
        self._target_field.amplitude = np.sqrt(intensity)

    def set_field_in_modulator_plane(self, field: Field):
        modulator_type = self.shaper.modulator_type
        if modulator_type == ModulatorType.PHASE:
            self.set_phase_in_modulator_plane(field.phase)
        elif modulator_type == ModulatorType.AMPLITUDE:
            self.set_amplitude_in_modulator_plane(field.amplitude)
        else:
            self.set_phase_in_modulator_plane(field.phase)
            self.set_amplitude_in_modulator_plane(field.amplitude)

    def set_amplitude_in_modulator_plane(self, amplitude: np.ndarray):
        self._modulator_field.amplitude = amplitude

    def set_phase_in_modulator_plane(self, phase: np.ndarray, induced_amplitude: np.ndarray = None):
        if phase.shape == self._modulator_field.shape:
            phase = phase.copy()
            if self.phase_manipulation.apply:
                phase = phase % (self.phase_manipulation.wrap_value * np.pi)
                phase = (np.round(
                    phase / (self.phase_manipulation.wrap_value * np.pi) * 2**self.phase_manipulation.dynamic_value) *
                         (self.phase_manipulation.wrap_value * np.pi) / 2**self.phase_manipulation.dynamic_value)
            if self.crosstalk.apply:
                phase = gaussian_filter(phase, self.crosstalk.value)

            self._modulator_field.phase = phase
            self._modulator_field.amplitude = (
                    self._input_field.amplitude.copy() *
                    (induced_amplitude if induced_amplitude is not None else 1))
        else:
            raise ValueError('The phase shape is incoherent with the parameters')

    @property
    def intensity_output(self):
        return self._output_field.intensity

    @property
    def fitness(self) -> float:
        """ Compute fitness with respect to the output_field and target_field

        To be subclassed if the given implementation below is not correct for your algorithm"""
        if self.ALGOTYPE == AlgoType.AMPLITUDE:
            self.fitness_name = 'NRMSE'
            return self.nrmse

        elif self.ALGOTYPE == AlgoType.AMPLITUDE_PHASE:
            self.fitness_name = 'Fidelity Error'
            return 1 - self.fidelity_error
        else:
            raise TypeError('Algorithm type not supported')

    @property
    def fidelity_error(self) -> float:
        if self.apply_mask(ApplyMaskTo.TARGET):
            slices = self.get_mask_slices(ApplyMaskTo.TARGET)
        else:
            slices = (...,)
        return 1- np.sqrt(np.abs(np.sum(np.conj(self._target_field.field[tuple(slices)]) * self._output_field.field[tuple(slices)])) ** 2 /
                          (np.sum(self._target_field.intensity[tuple(slices)] ** 2)))

    @property
    def nrmse(self) -> float:
        if self.apply_mask(ApplyMaskTo.TARGET):
            slices = self.get_mask_slices(ApplyMaskTo.TARGET)
        else:
            slices = (...,)
        norm = 1

        return np.sqrt(1 / norm * (
                np.sum(
                    (self._target_field.intensity[tuple(slices)] - self._output_field.intensity[tuple(slices)]) ** 2) /
                np.sum(self._target_field.intensity[tuple(slices)] ** 2)))

    @property
    def efficiency(self) -> float:
        """ Compute efficiency as the ratio between output_field intensity within a given region
        and total intensity

        Meaningfully only for algorithm using a Target defined mask

        To be subclassed if the given implementation below is not correct for your algorithm"""
        if self.apply_mask(ApplyMaskTo.TARGET):
            slices = self.get_mask_slices(ApplyMaskTo.TARGET)
        else:
            slices = (...,)

        return (np.sum(self._output_field.intensity[tuple(slices)]) /
                np.sum(self._output_field.intensity))

    def fitness_as_dwa(self):
        return DataRaw('fitness', data=[np.array([self.fitness])],
                       labels=[self.fitness_name])

    def metrics_as_dwa(self):
        return DataRaw('metrics', data=[np.array([self.fitness]),
                                        np.array([self.efficiency])],
                       labels=[self.fitness_name, 'efficiency'])

    def compute_phase_and_or_amplitude(self, do_step=True, ini_phase: np.ndarray = None, **kwargs):
        """ Compute the phase or the amplitude to apply to SLM given the target Field

        To be subclassed in real implementation
        """
        # if not reimplemented this method will be called and will test for backcompatibility self.compute_phase
        try:
            return self.compute_phase(do_step=do_step, ini_phase=ini_phase, **kwargs)
        except NotImplementedError:
            raise NotImplementedError

    def compute_phase(self, do_step=True, ini_phase: np.ndarray = None, **kwargs):
        """ Compute the phase to apply to SLM given the target Field

        Deprecated, use :meth:`compute_phase_and_or_amplitude`

        """
        deprecation_msg('compute_phase is deprecated, use compute_phase_and_or_amplitude')
        raise NotImplementedError

    def get_fields_to_plot(self) -> DataToExport:
        dte =  DataToExport('AlgoData', data=[
            self.output_field.amplitude_as_dwa('output'),
            self.output_field.phase_as_dwa('output'),
            self.metrics_as_dwa(),
            self.modulator_field.amplitude_as_dwa('modulator'),
            self.modulator_field.phase_as_dwa('modulator'),
        ])
        if self.intermediate_field is not None:
            dte.append(self.intermediate_field.intensity_as_dwa('intermediate'))
        return dte

    def do_things_after_init(self):
        """ to reimplement if needed"""
        pass

    def do_things_after_set_input(self):
        """ to reimplement if needed"""
        pass

    def do_things_after_set_target(self):
        """ to reimplement if needed"""
        pass

    def do_things_after_set_modulator(self):
        """ to reimplement if needed"""
        pass


    def scale_target_with_geometry(self, field: Field):
        """ Apply an axis scaling to have the target and its axes in correct units with respect to
        a given algorithm implementation and experimental setup
        """
        field.calibrate_axes(self.get_target_pixels_size())
        return field

    def get_target_pixels_size(self, input_size: Tuple[Q_, Q_] = None) -> list[Q_]:
        """ Get the expected physical size of the pixels in the target plane given
        the chosen algorithm and physical parameters: focal length, wavelength...

        Here we use either a 4f setup or a 2f setup, so the output field has the same size as the SLM with a ratio given by the focal
        length ratio

        """
        if input_size is None:
            input_size = [self._input_field.shape[ind] * self._input_field.pixels_sizes[ind]
                          for ind in range(2)]
        binning = plugin_config('sizing', 'binning')
        if self.SETUP_TYPE == LensSetup.TwoF:
            return [Q_(plugin_config('setup', 'wavelength_nm', ), 'nm') *
                    Q_(plugin_config('setup', self.SETUP_TYPE.value, 'focals')[0], 'mm') * binning /
                    size for size in input_size]

        elif self.SETUP_TYPE == LensSetup.FourF:
            pixels_size = self._input_field.pixels_sizes
            focal_ratio = (plugin_config('setup', self.SETUP_TYPE.value, 'focals')[1] /
                           plugin_config('setup', self.SETUP_TYPE.value, 'focals')[0])
            return [size * focal_ratio for size in pixels_size]

        else:
            raise NotImplementedError('The setup type is not recognized and cannot compute the pixels size')

    @property
    def intermediate_pixel_sizes(self):
        if self.SETUP_TYPE == LensSetup.FourF:
            slm_pixel_sizes = self._input_field.pixels_sizes
            intermediate_pixel_sizes = [((Q_(plugin_config('setup', 'wavelength_nm',), 'nm') *
                                         Q_(plugin_config('setup', self.SETUP_TYPE.value, 'focals')[0], 'mm')) /
                                        (slm_pixel_sizes[ind] * self._target_field.shape[ind])
                                        ).to('um') for ind in range(2)]

            return intermediate_pixel_sizes
        else:
            raise ValueError('Intermediate pixel size can only be computed for 4f setups')

    def value_changed(self, param: Parameter):
        self.parent_app.algo_settings_changed()
