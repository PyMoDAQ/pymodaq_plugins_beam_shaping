import numpy as np
from qtpy import QtWidgets, QtCore
from pathlib import Path

from pymodaq_utils import utils as utils
from pymodaq_utils.logger import set_logger, get_module_name
from pymodaq_utils.config import GlobalConfig

from pymodaq_data.h5modules.data_saving import DataToExportSaver, DataLoader

from pymodaq_gui.messenger import messagebox
from pymodaq_gui.utils.shared_ui import MenuToolbarNames, SharedUI
from pymodaq_gui.config import get_set_layout_path
from pymodaq_gui.plotting.data_viewers.viewer2D import Viewer2D
from pymodaq_gui.plotting.data_viewers.viewer import ViewerDispatcher
from pymodaq_gui.utils.file_io import select_file
from pymodaq_gui import utils as gutils

from pymodaq_gui.utils.layout import save_layout_state, load_layout_state
from pymodaq_gui.parameter.ioxml import  xml_string_to_parameter

from pymodaq.utils.custom_ext import CustomExt
from pymodaq.utils.gui_utils.loader_utils import create_extension
from pymodaq.utils.data import DataToExport, DataCalculated, DataDim

from pymodaq_plugins_beam_shaping.utils import Config as PluginConfig
from pymodaq_plugins_beam_shaping.algorithms.algorithm_app import AlgoApp
from pymodaq_plugins_beam_shaping.field.field_loader_app import FieldLoaderApp, FieldLoader, Field, Q_
from pymodaq_plugins_beam_shaping.utilities.corrections import Correction
from pymodaq_plugins_beam_shaping.algorithms import AlgorithmFactory, AlgoBase
from pymodaq_plugins_beam_shaping.utilities import sizing
from pymodaq_plugins_beam_shaping.algorithms.utils import ApplyMaskTo, LensSetup
from pymodaq_plugins_beam_shaping.utilities import regions
from pymodaq_plugins_beam_shaping.utilities.calibrating import BeamShapingCalibration, Calibration
from pymodaq_plugins_beam_shaping.utilities.data import DataShaper
from pymodaq_plugins_beam_shaping.utilities.shaper import Shaper, ModulatorType, get_default_shaper, set_shaper

logger = set_logger(get_module_name(__file__))
layout_path = get_set_layout_path(user=True)

config = GlobalConfig()
plugin_config = PluginConfig()

algo_factory = AlgorithmFactory

EXTENSION_NAME = 'BeamShaping'
CLASS_NAME = 'BeamShaping'


def create_calibration_scan_app(dashboard) -> tuple[SharedUI, BeamShapingCalibration]:
    return create_extension(dashboard, BeamShapingCalibration)



