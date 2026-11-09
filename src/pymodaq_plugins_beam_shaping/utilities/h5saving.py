from pathlib import Path
from typing import Callable, Union, List, Tuple, TYPE_CHECKING, Iterable

import xml.etree.ElementTree as ET

from pymodaq_data.h5modules.backends import GROUP, Node
from pymodaq_data.data import DataDim
import numpy as np

from pymodaq_data.h5modules.data_saving import (DataToExportEnlargeableSaver, DataToExport, DataToExportSaver,
                                                DataBundle)

from pymodaq.utils.h5modules.module_saving import ModuleSaver, GroupModuleType

from aenum import extend_enum

from pymodaq_data.h5modules.saving import SaveType
from pymodaq_utils.config import GlobalConfig

from pymodaq_gui.h5modules.saving import H5Saver

from pymodaq_plugins_beam_shaping.utilities.shaper import ModulatorType

if TYPE_CHECKING:
    from pymodaq_plugins_beam_shaping.field.field import Field

extend_enum(GroupModuleType, 'SHAPING')
# the sub groups of the group of a run saved at each step, each one by its own ModuleSaver (Fields, Metrics)
extend_enum(GroupModuleType, 'FIELDS')
extend_enum(GroupModuleType, 'METRICS')


class ShapingChildSaver(ModuleSaver):
    """ Saver of one sub group of the group of a run (the current fields, the metrics, the final fields...)

    As the savers of the control modules in the group of an extension: it owns its group, and the data saver adapted
    to it, enlargeable (with its own navigation axis) or not

    Parameters
    ----------
    group_type: GroupModuleType
        the type of the sub group (FIELDS, METRICS or FINAL), its name is derived from it
    enlargeable: bool
        the data are enlarged at each step along a navigation axis, otherwise saved once
    """
    def __init__(self, group_type: GroupModuleType, enlargeable: bool = True,
                 enl_axis_names=('step',), enl_axis_units=('',)):
        self.group_type = group_type
        self.title = group_type.name.capitalize()
        self.enlargeable = enlargeable
        self.enl_axis_names = enl_axis_names
        self.enl_axis_units = enl_axis_units
        self._module = self  # the title of the module is the one of the group
        self._module_group: GROUP = None
        self._h5saver: H5Saver = None
        self._datatoexport_saver: Union[DataToExportEnlargeableSaver, DataToExportSaver] = None

    def update_after_h5changed(self):
        if self.enlargeable:
            self._datatoexport_saver = DataToExportEnlargeableSaver(
                self.h5saver, self.enl_axis_names, self.enl_axis_units)
        else:
            self._datatoexport_saver = DataToExportSaver(self.h5saver)

    def _add_module(self, where: Union[Node, str] = None, metadata=None) -> Node:
        # not indexed: there is one per run, in the group of the run
        return self._h5saver.add_group(self.title, self.group_type.name, where, title=self.title,
                                       metadata=metadata or {})

    def add_data(self, where: Union[Node, str], dte: DataToExport,
                 axis_values: List[Union[float, np.ndarray]] = None, **kwargs):
        if self.enlargeable:
            self._datatoexport_saver.add_data(where, dte, axis_values=axis_values)
        else:
            self._datatoexport_saver.add_data(where, dte)


