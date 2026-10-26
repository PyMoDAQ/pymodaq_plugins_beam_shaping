from abc import ABCMeta, abstractproperty
from typing import Union
import numpy as np

from qtpy import QtWidgets, QtCore
from pathlib import Path

import pymodaq_gui.qt_utils
from pymodaq_data import DataCalculated
from pymodaq_gui.plotting.items.roi import RoiInfo
from pymodaq_utils.utils import ThreadCommand
from pymodaq_utils.config import GlobalConfig

from pymodaq_data.data import DataRaw, DataToExport, DataDim
from pymodaq_data.h5modules.data_saving import DataToExportSaver
from pymodaq_data.h5modules.saving import SaveType

from pymodaq_gui.managers.parameter_manager import Parameter
from pymodaq_gui.utils.custom_app import CustomApp
from pymodaq_gui.parameter.ioxml import parameter_to_xml_string
from pymodaq_utils.enums import StrEnum
from pymodaq_gui.utils.dock import DockArea, Dock
from pymodaq_gui.utils import QLED
from pymodaq_gui.utils.file_io import select_file
from pymodaq_gui.parameter import ioxml
from pymodaq_gui.parameter import utils as putils
from pymodaq_gui.config_saver_loader import ConfigSaverLoader
from pymodaq_gui.h5modules.saving import H5Saver
from pymodaq_gui.utils.widgets.spinbox import QSpinBox_ro

from pymodaq_plugins_beam_shaping.algorithms.factory import AlgorithmFactory
from pymodaq_plugins_beam_shaping.algorithms.algo_base import AlgoBase
from pymodaq_plugins_beam_shaping.algorithms.ini_phase import PhaseFactory, PhaseBase
from pymodaq_plugins_beam_shaping.algorithms.stopping import StoppingFactory, StoppingBase
from pymodaq_plugins_beam_shaping.algorithms.utils import ApplyMaskTo, LensSetup, CrossTalk, PhaseManipulation
from pymodaq_plugins_beam_shaping.utilities.masking import MaskType
from pymodaq_plugins_beam_shaping.field import Field
from pymodaq_plugins_beam_shaping import config as plugin_config
from pymodaq_plugins_beam_shaping.algorithms.algo_config import AlgoConfig
from pymodaq_plugins_beam_shaping.utilities.h5saving import ShapingSaver

from pymodaq_plugins_beam_shaping.utilities import sizing, regions

algo_factory = AlgorithmFactory()
phase_factory = PhaseFactory()
stopping_factory = StoppingFactory()
algo_config = AlgoConfig()

config = GlobalConfig()

class Actions(StrEnum):

    STEP = 'step'
    CONTINUOUS = 'continuous'
    STOP = 'stop'
    SAVE_CONTINUOUS = 'save_continuous'
    SHOW_SAVE_SETTINGS = 'show_saving'
    SHOW_SAVED_DATA = 'show_saved_data'
    RESET = 'reset_phase'
    COMPUTE_FFT = 'compute_fft'
    SHOW_DATA = 'show_data'