class BeamShaping(CustomExt):
    command_runner = QtCore.Signal(utils.ThreadCommand)

    params = [
    ]

    def __init__(self, dockarea, dashboard):
        super().__init__(dockarea, dashboard, add_toolbar_break=False)

        self._target_field_loader: FieldLoaderApp = None
        self._input_field_loader: FieldLoaderApp = None

        self._modulator_field: Field = None
        self._correction_phase: DataCalculated = None
        self.metrics_viewer:  ViewerDispatcher = None
        self.modulator_viewers: ViewerDispatcher = None
        self.output_viewers: ViewerDispatcher = None
        self.intermediate_viewer: Viewer2D = None
        self.other_viewers: ViewerDispatcher = None

        self._shaper: Shaper = None

        self._algorithm: AlgoApp = None

        self._corrections: Correction = None

        self._calibration_shared_ui: QtWidgets.QMainWindow = None
        self._calibration_app: BeamShapingCalibration = None
        self.calibration : Calibration = Calibration()

        if self.modules_manager is not None and 'Shaper' in self.modules_manager.actuators_name:
            self._shaper_actuator = self.modules_manager.get_mod_from_name('Shaper', 'act')
        else:
            self._shaper_actuator = None

        self.setup_ui()

        self.do_things_after_init()

    def update_calibration(self):
        """ Create a new Calibration object

        Will be triggered if a new calib is done and changed the calibration file
        """
        self.calibration = Calibration()

    @property
    def input_field(self) -> Field:
        return self._input_field_loader.field

    @property
    def target_field(self) -> Field:
        return self._target_field_loader.field

    def do_things_after_init(self):
        self._input_field_loader.load_field()
        self._target_field_loader.load_field()

    def get_slm_slices(self) -> tuple[slice, slice]:
        """ get slices to apply to fields to get only pixels corresponding to the SLM"""
        shape = self.input_field.shape
        center = tuple(np.array(shape) // 2)
        size = self.slm_shape
        slices = (slice(max(0, center[0] - size[0] // 2), min(shape[0], center[0] + size[0] // 2)),
                  slice(max(0, center[1] - size[1] // 2), min(shape[1], center[1] + size[1] // 2)))
        return slices

    def do_things_after_experiment_set(self, experiment_name: str):
        super().do_things_after_experiment_set(experiment_name)
        self._disconnect_shaper_actuator()
        if self.modules_manager is not None and 'Shaper' in self.modules_manager.actuators_name:
            self._shaper_actuator = self.modules_manager.get_mod_from_name('Shaper', 'act')
            # the plugin tells what the shaper is when it is initialized, possibly after the experiment is set
            self._shaper_actuator.init_signal.connect(self._shaper_actuator_initialized)
        else:
            self._shaper_actuator = None
        self.update_from_shaper()

    def _disconnect_shaper_actuator(self):
        if self._shaper_actuator is not None:
            try:
                self._shaper_actuator.init_signal.disconnect(self._shaper_actuator_initialized)
            except (RuntimeError, TypeError):  # the module is gone or was not connected
                pass

    def _shaper_actuator_initialized(self, initialized: bool):
        if initialized:
            self.update_from_shaper()

    def update_modulator_field(self, field: Field):
        """ field contains here the modulator field"""

        if field is None:
            field = self.input_field

        self._modulator_field = field

        self.send_field_to_shaper(field,
                                  send_to_shaper=self.is_action_checked('send_algo_to_shaper'),
                                  with_corrections=self.is_action_checked('send_correc_to_shaper')
                                  )
    @property
    def shaper(self) -> Shaper:
        """The shaper as told by the Shaper actuator (once initialized), else the default one"""
        shaper = None
        if self._shaper_actuator is not None:
            shaper = Shaper.from_module(self._shaper_actuator)
        set_shaper(shaper)  # None: the default shaper
        if shaper is None:
            shaper = get_default_shaper()
        if (self._shaper is None or self._shaper.modulator_type != shaper.modulator_type) and \
                self.has_action('calibration'):
            self.set_action_visible('calibration', shaper.modulator_type == ModulatorType.PHASE)
        self._shaper = shaper
        return shaper

    def send_field_to_shaper(self, field: Field, send_to_shaper=True, with_corrections=True):
        """ Send the modulator field to the shaper depending on its modulation type

        Parameters
        ----------
        field: the field to send
        send_to_shaper: should we send it?
        with_corrections: should we add corrections, mostly for the field's phase
        """
        if self._shaper_actuator is not None:
            if self.shaper.modulator_type == ModulatorType.PHASE:
               self.send_phase_to_shaper(field, send_to_shaper, with_corrections)
            elif self.shaper.modulator_type == ModulatorType.AMPLITUDE:
                self.send_amplitude_to_shaper(field, send_to_shaper, with_corrections)
            else:
                self.send_phase_to_shaper(field, send_to_shaper, with_corrections)
                self.send_amplitude_to_shaper(field, send_to_shaper, with_corrections)

    def send_amplitude_to_shaper(self, field: Field, send_to_shaper=True, with_corrections=True):
        """ Send the modulator amplitude to the shaper

        Parameters
        ----------
        field: the field to send
        send_to_shaper: should we send it?
        with_corrections: should we add corrections, mostly for the field's phase
        """
        raise NotImplementedError

    def send_phase_to_shaper(self, field: Field, send_to_shaper=True, with_corrections=True):
        """ Send the modulator phase to the shaper

        Parameters
        ----------
        field: the field to send
        send_to_shaper: should we send it?
        with_corrections: should we add corrections
        """
        if self._shaper_actuator is not None:
            phase_to_send = 0.
            if send_to_shaper or with_corrections:
                if send_to_shaper:
                    phase_to_send = phase_to_send + field.phase_as_dwa()[0][tuple(self.get_slm_slices())]
                if with_corrections:
                    if self._correction_phase is not None:
                        phase_to_send = phase_to_send + self._correction_phase[0][tuple(self.get_slm_slices())]
                phase_to_send = sizing.unbin_to_real_slm(phase_to_send)
                if self.shaper.has_internal_calibration and self.shaper.use_internal_calibration:
                    phase_dwa = DataShaper('phase', data=[phase_to_send], as_grey_levels=False)
                    self._shaper_actuator.move_abs(phase_dwa)
                else:
                    try:
                        grey_dwa = self.calibration.calibrate_phase_to_grey(phase_to_send)
                        self._shaper_actuator.move_abs(grey_dwa)
                    except NameError as e:
                        messagebox(title='Calibration',
                                   text='Calibration File not found, cannot send the data to the Shaper. '
                                        'You should try to do either:\n'
                                        '* a new calibration first\n'
                                        f'* add a calibration file in: {self.calibration.get_calibration_filepath()}\n'
                                        '* use the shaper internal calibration if possible (see preferences).')
                        self.set_action_checked('send_algo_to_shaper', False)

    def save(self, fname: Path = None):
        """ Save fields: input, modulator, output, target into a hdf5 file together with settings/metadata

        Also save the phase sent to the SLM (cropped/unbined to the SLM shape)

        """
        if fname is None:
            fname = select_file(save=True, ext='h5beam', force_save_extension=True)
        if fname:

            correction_values = self._corrections.get_corrections()

            quad_phase_array = self._corrections.compute_focal_phase(correction_values.focal_length)
            linear_phase_array = self._corrections.compute_linear_phase(correction_values.tilt_x, correction_values.tilt_y)
            zernike_phase = self._corrections.compute_zernike_phase(correction_values.zernike)
            dte = DataToExport('SLM Phases')
            if self._modulator_field is not None:
                dte.append(self._modulator_field.phase_as_dwa(name='Algo Phase').isig[tuple(self.get_slm_slices())])

            dte.append(DataCalculated('Quadratic Phase', data=[quad_phase_array[tuple(self.get_slm_slices())]]),)
            dte.append(DataCalculated('Linear Phase', data=[linear_phase_array[tuple(self.get_slm_slices())]]),)
            dte.append(DataCalculated('Zernike Phase', data=[zernike_phase[tuple(self.get_slm_slices())]]))

            with DataToExportSaver(fname, metadata={'settings': plugin_config.to_xml_string()}) as h5saver:
                group = h5saver.add_data_group('/RawData', DataDim.Data2D, title='SLM Phases', group_name='SLM')
                h5saver.add_data(group, dte)

            self._input_field_loader.save_field(fname, where='/RawData', group_name='Input', title='Input Field')
            self._target_field_loader.save_field(fname, where='/RawData', group_name='Target', title='Target Field')

            self.algorithm.save(fname, where='/RawData', group_name='Algorithm', title='Algorithm')

    def load(self, fname: Path = None):
        if fname is None:
            fname = select_file(save=False, filter="BeamShaping files (*.h5beam *.h5)")

        if fname:
            dwa_modulator_amplitude = None
            dwa_modulator_phase = None
            dwa_target_amplitude = None
            dwa_target_phase = None
            dwa_input_amplitude = None
            dwa_input_phase = None

            with DataLoader(fname) as loader:
                algo_settings = xml_string_to_parameter(
                    loader.h5saver.get_node('/RawData/Algorithm/').attrs['settings'])
                target_settings = xml_string_to_parameter(
                    loader.h5saver.get_node('/RawData/Target/').attrs['settings'])
                input_settings = xml_string_to_parameter(
                    loader.h5saver.get_node('/RawData/Input/').attrs['settings'])

                for node in loader.walk_nodes('/RawData/Algorithm/Data2D/'):
                    if 'ARRAY' in node.attrs['CLASS']:
                        if node.attrs.get('origin', '') == 'modulator' and node.title == 'amplitude':
                            dwa_modulator_amplitude = loader.load_data(node.path)
                        elif node.attrs.get('origin', '') == 'modulator' and node.title == 'phase':
                            dwa_modulator_phase = loader.load_data(node.path)
                for node in loader.walk_nodes('/RawData/Target/'):
                    if 'ARRAY' in node.attrs['CLASS']:
                        if node.attrs.get('label', '') == 'Amplitude':
                            dwa_target_amplitude = loader.load_data(node.path)
                        elif node.attrs.get('label', '') == 'Phase':
                            dwa_target_phase = loader.load_data(node.path)
                for node in loader.walk_nodes('/RawData/Input/'):
                    if 'ARRAY' in node.attrs['CLASS']:
                        if node.attrs.get('label', '') == 'Amplitude':
                            dwa_input_amplitude = loader.load_data(node.path)
                        elif node.attrs.get('label', '') == 'Phase':
                            dwa_input_phase = loader.load_data(node.path)
            if dwa_modulator_amplitude.shape != sizing.get_effective_needed_field_size():
                messagebox(
                    title='Sizing Issue',
                    text='Could not load this file as the size is not coherent with the current sizing configuration')
                return

            modulator_field = Field('modulator',
                                    amplitude=dwa_modulator_amplitude[0],
                                    phase=dwa_modulator_phase[0],
                                    pixel_sizes=self.input_field.pixels_sizes,
                                    )
            input_field = Field('input',
                                amplitude=dwa_input_amplitude[0],
                                phase=dwa_input_phase[0],
                                pixel_sizes=self.input_field.pixels_sizes,
                                )
            target_field = Field('target',
                                 amplitude=dwa_target_amplitude[0],
                                 phase=dwa_target_phase[0],
                                 pixel_sizes=self.target_field.pixels_sizes,)

            with self.algorithm.settings.treeChangeBlocker():
                self.algorithm.settings.restoreState(
                    algo_settings.child(self.algorithm.settings_name).saveState())
            with self.algorithm.algorithm.settings.treeChangeBlocker():
                self.algorithm.algorithm.settings.restoreState(
                    algo_settings.child(self.algorithm.algorithm.settings_name).saveState())

            with self._target_field_loader.settings.treeChangeBlocker():
                self._target_field_loader.settings.restoreState(
                    target_settings.child(FieldLoaderApp.settings_name).saveState())
            with self._target_field_loader.loader.settings.treeChangeBlocker():
                self._target_field_loader.loader.settings.restoreState(
                    target_settings.child(FieldLoader.settings_name).saveState()
                )

            with self._input_field_loader.settings.treeChangeBlocker():
                self._input_field_loader.settings.restoreState(
                    input_settings.child(FieldLoaderApp.settings_name).saveState())
            with self._input_field_loader.loader.settings.treeChangeBlocker():
                self._input_field_loader.loader.settings.restoreState(
                    input_settings.child(FieldLoader.settings_name).saveState()
                )
            self.algorithm.set_input_field(input_field)
            self.algorithm.set_target_field(target_field)
            self.update_modulator_field(modulator_field)
            self.algorithm.algorithm.set_phase_in_modulator_plane(modulator_field.phase)
            self.algorithm.compute_fft()


    def update_correction_phase(self, dwa: DataCalculated):
        self._correction_phase = dwa
        self.update_modulator_field(self._modulator_field)

    @property
    def algorithm(self):
        return self._algorithm

    def setup_docks_and_widgets(self):
        """
        to be subclassed to setup the docks layout
        for instance:

        self.docks['ADock'] = gutils.Dock('ADock name)
        self.dockarea.addDock(self.docks['ADock"])
        self.docks['AnotherDock'] = gutils.Dock('AnotherDock name)
        self.dockarea.addDock(self.docks['AnotherDock"], 'bottom', self.docks['ADock"])

        See Also
        ########
        pyqtgraph.dockarea.Dock
        """
        self._target_dockarea = gutils.DockArea()
        self._target_field_loader = FieldLoaderApp(self._target_dockarea,
                                             modules_manager=self.modules_manager,
                                             title='Target Field Loader')
        self._target_field_loader.set_loader_in_settings(
            plugin_config('target', 'default_loader')[0])


        self._input_field_dockarea = gutils.DockArea()
        self._input_field_loader = FieldLoaderApp(self._input_field_dockarea,
                                                  title='Input Field Loader')
        self._input_field_loader.set_loader_in_settings(
            plugin_config('input', 'default_loader')[0])
        self._input_field_loader.updated_slm(self.shaper.name)
        self._input_field_loader.update_apply_mask(size=self.slm_shape, apply=True)

        self._corrections_dockarea = gutils.DockArea()
        self._corrections = Correction(self._corrections_dockarea,
                                       title='Phase Corrections')

        self.docks['output_field'] = gutils.Dock('Output Plane')
        self.docks['modulator_field'] = gutils.Dock('Modulator Plane')
        self.docks['metrics'] = gutils.Dock('Metrics')
        self.dockarea.addDock(self.docks['metrics'], 'left')
        self.dockarea.addDock(self.docks['modulator_field'], 'right')
        self.dockarea.addDock(self.docks['output_field'], 'bottom', self.docks['modulator_field'])


        metrics_area = gutils.DockArea()
        self.metrics_viewer = ViewerDispatcher(metrics_area, title='Metrics', direction='bottom')
        self.docks['metrics'].addWidget(metrics_area)

        self.target_widget = QtWidgets.QWidget()
        self.target_widget.setLayout(QtWidgets.QHBoxLayout())
        target_area = gutils.DockArea()
        self.target_viewers = ViewerDispatcher(target_area)
        self.target_widget.layout().addWidget(target_area)
        self.target_widget.setVisible(False)

        modulator_area = gutils.DockArea()
        self.modulator_viewers = ViewerDispatcher(modulator_area)
        self.docks['modulator_field'].addWidget(modulator_area)

        output_area = gutils.DockArea()
        self.output_viewers = ViewerDispatcher(output_area)
        self.docks['output_field'].addWidget(output_area)

        self.intermediate_widget = QtWidgets.QWidget()
        self.intermediate_viewer = Viewer2D(self.intermediate_widget, title='Intermediate Field Intensity')

        self.other_plots_widget = QtWidgets.QWidget()
        self.other_plots_widget.setLayout(QtWidgets.QVBoxLayout())
        other_area = gutils.DockArea()
        self.other_plots_widget.layout().addWidget(other_area)
        self.other_viewers = ViewerDispatcher(other_area, title='Other Plots')

    def setup_menus_and_toolbars(self, menubar=None):
        """

        """
        self.create_dashboard_toolbar(add_break=False)
        self.add_menu(MenuToolbarNames.FILE, MenuToolbarNames.FILE.capitalize(),
                      parent_menu=self.menubar)
        self.add_menu(MenuToolbarNames.TOOLS, MenuToolbarNames.TOOLS.capitalize(),
                      parent_menu=self.menubar)
        self.add_menu('shaping_tools', 'Shaping', parent_menu=MenuToolbarNames.TOOLS, )
        self.add_menu('calibration', 'Calibration', parent_menu='shaping_tools', )

    def setup_actions(self):
        logger.debug('Main actions')
        self.add_action('save', 'Save', 'file_save', 'Save Everything to a h5beam file',
                        menu=MenuToolbarNames.FILE, auto_menu=True)
        self.add_action('load', 'Load', 'file_open', 'Load fields from a h5beam file',
                        menu=MenuToolbarNames.FILE, auto_menu=True)
        self.toolbar.addSeparator()
        self.add_action('target', 'Target Selection', 'target',
                        'Open the Target FieldLoader window', checkable=True,
                        icon_checked_color=self.get_theme().green, menu='shaping_tools')
        self.add_action('input', 'Input Beam Selection', 'input',
                        'Open the InputBeam FieldLoader window', checkable=True,
                        icon_checked_color=self.get_theme().green, menu='shaping_tools')
        self.add_action('show_other_plots', 'Show Other Plots', 'visibility', checkable=True,
                        icon_checked='visibility_off', auto_toolbar=False)
        self.add_action('show_intermediate', 'Show Intermediate', 'visibility', checkable=True,
                        icon_checked='visibility_off', tip='Show Field intensity in intermediate plane',
                        menu='shaping_tools')

        self.toolbar.addSeparator()
        self.add_action('calibration', 'Calibration', 'equalizer',
                        tip='Perform a calibration of the SLM phase wrt the grey levels applied to it.',
                        checkable=True, menu='calibration',
                        enabled=self.shaper.modulator_type == ModulatorType.PHASE)
        self.add_action('show_calibration', 'ShowCalibration',
                        tip='Show the saved calibration curve if any...', auto_toolbar=False,
                        checkable=False, menu='calibration')

        self.add_action('corrections', 'Corrections', 'deblur',
                        tip='Open the Utility window with focal and Zernike correction',
                        checkable=True, menu='shaping_tools')
        self.toolbar.addSeparator()

        self.add_action('send_algo_to_shaper', 'Algo to shaper', 'grid_off',
                        icon_color=self.get_theme().red,
                        tip='Send calculated phase to the control module called *Shaper*',
                        checkable=True, toolbar='dashboard',
                        icon_checked='grid_on', icon_checked_color=self.get_theme().green,
                        menu='shaping_tools')

        self.add_action('send_correc_to_shaper', 'Correction to shaper', 'ink_eraser_off',
                        'Send correction phase to the control module called *Shaper*',
                        checkable=True, toolbar='dashboard',
                        icon_color=self.get_theme().red,
                        icon_checked='ink_eraser',
                        icon_checked_color=self.get_theme().green, menu='shaping_tools')

        self.add_action('add_corrections', 'Add Corrections', 'add_circle',
                        'Add Focal and Zernike polynomials as individual actuators in Dashboard',
                    toolbar='dashboard'
                        )

        logger.debug('actions set')

    def update_ui_from_algo(self, algo: AlgoBase):
        self.set_action_visible('show_intermediate', algo.SETUP_TYPE == LensSetup.FourF)
        self.show_set_target_roi_select()

    def plot_target(self, field: Field):
        self.target_viewers.show_data(DataToExport('Target', data=[
            field.intensity_as_dwa(),
            field.amplitude_as_dwa(),
            field.phase_as_dwa(),
        ]))


    def value_changed(self, param):
        """ to be subclassed for actions to perform when one of the param's value in self.settings is changed

        For instance:
        if param.name() == 'do_something':
            if param.value():
                print('Do something')
                self.settings.child('main_settings', 'something_done').setValue(False)

        Parameters
        ----------
        param: (Parameter) the parameter whose value just changed
        """
        ...

    def do_things_after_ui_setup(self):

        self._algorithm = AlgoApp(self.dockarea, toolbar=self.toolbar)
        self.dockarea.addDock(self._algorithm.docks['algo_settings'], 'left')
        self._algorithm.algo_changed.connect(self.update_target_loader_from_algo)
        self._algorithm.algo_changed.connect(self.update_ui_from_algo)
        self._algorithm.fields_to_plot.connect(self.plot_fields)

        self._algorithm.modulator_field_signal.connect(self.update_modulator_field)
        self._input_field_loader.field_signal.connect(self._algorithm.set_input_field)
        self._target_field_loader.field_signal.connect(self._algorithm.set_target_field)
        self._target_field_loader.field_signal.connect(lambda field: self.show_set_target_roi_select())

        self.set_menu(self._algorithm.menu)  #adds this to the menu dict (automatically added in the sharedUI)

        self.intermediate_viewer.roi_select_signal.connect(
            lambda roi: self._algorithm.update_intermediate_slices(regions.from_axis_units(roi.to_slices(as_integer=False))))
        self.show_set_target_roi_select()

        for viewer in (self._target_field_loader.amp_viewer, self._target_field_loader.phase_viewer):
            viewer.roi_select_signal.connect(lambda roi: self._algorithm.update_target_slices(regions.from_axis_units(roi.to_slices(as_integer=False))))

        if layout_path.joinpath('shaping.dock').is_file():
            try:
                load_layout_state(self.dockarea, layout_path.joinpath('shaping.dock'))
            except Exception as e:
                logger.warning(f'Could not restore layout state: {e}, deleting existing file')
                layout_path.joinpath('shaping.dock').unlink(missing_ok=True)



    def show_set_target_roi_select(self):
        slices = self._algorithm.get_mask_region(ApplyMaskTo.TARGET)
        if slices is None:
            return
        slices = regions.to_axis_units(slices)  # the ROI is in the units of the axes
        view = self._target_field_loader.amp_viewer.view
        view.set_action_checked('ROIselect', True)
        view.show_ROI_select()  # position and size are not taken into account by the viewer, set below
        view.ROIselect.setPos((slices[1].start, slices[0].start))
        view.ROIselect.setSize((slices[1].stop - slices[1].start, slices[0].stop - slices[0].start))

    def connect_things(self):
        logger.debug('connecting things')
        self.connect_action('show_other_plots', self.show_other_plots)
        self.connect_action('show_intermediate', self.show_intermediate_field)

        self.connect_action('target', self.show_target)
        self.connect_action('input', self.show_input)

        self._target_field_loader.field_signal.connect(self.plot_target)

        self.connect_action('show_calibration', lambda: self.calibration.show_calibration(True))

        self.connect_action('corrections', self.show_corrections)
        self._corrections.phase_changed.connect(self.update_correction_phase)
        if self.dashboard is not None:
            self.connect_action('add_corrections', self.add_corrections_actuators)

        self.connect_action('save', lambda: self.save())
        self.connect_action('load', lambda: self.load())
        self.config_changed.connect(self.do_things_after_config_changed)

        self.connect_action('calibration', self.open_calibration_app)

    def plot_fields(self, dte: DataToExport):
        metrics = dte.remove(dte.get_data_from_name('metrics'))
        dte_output = DataToExport('output', data=[
            dte.remove(dte.get_data_from_full_name(full_name)) for full_name in ['output/amplitude', 'output/phase']])
        dte_modulator = DataToExport('modulator', data=[
            dte.remove(dte.get_data_from_full_name(full_name)) for full_name in ['modulator/amplitude', 'modulator/phase']])
        try:
            dwa_intermediate = dte.remove(dte.get_data_from_full_name('intermediate/intensity'))
            self.intermediate_viewer.show_data(dwa_intermediate)
        except ValueError:  # means no intermediate data to plot
            pass
        self.modulator_viewers.show_data(dte_modulator)
        self.output_viewers.show_data(dte_output)
        self.metrics_viewer.show_data(metrics.split_as_dte('Metrics'))
        self.other_viewers.show_data(dte)

    def show_corrections(self, show=True):
        self._corrections_dockarea.setVisible(show)
        self._corrections_dockarea.closeEvent = lambda event: self.set_action_checked('corrections', False)

    def open_calibration_app(self, show=True):
        if self._calibration_app is None:
            self._calibration_shared_ui, self._calibration_app = create_calibration_scan_app(self.dashboard)
            self._calibration_app.scan_done_signal.connect(self.update_calibration)

        self._calibration_shared_ui.show(show)
        self._calibration_shared_ui.mainwindow.closeEvent = lambda event: self.set_action_checked('calibration', False)

    @property
    def slm_shape(self) -> tuple[int, int]:
        """ Get the shape of the configured SLM"""
        return sizing.get_effective_slm_size()

    def add_corrections_actuators(self):
        try:
            if plugin_config('corrections', 'actuators', 'focal_length'):
                self.dashboard.add_move_from_extension(f'FocalLength', "FocalLength",
                                                       self._corrections,
                                                       ui_identifier='Simple')
            for n in range(plugin_config('corrections', 'zernike', 'order_max')):
                if plugin_config('corrections', 'zernike', 'actuators', f'n{n}'):
                    for m in range(-n, n+2, 2):
                        self.dashboard.add_move_from_extension(f'Zernike {n}/{m}',
                                                               "Zernike",
                                                               self._corrections,
                                                               ui_identifier = 'Simple')
                        self.dashboard.actuators_modules[-1].axis_name = f'{n}{m}'
            self.set_action_enabled("add_corrections", False)

        except Exception as e:
            logger.exception('Could not create Corrections Actuators', exc_info=e)

    def update_target_loader_from_algo(self, algo: AlgoBase):
        pixel_size = Q_(sizing.get_effective_slm_pixel_size(), 'um')
        needed_pixel_size = sizing.get_effective_needed_field_size()

        field_size = (pixel_size * needed_pixel_size[0], pixel_size * needed_pixel_size[1])

        self._target_field_loader.update_pixels(algo.get_target_pixels_size(field_size))

    def do_things_after_config_changed(self):
        self.update_from_shaper()

    def update_from_shaper(self):
        """Read the shaper again (Shaper actuator or default one) and update what depends on it: the fields"""
        if self._input_field_loader is None or self._target_field_loader is None or self._algorithm is None:
            return  # the user interface is not set up yet
        self._shaper = None  # make sure to check if the shaper object should be reinit
        self._input_field_loader.updated_slm(self.shaper.name)
        self._input_field_loader.update_apply_mask(size=self.slm_shape, apply=True)
        self._input_field_loader.loader.load_field(notify=True)

        self._target_field_loader.updated_slm(self.shaper.name)
        self.update_target_loader_from_algo(self.algorithm.algorithm) #will reload the target

    def show_target(self, show=True):
        self._target_dockarea.setVisible(show)
        if show:
            self._target_dockarea.showMaximized()
        self._target_dockarea.closeEvent = lambda event: self.get_action('target').trigger()

    def show_input(self, show=True):
        self._input_field_dockarea.setVisible(show)
        if show:
            self._input_field_dockarea.showMaximized()
        self._input_field_dockarea.closeEvent = lambda event: self.get_action('input').trigger()

    def show_other_plots(self, show=True):
        self.other_plots_widget.setVisible(show)
        self.other_plots_widget.closeEvent = lambda event: self.get_action('show_other_plots').trigger()

    def show_intermediate_field(self, show=True):
        self.intermediate_widget.setVisible(show)
        if show:
            self.intermediate_widget.showMaximized()
        self.intermediate_widget.closeEvent = lambda event: self.get_action('show_intermediate').trigger()

    def _quit_fun(self) -> bool:

        save_layout_state(self.dockarea, file=layout_path.joinpath('shaping.dock'))

        self._input_field_dockarea.close()
        self._target_dockarea.close()
        self.intermediate_widget.close()
        self.other_plots_widget.close()
        QtWidgets.QApplication.processEvents()  # allows the dashboard modules to close properly
        return True


def main():
    import sys
    from pymodaq_gui.qt_utils import mkQApp
    from pymodaq.dashboard import load_dashboard_with_arguments
    from pymodaq.utils.gui_utils.loader_utils import create_extension

    app = mkQApp('BeamShaping')

    win, dashboard, _ = load_dashboard_with_arguments(show_dashboard=False, load_extension=False)
    win.mainwindow.setVisible(False)

    win_ext, ext = create_extension(dashboard, BeamShaping, show_extension=True)

    sys.exit(app.exec())


if __name__ == '__main__':
    main()



