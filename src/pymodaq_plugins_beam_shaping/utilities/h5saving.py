from pathlib import Path
from typing import Callable, Union, List, Tuple, TYPE_CHECKING, Iterable

import xml.etree.ElementTree as ET

from pymodaq_data.h5modules.backends import GROUP, Node
import numpy as np

from pymodaq_data.h5modules.data_saving import (DataToExportEnlargeableSaver, DataToExport, DataToExportSaver,
                                                DataBundle)

from pymodaq.utils.h5modules.module_saving import ModuleSaver, GroupModuleType

from aenum import extend_enum

from pymodaq_data.h5modules.saving import SaveType
from pymodaq_utils.config import GlobalConfig

from pymodaq_gui.h5modules.saving import H5Saver

from pymodaq_plugins_beam_shaping.utilities.shaper import ModulatorType

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


    def add_data(self, dte: DataToExport, axis_values: List[Union[float, np.ndarray]] = None, **kwargs):
        """ Append data to the last group, as the next step of the enlargeable arrays

        Parameters
        ----------
        dte: DataToExport
            the data of this step
        axis_values: list of float
            the value of the 'step' axis for these data. By default, the number of data already saved
            (the N_saved setting of the H5Saver)
        """
        if axis_values is None:
            axis_values = (self.h5saver.settings['N_saved'],)
        self._datatoexport_saver.add_data(self.get_last_node(self._h5saver.raw_group), dte,
                                          axis_values=axis_values)

    def add_data_bundle(self, data: DataBundle):
        self.add_data(data.dte, axis_values=data.axis_values)


FIELDS_SAVED_BY_THE_APP = ('modulator/phase',)  # default fields of the continuous saving of the AlgoApp


def fields_of_modulator(modulator_type: ModulatorType) -> tuple[str, ...]:
    """ The modulator field(s) actually sent to the shaper: the phase for a phase modulator, the amplitude (binary
    hologram...) for an amplitude one, both otherwise"""
    modulator_type = ModulatorType(modulator_type)
    if modulator_type == ModulatorType.PHASE:
        return ('modulator/phase',)
    if modulator_type == ModulatorType.AMPLITUDE:
        return ('modulator/amplitude',)
    return ('modulator/amplitude', 'modulator/phase')


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
        self.module_saver.get_set_node(new=True, settings_as_xml=settings_as_xml)

    def add(self, dte: DataToExport):
        """ Save the selected data of the output of an algorithm, as the next step, and flush the file"""
        data = select_data_to_save(dte, self.fields, self.metrics)
        if len(data) == 0:
            return
        self.module_saver.add_data(data, axis_values=[self._step])
        self._step += 1
        self.h5saver.settings.child('N_saved').setValue(self._step)
        self.h5saver.flush()  # the content of the file is up to date at each step, e.g. to browse it while paused

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