class AlgoApp(CustomApp):
    save_settings = True
    params = [

        {'title': 'Initial Phase', 'name': 'ini_phase_group', 'type': 'group',
         'children': [
             {'title': 'Phase type:', 'name': 'ini_phase_factory', 'type': 'list',
              'value': phase_factory.phases[0],
              'limits': phase_factory.phases},
             {'title': 'Phase Parameters', 'name': 'phase_params', 'type': 'group', 'children': []},
         ]},
        {'title': 'Stopping Criteria:', 'name': 'stopping', 'expanded': True, 'type': 'group',
         'children': [
             {'title': 'Stopping Type', 'name': 'stopping_type', 'type': 'list',
              'value': stopping_factory.stops[0],
              'limits': stopping_factory.stops},
         ]},

        {'title': 'Phase Manipulation:', 'name': 'phase_manipulation', 'type': 'group', 'expanded': False, 'children': [
            {'title': 'Apply:', 'name': 'apply', 'type': 'bool', 'value': plugin_config('algo', 'phase_manipulation', 'apply')},
            {'title': 'Value (Pi):', 'name': 'wrap_value', 'type': 'int',
             'value': plugin_config('algo', 'phase_manipulation', 'wrap_value')},
            {'title': 'SLM Dynamic (bits):', 'name': 'dynamic_value', 'type': 'list',
             'value': plugin_config('algo', 'phase_manipulation', 'dynamic_value')[0],
             'limits': plugin_config('algo', 'phase_manipulation', 'dynamic_value')},
        ]},
        {'title': 'Pixel Crosstalk:', 'name': 'crosstalk', 'type': 'group', 'expanded': False, 'children':[
            {'title': 'Apply:', 'name': 'apply', 'type': 'bool', 'value': plugin_config('algo', 'crosstalk', 'apply')},
            {'title': 'Value (pxl):', 'name': 'value', 'type': 'float',
             'value': plugin_config('algo', 'crosstalk', 'value')},
        ]},
        {'title': 'Target Masking', 'name': str(ApplyMaskTo.TARGET), 'type': 'group', 'children': [
            {'title': 'Apply Mask', 'name': 'apply_mask', 'type': 'bool', 'value': False},
            {'title': 'Mask Type', 'name': 'mask_type', 'type': 'list', 'value': str(MaskType.SQUARE),
             'limits': MaskType.names()},
            {'title': 'Slices (um):', 'name': 'slices', 'type': 'str', 'value': ''},
        ]},
        {'title': 'Intermediate Masking', 'name': str(ApplyMaskTo.INTERMEDIATE), 'type': 'group',
         'visible': False, 'children': [
            {'title': 'Apply Mask', 'name': 'apply_mask', 'type': 'bool', 'value': False},
            {'title': 'Mask Type', 'name': 'mask_type', 'type': 'list', 'value': str(MaskType.ELLIPTICAL),
             'limits': MaskType.names()},
            {'title': 'Slices (um):', 'name': 'slices', 'type': 'str', 'value': ''},
        ]}
    ]

    command_runner = QtCore.Signal(ThreadCommand)
    modulator_field_signal = QtCore.Signal(Field)
    algo_changed = QtCore.Signal(AlgoBase)
    fields_to_plot = QtCore.Signal(DataToExport)

    def __init__(self, dockarea, toolbar: QtWidgets.QToolBar=None):
        super().__init__(dockarea, toolbar=toolbar)
        self.runner_thread: QtCore.QThread = None

        self._algorithm: AlgoBase = None
        self._target_field: Field = None
        self._input_field: Field = None

        self.config_saver_loader = ConfigSaverLoader(self.settings, algo_config)

        self._current_data: DataToExport = None
        self._current_phase: np.ndarray = None  # cached phase to be used for subsequent optimizations

        self.setup_ui()

        self.enable_things(False)

        self.set_settings_values()

        for phase in phase_factory.phases:
            self.settings.child('ini_phase_group', 'phase_params').addChild(
                {'title': phase, 'name': phase, 'type': 'group',
                 'visible': self.settings['ini_phase_group', 'ini_phase_factory'] == phase,
                 'children': phase_factory.get_phase(phase).params})

        for stop in stopping_factory.stops:
            self.settings.child('stopping').addChild(
                {'title': stop, 'name': stop, 'type': 'group',
                 'visible': self.settings['stopping', 'stopping_type'] == stop,
                 'children': stopping_factory.get_stop_class(stop).params})

        self._module_and_data_saver: ShapingSaver = None
        self._h5saver: H5Saver = None


    @property
    def module_and_data_saver(self) -> ShapingSaver:
        return self._module_and_data_saver

    @module_and_data_saver.setter
    def module_and_data_saver(self, saver: ShapingSaver):
        self._module_and_data_saver = saver

    @property
    def h5saver(self) -> H5Saver:
        if self._h5saver is None:
            self._h5saver = H5Saver(save_type=SaveType.custom,
                                    backend=config('data', 'data_saving', 'backend')[0])
            for setting_name in ('save_type', 'save_2D', 'do_save', 'backend', 'custom_name', 'close_after_scan',):
                self._h5saver.settings.child(setting_name).hide()
        if self._h5saver.h5_file is None:
            self._h5saver.init_file(update_h5=True)
        if not self._h5saver.isopen():
            self._h5saver.init_file(addhoc_file_path=self._h5saver.settings['current_h5_file'])

        return self._h5saver

    @h5saver.setter
    def h5saver(self, h5saver_temp: H5Saver):
        self._h5saver = h5saver_temp

    def show_saver_settings(self, show: bool = True):
        if self._h5saver is not None:
            self.h5saver.settings_tree.setVisible(show)

    def show_continuous_data(self):
        if self._h5saver is not None:
            self.h5saver.show_file_content()

    def close_file(self):
        if self._h5saver is not None:
            self._h5saver.close_file()

    def setup_continuous_saving(self):
        """Configure the objects dealing with the continuous saving mode"""
        self.module_and_data_saver = ShapingSaver()
        self.module_and_data_saver.h5saver = self.h5saver

    def do_save_continuous(self, dosave: bool = True):
        if self._h5saver is None:
            self.setup_continuous_saving()
            self.h5saver.settings.child('base_name').setValue('Shaping')
            self.h5saver.settings.child('N_saved').show()

        self.h5saver.settings.child('do_save').setValue(dosave)

        if dosave:
            self.h5saver.settings.child('N_saved').setValue(0)
            self.module_and_data_saver.get_set_node(new=True)

    def save_continuous(self, dte: DataToExport):
        if self._h5saver is not None:
            self.module_and_data_saver.add_data(dte)
            self.h5saver.settings.child('N_saved').setValue(self.h5saver.settings['N_saved'] + 1)

    def quit_fun(self):
        super().quit_fun()
        self.close_file()

    def set_settings_values(self, param: Parameter = None):
        self.config_saver_loader.load_config(param)

    def save_algo_parameters(self):
        if self.save_settings:
            self.config_saver_loader.save_config()

    def save(self, fname: H5Saver | Path = None, where: str = '/RawData',
             group_name: str = 'Algorithm', title: str = ''):
        """ Save the fields, algorithm settings  into a hdf5 file

        Parameters
        ----------
        fname : Path
            If specified, add the field in the existing (or new) file. Otherwise open a File dialog to enter a file name
        where: str
            the node where the data will be saved
        """
        if fname is None:
            fname = select_file(start_path=config('data', 'data_saving','h5file', 'save_path'),
                                save=True, ext='h5')  # see daq_utils
        if fname != '':
            new_file = not fname.exists()


            settings_all = [parameter_to_xml_string(self.settings),
                            parameter_to_xml_string(self.algorithm.settings)]
            settings_str = b'<All_settings title="All Settings" type="group">'
            for set in settings_all:
                if len(settings_str + set) < 60000:
                    # size limit for any object header (including all the other attributes) is 64kb
                    settings_str += set
                else:
                    break
            settings_str += b'</All_settings>'

            with DataToExportSaver(fname, new_file=new_file, save_type=SaveType.custom) as saver:
                group = saver.add_data_group(where, DataDim.Data2D, title=title, settings_as_xml=settings_str,
                                             group_name=group_name)
                saver.add_data(group, self.algorithm.get_fields_to_plot())


    @property
    def current_phase(self) -> np.ndarray:
        """ cached phase to be used for subsequent optimizations """
        return self._current_phase

    @property
    def algorithm_combo(self) -> QtWidgets.QComboBox:
        return self.get_action('algorithms')

    @property
    def algorithm(self):
        if self._algorithm is None:
            self.set_algorithm()
        return self._algorithm

    def set_target_field(self, field: Field):
        if self._algorithm is not None:
            field = self._algorithm.scale_target_with_geometry(field)
            self._algorithm.set_target_field(field)

        self._target_field = field
        self.check_slices()

    def set_input_field(self, field: Field):

        modulator_field = field.deepcopy()

        if self._algorithm is not None:
            self._algorithm.set_modulator_field(modulator_field)
            self._algorithm.set_input_field(field)
            self.define_phase(force_reset=True)

        self._input_field = field

    def set_algorithm(self, algo_name: str = None):
        if algo_name is None:
            algo_name = self.algorithm_name
        try:
            if self._algorithm is not None:
                self._algorithm.quit()
                QtWidgets.QApplication.processEvents()

            self._algorithm: AlgoBase = \
                algo_factory.get_algorithm(algo_name)(
                    self,
                    CrossTalk(self.settings['crosstalk', 'apply'], self.settings['crosstalk', 'value'],),
                    PhaseManipulation(self.settings['phase_manipulation', 'apply'],
                                      self.settings['phase_manipulation', 'wrap_value'],
                                      int(self.settings['phase_manipulation', 'dynamic_value']),),
                )

            #change the chosen setup type (defined by the algo) in the config, to be used elsewhere
            setup_types: list[str] = plugin_config['setup', 'setup_type']
            setup_types.remove(self._algorithm.SETUP_TYPE.value)
            plugin_config['setup', 'setup_type'] = [self._algorithm.SETUP_TYPE.value] + setup_types
            plugin_config.save()

            self.settings.child('ini_phase_group').show(self._algorithm.INI_PHASE)
            self.settings.child(str(ApplyMaskTo.INTERMEDIATE)).show(self._algorithm.SETUP_TYPE == LensSetup.FourF)
            self.settings.child('stopping').show(self._algorithm.ITERATIVE == True)


            while True:
                child = self._algo_settings_widget.layout().takeAt(0)
                if not child:
                    break
                child.widget().deleteLater()
                QtWidgets.QApplication.processEvents()

            self._algo_settings_widget.layout().addWidget(self._algorithm.settings_tree)

            if self._input_field is not None:
                self.set_input_field(self._input_field)  # defines it first as the target axes depends
                # on the input beam size and resolution
                self.set_target_field(self._target_field)
            self.set_action_visible(Actions.CONTINUOUS, self._algorithm.ITERATIVE)
            self.set_action_visible(Actions.SAVE_CONTINUOUS, self._algorithm.ITERATIVE)
            self.set_action_visible(Actions.SHOW_SAVED_DATA, self._algorithm.ITERATIVE)
            self._iter_count_widget.setVisible(self._algorithm.ITERATIVE)

            self.config_saver_loader.base_path = [self._algorithm.ALGO_NAME]
            self.set_settings_values()
            self.check_slices()

            self.algo_changed.emit(self._algorithm)

        except ValueError as e:
            self.enable_things(False)

    @property
    def ini_phase_modulator(self) -> PhaseBase:
        return phase_factory.get_phase(
            self.settings['ini_phase_group', 'ini_phase_factory'])(
            self.settings.child('ini_phase_group', 'phase_params',
                                self.settings['ini_phase_group', 'ini_phase_factory']),
        self.algorithm)

    @property
    def ini_stopping_criteria(self) -> StoppingBase:
        return stopping_factory.get_stop_class(self.settings['stopping', 'stopping_type'])(
            self.settings.child('stopping', self.settings['stopping', 'stopping_type']))

    def update_counter(self, counter: int = 0):
        self._iter_count_widget.setValue(counter)

    def ini_algo(self):
        #self.set_action_enabled(Actions.CONTINUOUS, False)

        if self.is_action_checked('ini_algo'):
            self.get_action('algorithms').widget.setEnabled(False)
            #self.set_action_enabled('ini_algo', False)
            self.set_algorithm()

            self.runner_thread = QtCore.QThread()
            runner = AlgoRunner(self._algorithm)

            self.runner_thread.runner = runner
            runner.algo_output_signal.connect(self.process_output)
            runner.algo_stopped_signal.connect(self._algo_stopped)
            runner.algo_iter_count.connect(self.update_counter)
            runner.algo_status.connect(self.update_status)
            self.command_runner.connect(runner.queue_command)

            runner.moveToThread(self.runner_thread)

            self.runner_thread.start()

            self.define_phase(force_reset=True)
            self.compute_fft(update_plots=True)

            self.enable_things()

        else:
            self.get_action('algorithms').widget.setEnabled(True)
            if self.runner_thread is not None:
                self.command_runner.disconnect()
                if self.runner_thread.isRunning():
                    self.runner_thread.terminate()
                    while not self.runner_thread.isFinished():
                        QtCore.QThread.msleep(100)
                    self.runner_thread = None
            self.enable_things(enable=False)

    def _algo_stopped(self):
        if self.is_action_checked(Actions.CONTINUOUS):
            self.get_action(Actions.CONTINUOUS).trigger()

    def setup_docks_and_widgets(self):

        self.algo_area = self.dockarea

        self.docks['algo_settings'] = Dock('Algorithm Settings')

        self.settings_widget = QtWidgets.QWidget()
        self.settings_widget.setLayout(QtWidgets.QVBoxLayout())
        self.settings_widget.layout().setContentsMargins(0, 0, 0, 0)
        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        self.settings_widget.layout().addWidget(splitter)
        splitter.addWidget(self.settings_tree)

        self._algo_settings_widget = QtWidgets.QWidget()
        self._algo_settings_widget.setLayout(QtWidgets.QVBoxLayout())
        self._algo_settings_widget.layout().setContentsMargins(0, 0, 0, 0)
        splitter.addWidget(self._algo_settings_widget)

        self.settings_tree.setMinimumWidth(300)
        self.settings_tree.setMinimumHeight(150)

        self.docks['algo_settings'].addWidget(self.settings_widget)

        self.set_menu(QtWidgets.QMenu('Algorithm'))

        self._iter_count_widget = QSpinBox_ro()
        self._iter_count_widget.setToolTip('Current Iteration Number')

        self.statusbar.addPermanentWidget(self._iter_count_widget)

    def setup_menus_and_toolbars(self, menubar: QtWidgets.QMenuBar = None):
        pass  # actions auto-affected in setup_actions

    def setup_actions(self):
        self.add_widget('algorithms', QtWidgets.QComboBox,
                        tip='select the algorithm to compute the phase')
        self.get_action('algorithms').addItems(plugin_config('algo', 'default_algo'))
        self.get_action('algorithms').setCurrentText(plugin_config('algo', 'default_algo')[0])
        self.add_action('ini_algo', 'Init Algo', 'start', checkable=True,
                        icon_checked_color=self.get_theme().green,
                        auto_menu=False)
        self.add_action(Actions.RESET, 'Reset Phase', 'refresh',
                        tip="Reset the SLM phase to the initial one and the iterative algo counter (if any)")
        self.add_action(Actions.COMPUTE_FFT, 'Compute FFT', 'function', tip="Run a fft of the input phase")

        self.add_action(Actions.STEP, 'Step', 'looks_one', tip="Step a loop of the algorithm")
        self.add_action(Actions.CONTINUOUS, 'Continuous', 'repeat',
                        tip="Run continuously the algorithm",
                        checkable=True, icon_checked='repeat_on',
                        icon_checked_color=self.get_theme().green)
        self.add_action(Actions.SHOW_DATA, 'Continuous', 'bid_landscape',
                        tip='Display the data after each iteration', checkable=True, checked=True,
                        icon_checked_color=self.get_theme().green)
        self.add_action(Actions.SHOW_SAVE_SETTINGS, 'Show Saving Settings', 'account_tree',
                        tip="Show the Continuous Saving settings",
                        checkable=True, icon_checked_color=self.get_theme().green,
                        auto_toolbar=False)
        self.add_action(Actions.SAVE_CONTINUOUS, 'Save Continuous', 'save_clock',
                        tip="Save continuously the algorithm output",
                        checkable=True, icon_checked_color=self.get_theme().green)
        self.add_action(Actions.SHOW_SAVED_DATA, 'Show file content', 'folder_data',
                        tip='Browse the content of the current HDF5 file')
        self.set_action_visible(Actions.SHOW_SAVED_DATA, False)



    def connect_things(self):
        self.connect_action(Actions.STEP, self.compute_phase)
        self.connect_action(Actions.COMPUTE_FFT, lambda: self.compute_fft(update_plots=True))
        self.connect_action(Actions.CONTINUOUS, self.compute_phase_loop)
        self.connect_action('ini_algo', self.ini_algo)
        self.connect_action(Actions.RESET, lambda: self.define_phase(force_reset=True))
        self.connect_action('algorithms', slot=self.set_algorithm,
                            signal_name='currentTextChanged')
        self.connect_action(Actions.SAVE_CONTINUOUS, self.do_save_continuous)
        self.connect_action(Actions.SHOW_SAVE_SETTINGS, self.show_saver_settings)
        self.connect_action(Actions.SHOW_SAVED_DATA, self.show_continuous_data)


    def enable_things(self, enable=True, exclude: tuple[str]= ()):
        """ Given the initialization state of the chosen algorithm enable or not some actions and settings"""
        for action in (Actions.STEP, Actions.CONTINUOUS, Actions.RESET,
                       Actions.SAVE_CONTINUOUS, Actions.SHOW_SAVE_SETTINGS,
                       Actions.SHOW_SAVED_DATA):
            if action not in exclude:
                self.set_action_enabled(action, enable)
        self.set_action_enabled('algorithms', not enable)
        self.settings_widget.setEnabled(enable)

    @property
    def algorithms(self) -> list[str]:
        return algo_factory.algorithms

    @property
    def algorithm_name(self) -> str:
        """ get the current algorithm name """
        return self.get_action('algorithms').currentText()

    def define_phase(self, force_reset=False):
        if self._algorithm is not None and force_reset:
            if self._algorithm.INI_PHASE:
                self._current_phase = self.ini_phase_modulator.compute_phase()
                self.algorithm.define_input_phase(self._current_phase)
            self.command_runner.emit(ThreadCommand(Actions.RESET))

    def compute_fft(self, update_plots=True):
        if self._algorithm is not None:
            self._algorithm.compute_forward_fft(update_plots=update_plots)

    def compute_phase_loop(self):
        if self.is_action_checked(Actions.CONTINUOUS):
            self.command_runner.emit(ThreadCommand(Actions.CONTINUOUS,
                                                   attribute={'ini_phase': self._current_phase,
                                                              'stopping': self.ini_stopping_criteria}))
            for child in self.settings.child('stopping').children():
                child.setOpts(enabled=False)
        else:
            self.command_runner.emit(ThreadCommand(Actions.STOP))
            for child in self.settings.child('stopping').children():
                child.setOpts(enabled=True)

    def compute_phase(self):
        self.command_runner.emit(ThreadCommand(Actions.STEP, attribute=self._current_phase))
        self.set_action_enabled(Actions.CONTINUOUS, True)

    def apply_mask(self, apply_to: ApplyMaskTo) -> bool:
        return self.settings[str(apply_to), 'apply_mask']

    def get_plane_pixel_sizes(self, apply_to: ApplyMaskTo) -> Union[None, tuple]:
        """ Pixel sizes of the plane the mask applies to, None if not (yet) defined"""
        try:
            if str(apply_to) == str(ApplyMaskTo.INTERMEDIATE):
                return self._algorithm.intermediate_pixel_sizes
            return self._target_field.pixels_sizes
        except (AttributeError, ValueError, TypeError):
            return None

    def get_mask_region(self, apply_to: ApplyMaskTo) -> Union[None, tuple[slice, slice]]:
        """ Get the mask region as slices in real units (um), None if not defined"""
        return regions.parse_slices(self.settings[str(apply_to), 'slices'])

    def get_mask_as_slices(self, apply_to: ApplyMaskTo) -> Union[None, tuple[slice, slice]]:
        """ Get the mask region as slices of indexes to be used on the arrays of the corresponding plane"""
        if self.apply_mask(apply_to):
            region = self.get_mask_region(apply_to)
            pixel_sizes = self.get_plane_pixel_sizes(apply_to)
            if region is None or pixel_sizes is None:
                return None
            return regions.slices_to_indexes(region, pixel_sizes, sizing.get_effective_needed_field_size())
        else:
            return None

    def get_mask_type(self, apply_to: ApplyMaskTo) -> MaskType:
        return MaskType[self.settings[str(apply_to), 'mask_type']]

    def update_intermediate_slices(self, slices: tuple[slice, slice]):
        self.update_slices(ApplyMaskTo.INTERMEDIATE, slices)

    def update_target_slices(self, slices: tuple[slice, slice]):
        self.update_slices(ApplyMaskTo.TARGET, slices)

    def update_slices(self, apply_to: ApplyMaskTo, slices: tuple[slice, slice]):
        """ Set the mask region (slices in m) constrained to the effective area of the plane"""
        pixel_sizes = self.get_plane_pixel_sizes(apply_to)
        if pixel_sizes is not None:
            slices = regions.constrain_slices(slices, pixel_sizes)
        self.settings.child(str(apply_to), 'slices').setValue(regions.slices_to_str(slices))

    def check_slices(self):
        """ Set the default region (2/3 of the effective area, centered) if the current one is not valid"""
        for apply_to in (ApplyMaskTo.TARGET, ApplyMaskTo.INTERMEDIATE):
            pixel_sizes = self.get_plane_pixel_sizes(apply_to)
            if pixel_sizes is None:
                continue
            region = self.get_mask_region(apply_to)
            if region is None or not regions.are_slices_in_area(region, pixel_sizes):
                self.update_slices(apply_to, regions.default_slices(pixel_sizes))

    def value_changed(self, param: Parameter):
        for applied in ApplyMaskTo.values():
            if applied in putils.get_param_path(param) and self._algorithm is not None:
               self._algorithm.update_mask = True
        if param.name() == 'ini_phase_factory':
            for param_child in self.settings.child('ini_phase_group', 'phase_params').children():
                param_child.show(param.value() == param_child.name() and param_child.hasChildren())
        elif 'crosstalk' in putils.get_param_path(param):
            self._algorithm.crosstalk = CrossTalk(self.settings['crosstalk', 'apply'],
                                                  self.settings['crosstalk', 'value'], )
        elif 'phase_manipulation' in putils.get_param_path(param):
            self._algorithm.phase_manipulation = PhaseManipulation(self.settings['phase_manipulation', 'apply'],
                                                                   self.settings['phase_manipulation', 'wrap_value'], )
        elif param.name() == 'stopping_type':
            for param_child in self.settings.child('stopping').children():
                if param_child.name() != param.name():
                    param_child.show(param.value() == param_child.name() and param_child.hasChildren())

        self.save_algo_parameters()

    def algo_settings_changed(self):
        self.algo_changed.emit(self.algorithm)

    def process_output(self, dte: DataToExport):
        self._current_data = dte
        self._current_phase: np.ndarray = dte.get_data_from_full_name('modulator/phase')[0].copy()

        self.modulator_field_signal.emit(
            Field('modulator',
                  amplitude=dte.get_data_from_full_name('modulator/amplitude')[0],
                  phase=dte.get_data_from_full_name('modulator/phase')[0],
                  pixel_sizes=self._input_field.pixels_sizes))
        if self.is_action_checked(Actions.SAVE_CONTINUOUS):
            dte_to_save = DataToExport('tosave', data=[
                dte.get_data_from_full_name('modulator/phase').deepcopy(),
                dte.get_data_from_full_name('AlgoData/metrics').deepcopy(),
            ])
            self.save_continuous(dte_to_save)

        if self.is_action_checked(Actions.SHOW_DATA):
            self.fields_to_plot.emit(dte)


