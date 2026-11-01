""" Field Tool: apply a chain of operations to a field (remove a linear phase, Zernike modes, unwrap...) and show it
before, after and their difference.

The field comes from one of the planes of the BeamShaping algorithm (input, modulator, intermediate, target, output),
given as callables by the extension, or from a h5field file (the only source when the tool runs on its own, see main).
The tool only reads the field: nothing is sent back to the algorithm or to the shaper.
"""
from pathlib import Path
from typing import Callable, Optional

import numpy as np
from qtpy import QtWidgets, QtCore

from pymodaq_utils.config import GlobalConfig
from pymodaq_utils.logger import set_logger, get_module_name
from pymodaq_data import DataCalculated
from pymodaq_gui.managers.parameter_manager import Parameter
from pymodaq_gui.parameter import utils as putils
from pymodaq_gui.plotting.data_viewers.viewer2D import Viewer2D
from pymodaq_gui.utils.custom_app import CustomApp
from pymodaq_gui.utils.dock import DockArea, Dock
from pymodaq_gui.utils.file_io import select_file

from pymodaq_plugins_beam_shaping.field import Field
from pymodaq_plugins_beam_shaping.field.h5 import save_field_to_h5, load_field_from_h5
from pymodaq_plugins_beam_shaping.field.operations import OperationFactory, FieldOperation
from pymodaq_plugins_beam_shaping.field.operations import compute

logger = set_logger(get_module_name(__file__))

FILE_SOURCE = 'file'
ROWS = {'before': 'Before', 'after': 'After', 'difference': 'Difference (after - before)'}