class ShapingSaver(ModuleSaver):
    """ Saver of the group of a run (ShapingXXX) with the savers of its sub groups: the fields and the metrics at each
    step (``fields``, ``metrics``, each enlarged along its own step axis), the fields saved once at the end (``Final``) and the
    input and target fields (``Input``, ``Target``)"""
    group_type = GroupModuleType.SHAPING

    def __init__(self, indexed: bool = True):
        """
        Parameters
        ----------
        indexed: bool
            the group of a run is named ShapingXXX with the next index (several runs in a file), otherwise Shaping
            (a file saved at once, as the Save of the extension)
        """
        self._module = None
        self._module_group: GROUP = None
        self._h5saver: H5Saver = None
        self.indexed = indexed

        self.enl_axis_names = ('step',)
        self.enl_axis_units = ('',)

        self.fields = ShapingChildSaver(GroupModuleType.FIELDS)
        self.metrics = ShapingChildSaver(GroupModuleType.METRICS)
        self.children = (self.fields, self.metrics)

    def update_after_h5changed(self):
        for child in self.children:
            child.h5saver = self.h5saver

    def get_set_node(self, where: Union[Node, str] = None, new=False,
                     settings_as_xml= None, common_data: DataToExport = None) -> GROUP:
        """Get the last group scan node

        Get the last Scan Group or create one
        get the last Scan Group if:
        * there is one already created
        * new is False

        Parameters
        ----------
        where: Union[Node, str]
            the path of a given node or the node itself
        new: bool
        settings_as_xml: optional, binary string to be added for new node
        common_data: optional, DataToExport
        Returns
        -------
        GROUP: the GROUP associated with this module
        """

        self._module_group = self.get_last_node(where)
        new = new or (self._module_group is None)
        if new:
            self._module_group = self._add_module(where, settings_as_xml=settings_as_xml)
        if common_data is not None:
            with DataToExportSaver(self._h5saver) as saver:
                saver.add_data(self._module_group, common_data)

        return self._module_group

    def _add_module(self, where=None, metadata=None, settings_as_xml='') -> Node:
        if metadata is None:
            metadata = {}
        if where is None:
            where = self._h5saver.raw_group


        if self.indexed:
            return self._h5saver.add_incremental_group(self.group_type, where, title='BeamShaping',
                                                       settings_as_xml=settings_as_xml, metadata=metadata)
        group = self._h5saver.add_group('Shaping', self.group_type.name, where, title='BeamShaping',
                                        metadata=metadata)
        self._h5saver.set_attr(group, 'settings', settings_as_xml)
        return group


    def _child_node(self, child: ShapingChildSaver) -> GROUP:
        """ The group of a child saver in the group of the current run, created at first use"""
        return child.get_set_node(self.get_last_node(self._h5saver.raw_group), name=child.title)

    def add_data(self, dte: DataToExport, axis_values: List[Union[float, np.ndarray]] = None,
                 child: ShapingChildSaver = None, **kwargs):
        """ Append data as the next step of the enlargeable arrays, in the sub group of ``child`` (by default
        the group of the run)

        Parameters
        ----------
        dte: DataToExport
            the data of this step
        axis_values: list of float
            the value of the 'step' axis for these data. By default, the number of data already saved
            (the N_saved setting of the H5Saver)
        child: ShapingChildSaver
            ``fields`` or ``metrics``: the sub group where to append the data, with its own step axis
        """
        if axis_values is None:
            axis_values = (self.h5saver.settings['N_saved'],)
        if child is None:
            raise ValueError('The data are saved in the sub group of a child saver: fields, metrics or final')
        child.add_data(self._child_node(child), dte, axis_values=axis_values)

    def add_group_data(self, dte: DataToExport, group_name: str, title: str = '', settings_as_xml=''):
        """ Save data once in the sub group ``group_name`` of the current run (as the control modules save theirs in the
        group of an extension), so that they share its settings and attributes, whatever is saved at each step

        The data and the group are saved by the code shared with the Save of the extension, see
        :func:`add_algorithm_group`"""
        saver = DataToExportSaver(self._h5saver)  # not as a context manager: it closes the file
        return add_algorithm_group(saver, dte, where=self.get_last_node(self._h5saver.raw_group),
                                   group_name=group_name, title=title or group_name, settings_as_xml=settings_as_xml)

    def add_final_data(self, dte: DataToExport):
        """ Save all the fields once in the ``Final`` sub group of the current run, e.g. at the end of a run"""
        return self.add_group_data(dte, 'Final', 'Final Fields')

    def add_loaded_field(self, field: 'Field', settings: Iterable = (), group_name: str = 'Input'):
        """ Save once a field (its amplitude and phase) in the sub group ``group_name`` of the current run, with the
        settings of the loader that produced it as the metadata of the group.

        The same group (``Input`` and ``Target``) and format as the save of the extension, shared code
        (:func:`add_field_group`): it can be read with :func:`load_field_from_h5`"""
        from pymodaq_data.h5modules.data_saving import DataSaverLoader
        from pymodaq_plugins_beam_shaping.field.h5 import add_field_group
        add_field_group(DataSaverLoader(self._h5saver), field, settings,  # not as a context manager: it closes the file
                        where=self.get_last_node(self._h5saver.raw_group), group_name=group_name,
                        title=f'{group_name} Field')

    def add_data_bundle(self, data: DataBundle):
        self.add_data(data.dte, axis_values=data.axis_values)