class AlgoRunner(QtCore.QObject):
    algo_output_signal = QtCore.Signal(DataToExport)
    algo_stopped_signal = QtCore.Signal()
    algo_iter_count = QtCore.Signal(int)
    algo_status = QtCore.Signal(str)

    def __init__(self, algo: AlgoBase):
        super().__init__()

        self.algo: AlgoBase = algo
        self.algo.do_things_after_init()
        self.running = False
        self._iter_index = 0

    def queue_command(self, command: ThreadCommand):
        """
        """
        if command.command == Actions.CONTINUOUS:
            self.algo_status.emit('Starting Continuous Algorithm')
            self.continuous_algo(**command.attribute)

        elif command.command == Actions.STEP:
            self.algo_status.emit('Stepping Algorithm')
            self.step_algo(command.attribute)

        elif command.command == Actions.STOP:
            self.algo_status.emit('Stopping Algorithm')
            self.running = False
            self.algo.stop()

        elif command.command == Actions.RESET:
            self.algo_status.emit('Resetting Phase and Counter')
            self._iter_index = 0

    def step_algo(self, ini_phase: np.ndarray = None):
        self._iter_index += 1
        self.algo_iter_count.emit(self._iter_index)
        self.algo.start()
        self.algo.compute_phase(do_step=True, ini_phase=ini_phase)
        self.algo_output_signal.emit(self.algo.get_fields_to_plot())
        self.algo.stop()
        self.algo_stopped_signal.emit()

    def continuous_algo(self, ini_phase: np.ndarray = None, stopping: StoppingBase = None):
        self.running = True
        stop_criteria = False
        if self.algo.MANUAL_LOOP:
            while self.running and not stop_criteria:
                self._iter_index += 1
                self.algo.start()
                self.algo.compute_phase(do_step=True, ini_phase=ini_phase)
                fields = self.algo.get_fields_to_plot()
                metrics = [data_array[0] for data_array in fields.get_data_from_name('metrics')]
                self.algo_output_signal.emit(fields)
                self.algo_iter_count.emit(self._iter_index)
                ini_phase = None
                QtWidgets.QApplication.processEvents()
                stop_criteria =  stopping.tell_stop(self._iter_index, metrics[0], metrics[1])
                if stop_criteria:
                    self.algo_status.emit('Stopping Algorithm due to stopping criteria')
                #QtCore.QThread.msleep(20)
        else:
            self._iter_index += 1
            self.algo_iter_count.emit(self._iter_index)
            self.algo.start()
            self.algo.compute_phase(do_step=False, ini_phase=ini_phase)  # the continuous run is handled by the algo itself. If possible
            #it should update the plots during the course of the initialization... See minimizer.py as an example
        self.algo.stop()
        self.algo_stopped_signal.emit()

