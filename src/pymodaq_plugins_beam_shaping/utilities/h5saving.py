from pathlib import Path
from typing import Callable, Union, List, Tuple, TYPE_CHECKING, Iterable

import xml.etree.ElementTree as ET

from pymodaq_data.h5modules.backends import GROUP, Node
from pymodaq_data.h5modules.data_saving import DataToExportEnlargeableSaver, DataToExport, DataToExportSaver

from pymodaq.utils.h5modules.module_saving import ModuleSaver, GroupModuleType

from aenum import extend_enum

from pymodaq_data.h5modules.saving import SaveType
from pymodaq_utils.config import GlobalConfig

from pymodaq_gui.h5modules.saving import H5Saver

extend_enum(GroupModuleType, 'SHAPING')


class ShapingSaver(ModuleSaver):
    group_type = GroupModuleType.SHAPING

    def __init__(self):
        self._module = None
        self._module_group: GROUP = None
        self._h5saver: H5Saver = None

        self.enl_axis_names = ('step',)
        self.enl_axis_units = ('',)

        self._datatoexport_saver: DataToExportEnlargeableSaver = None

    def update_after_h5changed(self):
        self._datatoexport_saver = DataToExportEnlargeableSaver(
            self.h5saver, self.enl_axis_names, self.enl_axis_units)

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


        return self._h5saver.add_incremental_group(self.group_type, where, title='BeamShaping',
                                                   settings_as_xml=settings_as_xml, metadata=metadata)


    def add_data(self, data: DataToExport):

        self._datatoexport_saver.add_data(self.get_last_node(self._h5saver.raw_group),
                                          data, axis_values=(self.h5saver.settings['N_saved'],))


FIELDS_SAVED_BY_THE_APP = ('modulator/phase',)  # the fields of the continuous saving of the AlgoApp


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


class ContinuousSaver:
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

    @property
    def is_set(self) -> bool:
        """ True once the saver has been used (file created or run started)"""
        return self._h5saver is not None or self._module_saver is not None

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
        """ A new 'BeamShaping' group for a new run, the step counter reset"""
        self.h5saver.settings.child('N_saved').setValue(0)
        self.module_saver.get_set_node(new=True, settings_as_xml=settings_as_xml)

    def add(self, dte: DataToExport):
        """ Save the selected data of the output of an algorithm, as the next step, and flush the file"""
        data = select_data_to_save(dte, self.fields, self.metrics)
        if len(data) == 0:
            return
        self.module_saver.add_data(data)
        self.h5saver.settings.child('N_saved').setValue(self.h5saver.settings['N_saved'] + 1)
        self.h5saver.flush()  # the content of the file is up to date at each step, e.g. to browse it while paused

    def close_file(self):
        """ Close the file of its own H5Saver (with a provider, closing the file is the job of its manager)"""
        if self._h5saver is not None:
            self._h5saver.close_file()