def add_algorithm_group(saver: DataToExportSaver, dte: DataToExport, where: Union[Node, str] = '/RawData',
                        group_name: str = 'Algorithm', title: str = '', settings_as_xml: Union[bytes, str] = ''):
    """ Add to an opened file a group holding the fields of an algorithm (the output of ``get_fields_to_plot``) and,
    optionally, the settings that produced them

    Shared by the Save of the extension (the ``Algorithm`` group) and by the saved runs (the ``Final`` group)"""
    group = saver.add_data_group(where, DataDim.Data2D, title=title, settings_as_xml=settings_as_xml,
                                 group_name=group_name)
    saver.add_data(group, dte)
    return group


VERSION_ATTRIBUTE = 'pymodaq_plugins_beam_shaping_version'


def add_plugin_version(saver) -> None:
    """ Write the version of this plugin in the attributes of the root of the file of a saver (an H5Saver, or a data
    saver holding one), next to the versions of PyMoDAQ that it writes itself"""
    from pymodaq_plugins_beam_shaping import __version__
    h5saver = saver if hasattr(saver, 'root') else (getattr(saver, 'h5saver', None) or saver._h5saver)
    h5saver.root().attrs[VERSION_ATTRIBUTE] = __version__


FIELDS_SAVED_BY_THE_APP = ('modulator/phase',)  # default fields of the continuous saving of the AlgoApp


def fields_of_modulator(modulator_type: ModulatorType) -> tuple[str, ...]:
    """ The field(s) actually sent to the shaper (the SLM field, not the modulator field which contains the input
    beam): the phase for a phase modulator, the amplitude pattern (binary hologram...) for an amplitude one, both
    otherwise"""
    modulator_type = ModulatorType(modulator_type)
    if modulator_type == ModulatorType.PHASE:
        return ('modulator/phase',)
    if modulator_type == ModulatorType.AMPLITUDE:
        return ('slm/amplitude',)
    return ('slm/amplitude', 'modulator/phase')


def select_data_to_save(dte: DataToExport, fields: Union[bool, Iterable[str]] = True,
                        metrics: bool = True) -> DataToExport:
    """ The part of the output of an algorithm (``AlgoBase.get_fields_to_plot``) to save at each iteration

    Parameters
    ----------
    dte: DataToExport
        the output of the algorithm: amplitude and phase of the output and modulator fields, the intensity of the
        intermediate one (4f setups) and the metrics
    fields: bool or iterable of str
        True: all the fields, False: none, or the full names of the ones to save ('modulator/phase',
        'output/amplitude', 'intermediate/intensity'...)
    metrics: bool
        save the metrics (fitness, efficiency...)
    """
    if fields is True:
        names = [dwa.get_full_name() for dwa in dte if dwa.name != 'metrics']
    elif fields is False or fields is None:
        names = []
    else:
        names = list(fields)
    if metrics:
        names.append(dte.get_data_from_name('metrics').get_full_name())
    return DataToExport('tosave', data=[dte.get_data_from_full_name(name).deepcopy() for name in names])