def main():
    from pathlib import Path
    from pymodaq.utils.daq_utils import get_set_experiment_path
    from pymodaq_utils.math_utils import normalize_to

    from skimage.io import imread
    from skimage.color import rgb2gray
    from skimage.transform import rescale, resize

    from pymodaq_gui.qt_utils import mkQApp

    cheshire_cat_path = Path(__file__).parent.parent.joinpath(
        'resources/cheshirecat_rect.png')
    cemes_path = Path(__file__).parent.parent.joinpath(
        'resources/Cemes - Logo - Sigle - Blanc.png')

    app = mkQApp('Optical Shaping')

    win = QtWidgets.QMainWindow()
    area = DockArea()
    win.setCentralWidget(area)
    win.resize(1000, 500)
    win.setWindowTitle('PyMoDAQ Dashboard')
    win.show()

    # get amplitude
    target_intensity = imread(cheshire_cat_path)
    if len(target_intensity.shape) == 3:
        target_intensity = rgb2gray(target_intensity[..., 0:3])

    ratio = np.max(np.array((1080, 1920)) / np.array(target_intensity.shape))
    target_intensity = rescale(target_intensity, 1 * ratio)

    # get phase
    target_phase = imread(cemes_path)
    if len(target_phase.shape) == 3:
        target_phase = rgb2gray(target_phase[..., 0:3])

    ratio = np.max(np.array((1080, 1920)) / np.array(target_phase.shape))
    target_phase = rescale(target_phase, 1 * ratio)
    target_phase =  normalize_to(target_phase, 2* np.pi)

    algo_app = AlgoApp(area)
    target = Field(amplitude=np.sqrt(np.flipud(normalize_to(target_phase, 1))),
                   phase=np.flipud(target_phase))
    input = Field(amplitude=np.ones(target.shape))

    algo_app.set_target_field(target)
    algo_app.set_input_field(input)


    app.exec()


if __name__ == '__main__':
    main()