class FieldToolApp(CustomApp):
    """ Apply a chain of operations to a field and show the field before, after and their difference

    Parameters
    ----------
    dockarea: DockArea
    field_sources: dict of callables
        name of the source (input, output...) -> callable returning the current Field of this source (or None)
    title: str
    """
    settings_name = 'FieldToolSettings'
    params = [
        {'title': 'Field', 'name': 'source', 'type': 'list', 'value': FILE_SOURCE, 'limits': [FILE_SOURCE],
         'tip': 'The field to work on: a plane of the algorithm, or a h5field file'},
        {'title': 'File', 'name': 'file', 'type': 'group', 'visible': True, 'children': [
            {'title': 'Path:', 'name': 'path', 'type': 'browsepath', 'value': '', 'filetype': True,
             'filter': 'Fields (*.h5field)'},
            {'title': 'Load:', 'name': 'load', 'type': 'bool_push', 'label': 'Load!', 'value': False},
        ]},
        {'title': 'Active', 'name': 'active', 'type': 'bool', 'value': True,
         'tip': 'Recompute each time the algorithm gives a new field'},
        {'title': 'Threshold (%)', 'name': 'threshold', 'type': 'float', 'value': 5., 'min': 0., 'max': 100.,
         'tip': 'The support of the field: where the amplitude is above this percentage of its maximum. The fits '
                'are done on it'},
        {'title': 'Mask phase', 'name': 'mask_phase', 'type': 'bool', 'value': True,
         'tip': 'Show the phases as 0 outside the support'},
        {'title': 'Save:', 'name': 'save', 'type': 'bool_push', 'label': 'Save Field!', 'value': False,
         'tip': 'Save the field after the operations (h5field, the chain of operations in the metadata)'},
        {'title': 'Operations', 'name': 'operations', 'type': 'group', 'addText': 'Add',
         'addList': [], 'children': [],
         'tip': 'Applied from top to bottom. Right click on an operation to move or remove it'},
    ]

    def __init__(self, dockarea: DockArea, field_sources: dict[str, Callable[[], Optional[Field]]] = None,
                 title: str = 'Field Tool'):
        self._field_sources: dict[str, Callable[[], Optional[Field]]] = dict(field_sources or {})
        self._operations: dict[str, FieldOperation] = {}
        self._operation_index = 0
        self._computing = False

        self.field_before: Optional[Field] = None
        self.field_after: Optional[Field] = None
        self.support: Optional[np.ndarray] = None
        self.viewers: dict[str, dict[str, Viewer2D]] = {}

        super().__init__(dockarea, title=title)
        self.setup_ui()

        operations = self.settings.child('operations')
        operations.setOpts(addList=OperationFactory.operations())
        operations.addNew = self.add_operation  # called by the Add button of the group

        source = self.settings.child('source')
        sources = list(self._field_sources.keys()) + [FILE_SOURCE]
        source.setLimits(sources)
        source.setValue(sources[0])
        self.settings.child('file').show(source.value() == FILE_SOURCE)

    # ------------------------------------------------------------------ UI
    def setup_docks_and_widgets(self):
        self.docks['field_tool'] = Dock('Field Tool')
        self.dockarea.addDock(self.docks['field_tool'])

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        self.settings_tree.setMinimumWidth(320)
        splitter.addWidget(self.settings_tree)

        rows_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        for row, row_title in ROWS.items():
            row_widget = QtWidgets.QWidget()
            row_widget.setLayout(QtWidgets.QVBoxLayout())
            row_widget.layout().setContentsMargins(0, 0, 0, 0)
            label = QtWidgets.QLabel(row_title)
            font = label.font()
            font.setBold(True)
            label.setFont(font)
            row_widget.layout().addWidget(label)
            viewers_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
            row_widget.layout().addWidget(viewers_splitter)
            self.viewers[row] = {}
            for part in ('amplitude', 'phase'):
                widget = QtWidgets.QWidget()
                self.viewers[row][part] = Viewer2D(widget, title=f'{row_title}: {part}')
                self.viewers[row][part].view.get_action('autolevels').trigger()  # the levels follow the data
                viewers_splitter.addWidget(widget)
            rows_splitter.addWidget(row_widget)
        splitter.addWidget(rows_splitter)
        splitter.setStretchFactor(1, 1)
        self.docks['field_tool'].addWidget(splitter)

    def setup_actions(self):
        ...

    def connect_things(self):
        ...

    # ------------------------------------------------------------------ sources
    @property
    def source(self) -> str:
        return self.settings['source']

    def get_source_field(self) -> Optional[Field]:
        """ A copy of the current field of the selected source (None if it has none)"""
        if self.source == FILE_SOURCE:
            path = self.settings['file', 'path']
            if path == '' or not Path(path).is_file():
                return None
            return load_field_from_h5(path, name='file')
        field = self._field_sources[self.source]()
        return None if field is None else field.deepcopy()

    def refresh(self):
        """ Get the field of the source again and recompute"""
        try:
            field = self.get_source_field()
        except Exception as e:
            logger.warning(f'Could not get the field {self.source}: {e}')
            field = None
        self.field_before = field
        self.compute()

    def update_from_source(self, *args):
        """ To connect to the signals telling that the fields of the algorithm changed: recompute if active, shown
        and working on a plane of the algorithm"""
        if self.settings['active'] and self.source != FILE_SOURCE and self.dockarea.isVisible():
            self.refresh()

    # ------------------------------------------------------------------ operations chain
    def add_operation(self, operation_name: str):
        """ Add an operation at the end of the chain"""
        operation_class = OperationFactory.get_operation(operation_name)
        name = f'op{self._operation_index:02d}'
        self._operation_index += 1
        group = self.settings.child('operations').addChild(operation_class.make_group(name))
        group.sigContextMenu.connect(self._operation_context_menu)
        self._operations[name] = operation_class(group)
        self.compute()
        return self._operations[name]

    def _operation_context_menu(self, param: Parameter, action: str):
        if action == 'move_up':
            self.move_operation(param.name(), -1)
        elif action == 'move_down':
            self.move_operation(param.name(), +1)
        elif action == 'remove':
            self.remove_operation(param.name())

    def move_operation(self, name: str, step: int):
        """ Move the operation up (step < 0) or down (step > 0) in the chain"""
        parent = self.settings.child('operations')
        group = parent.child(name)
        children = parent.children()
        index = children.index(group)
        new_index = int(np.clip(index + step, 0, len(children) - 1))
        if new_index != index:
            parent.insertChild(new_index, group)
            self.compute()

    def remove_operation(self, name: str):
        group = self.settings.child('operations', name)
        group.sigContextMenu.disconnect(self._operation_context_menu)
        group.remove()
        self._operations.pop(name, None)
        self.compute()

    @property
    def chain(self) -> list[FieldOperation]:
        """ The operations in the order of the settings"""
        return [self._operations[group.name()] for group in self.settings.child('operations').children()
                if group.name() in self._operations]

    # ------------------------------------------------------------------ computation
    def compute(self):
        """ Apply the enabled operations of the chain to field_before and show the result"""
        if self._computing:
            return
        self._computing = True
        try:
            if self.field_before is None:
                self.field_after = None
                self.support = None
            else:
                self.support = compute.support_mask(self.field_before.amplitude, self.settings['threshold'] / 100)
                field = self.field_before
                for operation in self.chain:
                    if operation.enabled:
                        try:
                            field = operation.apply(field, self.support)
                        except Exception as e:
                            logger.warning(f'The operation {operation.OPERATION_NAME} failed: {e}')
                self.field_after = field
        finally:
            self._computing = False
        self.show_fields()

    def get_difference(self) -> Optional[tuple[np.ndarray, np.ndarray]]:
        """ amplitude after - before, angle(E_after * conj(E_before))"""
        if self.field_before is None or self.field_after is None:
            return None
        return (self.field_after.amplitude - self.field_before.amplitude,
                compute.phase_difference(self.field_after.phase, self.field_before.phase))

    def show_fields(self):
        if self.field_before is None:
            return
        mask = self.support if self.settings['mask_phase'] else np.ones(self.field_before.shape, dtype=bool)
        difference = self.get_difference()
        arrays = {'before': (self.field_before.amplitude, self.field_before.phase),
                  'after': (self.field_after.amplitude, self.field_after.phase),
                  'difference': difference}
        axes = self.field_before.get_axes()
        for row, (amplitude, phase) in arrays.items():
            self.viewers[row]['amplitude'].show_data(
                DataCalculated(f'{row}_amplitude', data=[amplitude], axes=axes, labels=['Amplitude']))
            self.viewers[row]['phase'].show_data(
                DataCalculated(f'{row}_phase', data=[np.where(mask, phase, 0.)], axes=axes, labels=['Phase']))

    # ------------------------------------------------------------------ settings
    def value_changed(self, param: Parameter):
        path = putils.get_param_path(param)
        if 'results' in path or self._computing:
            return
        if param.name() == 'source':
            self.settings.child('file').show(param.value() == FILE_SOURCE)
            self.refresh()
        elif param.name() == 'load':
            if param.value():
                param.setValue(False)
                self.refresh()
        elif param.name() == 'path':
            self.refresh()
        elif param.name() == 'active':
            if param.value():
                self.refresh()
        elif param.name() == 'save':
            if param.value():
                param.setValue(False)
                self.save_field()
        elif param.name() in ('threshold', 'mask_phase') or 'operations' in path:
            self.compute()

    def save_field(self, fname: Path = None):
        """ Save the field after the operations, with the settings (chain of operations and results) as metadata"""
        if self.field_after is None:
            logger.warning('No field to save')
            return
        if fname is None:
            fname = select_file(start_path=GlobalConfig()('data', 'data_saving', 'h5file', 'save_path'),
                                save=True, ext='h5field', force_save_extension=True)
        if fname is not None and fname != '':
            save_field_to_h5(self.field_after, fname, settings=(self.settings,),
                             title=f'Field Tool on {self.source}')


def main():
    """ The Field Tool on its own, working on h5field files"""
    from pymodaq_gui.qt_utils import mkQApp
    from pymodaq_gui.utils.widgets.window import make_window
    from pymodaq_gui.utils.shared_ui import SharedUI

    app = mkQApp('Field Tool')
    win, area = make_window(title='Field Tool')
    shared_ui = SharedUI(win)
    field_tool = FieldToolApp(area)
    shared_ui.affect_application(field_tool)
    app.exec()


if __name__ == '__main__':
    main()