def algorithm_name_settings(algorithm_name: str):
    """ A settings group holding the name of the algorithm, to be saved with the other settings of a run (the
    settings of the algorithm do not tell which algorithm it is)"""
    from pyqtgraph.parametertree import Parameter
    return Parameter.create(name='algorithm', title='Algorithm', type='group', children=[
        {'name': 'name', 'title': 'Name', 'type': 'str', 'value': algorithm_name or ''}])


def configure_h5saver(h5saver: H5Saver, base_name: str = 'Shaping') -> H5Saver:
    """ Set a H5Saver as the continuous saving needs it: custom save type (a file named after the date and time, not
    a scan folder), file name starting with ``base_name``, the irrelevant settings hidden"""
    h5saver.save_type = SaveType.custom
    h5saver.settings.child('save_type').setValue(SaveType.custom.name)
    for setting_name in ('save_type', 'save_2D', 'do_save', 'backend', 'custom_name', 'close_after_scan',):
        h5saver.settings.child(setting_name).hide()
    h5saver.settings.child('base_name').setValue(base_name)
    h5saver.settings.child('N_saved').show()
    return h5saver


class RunSaver:
    """ Save the output of an algorithm at each iteration in a h5 file

    The format of the continuous saving of the AlgoApp: a group /RawData/ShapingXXX (ShapingSaver) per run, holding the
    saved data enlarged along a 'step' axis. Used by the AlgoApp and the algorithm playground script.

    Parameters
    ----------
    fields: bool or iterable of str
        the fields to save, see ``select_data_to_save``
    metrics: bool
        save the metrics
    h5saver_provider: callable
        optional, returns the H5Saver with its file open, when the file is managed elsewhere (the H5Manager of the
        AlgoApp). Without it, the saver creates its own H5Saver and file when first needed.
    """
    base_name = 'Shaping'

    def __init__(self, fields: Union[bool, Iterable[str]] = FIELDS_SAVED_BY_THE_APP, metrics: bool = True,
                 h5saver_provider: Callable[[], H5Saver] = None):
        self.fields = fields
        self.metrics = metrics
        self._h5saver_provider = h5saver_provider
        self._h5saver: H5Saver = None
        self._module_saver: ShapingSaver = None
        self._file_path: Path = None
        self._step = 0  # number of steps saved in the current run
        self._started = False  # a run has been started

    @property
    def is_set(self) -> bool:
        """ True once the saver has been used (file created or run started)"""
        return self._h5saver is not None or self._started

    def _new_h5saver(self) -> H5Saver:
        return configure_h5saver(
            H5Saver(save_type=SaveType.custom, backend=GlobalConfig()('data', 'data_saving', 'backend')[0]),
            self.base_name)

    @property
    def h5saver(self) -> H5Saver:
        """ The H5Saver, created and its file opened if needed: a new one in the PyMoDAQ data folder the first time, then
        the same one (closing the file does not start a new one). From the provider if one was given"""
        if self._h5saver_provider is not None:
            return self._h5saver_provider()
        if self._h5saver is None:
            self._h5saver = self._new_h5saver()
        if self._h5saver.h5_file is None or not self._h5saver.isopen():
            if self._file_path is None:  # a new file named after the date and time
                self._h5saver.init_file(update_h5=True)
                self._file_path = Path(self._h5saver.settings['current_h5_file'])
            else:  # reopened, the new data are added to it
                self._h5saver.init_file(addhoc_file_path=self._file_path)
        return self._h5saver

    @property
    def module_saver(self) -> ShapingSaver:
        if self._module_saver is None:
            self._module_saver = ShapingSaver()
            self._module_saver.h5saver = self.h5saver
        return self._module_saver

    @property
    def file_path(self) -> Union[Path, None]:
        """ The file the data are saved in, None before the first save"""
        if self._h5saver_provider is not None:
            return Path(self.h5saver.settings['current_h5_file']) if self.is_set else None
        return self._file_path

    def open_file(self, file_path: Union[str, Path]):
        """ Save in this file (created if needed, added to otherwise) instead of a new one in the data folder (not with
        a provider: the file is managed by it)"""
        if self._h5saver_provider is not None:
            raise RuntimeError('The file is managed by the provider of the H5Saver')
        self.close_file()
        self._file_path = Path(file_path)
        if self._h5saver is None:
            self._h5saver = self._new_h5saver()
        self._h5saver.init_file(addhoc_file_path=self._file_path)
        self._module_saver = None

    def start(self, settings_as_xml: bytes = None):
        """ A new 'ShapingXXX' group for a new run, the step counter reset"""
        self.finalize()
        self._module_saver = None  # a new one: the SWMR mode of the previous run is over
        self._started = True
        self._step = 0
        self.h5saver.settings.child('N_saved').setValue(0)
        add_plugin_version(self.h5saver)
        self.module_saver.get_set_node(new=True, settings_as_xml=settings_as_xml)

    def add(self, dte: DataToExport):
        """ Save the selected data of the output of an algorithm, as the next step, and flush the file"""
        data = select_data_to_save(dte, self.fields, self.metrics)
        if len(data) == 0:
            return
        # the metrics and the fields in their own sub group, each with its own step axis
        saver = self.module_saver
        for child, selected in ((saver.metrics, [dwa for dwa in data if dwa.name == 'metrics']),
                                (saver.fields, [dwa for dwa in data if dwa.name != 'metrics'])):
            if selected:
                self.module_saver.add_data(DataToExport('tosave', data=selected), axis_values=[self._step],
                                           child=child)
        self._step += 1
        self.h5saver.settings.child('N_saved').setValue(self._step)
        self.h5saver.flush()  # the content of the file is up to date at each step, e.g. to browse it while paused

    def add_loaded_fields(self, input_field: 'Field' = None, target_field: 'Field' = None,
                          input_settings: Iterable = (), target_settings: Iterable = ()):
        """ Save the input and the target fields of a run, each in its sub group (``Input``, ``Target``) of the group of
        the current run, with the settings of the loaders as the metadata of the group (as the extension does)"""
        for name, field, settings in (('Input', input_field, input_settings), ('Target', target_field, target_settings)):
            if field is not None:
                self.module_saver.add_loaded_field(field, settings, name)
        self.h5saver.flush()

    def add_final(self, dte: DataToExport):
        """ Save all the data of the output of an algorithm (every field, the metrics, the unreachable region...) once,
        in the ``Final`` sub group of the group of the current run, whatever the data saved at each step"""
        self.module_saver.add_final_data(dte.deepcopy())
        self.h5saver.flush()

    def finalize(self):
        """ Make the file consistent: end the SWMR mode if it was activated

        In SWMR mode the attributes of the enlargeable arrays (shape) and of the step axis (size) are not updated,
        they are set from the actual data when the file is closed and reopened. Call it when the saving is paused or
        stopped. The file stays open, and the next steps are appended to the same group.
        """
        h5saver = self.h5saver if self.is_set else None
        if h5saver is not None and h5saver.is_swmr_active:
            file_path = Path(h5saver.settings['current_h5_file'])
            h5saver.close_file()  # ends the SWMR mode
            h5saver.init_file(addhoc_file_path=file_path)  # reopened in append mode, with its nodes
            h5saver.reconcile_swmr_attrs()  # the shapes from the actual data
            for node in h5saver.walk_nodes('/'):  # and the sizes of the enlarged axes (not done by the above)
                if node.path.split('/')[-2:-1] == ['NavAxes'] and node.attrs['CLASS'] == 'EARRAY':
                    node.attrs['size'] = int(node.attrs['shape'][0])
            self._module_saver = None  # its nodes belong to the file before it was reopened

    def close_file(self):
        """ Close the file of its own H5Saver (with a provider, closing the file is the job of its manager)"""
        if self._h5saver is not None:
            self.finalize()
            self._h5saver.close_file()
