""" Base class and factory of the operations of the Field Tool

An operation is a class derived from FieldOperation, registered with ``@OperationFactory.register_operation()``,
declaring its settings in ``params`` and the values it finds (shown read only) in ``results``. In the Field Tool each
operation added to the chain is a group of the settings built by ``FieldOperation.make_group``.
"""
from abc import ABCMeta, abstractmethod, abstractproperty
from copy import deepcopy
from importlib import import_module
from pathlib import Path
from typing import Callable

import numpy as np

from pymodaq_utils.logger import set_logger, get_module_name
from pymodaq_gui.parameter import Parameter

from pymodaq_plugins_beam_shaping.field import Field

logger = set_logger(get_module_name(__file__))

CONTEXT_MENU = {'move_up': 'Move up', 'move_down': 'Move down', 'remove': 'Remove'}


class FieldOperation(metaclass=ABCMeta):
    """ An operation applied to a Field by the Field Tool

    Parameters
    ----------
    settings: Parameter
        the group of this operation in the settings of the Field Tool (see make_group)
    """
    OPERATION_NAME: str = abstractproperty()
    params: list[dict] = []
    results: list[dict] = []

    def __init__(self, settings: Parameter):
        self.settings = settings

    @classmethod
    def make_group(cls, name: str) -> dict:
        """ The settings of the operation as a group: enabled, its params, its results (read only)"""
        children = [{'title': 'Enabled', 'name': 'enabled', 'type': 'bool', 'value': True}]
        children += deepcopy(cls.params)
        if cls.results:
            children.append({'title': 'Results', 'name': 'results', 'type': 'group',
                             'children': [dict(result, readonly=True) for result in deepcopy(cls.results)]})
        return {'title': cls.OPERATION_NAME, 'name': name, 'type': 'group', 'context': dict(CONTEXT_MENU),
                'tip': 'Right click to move or remove this operation', 'children': children}

    @property
    def enabled(self) -> bool:
        return self.settings['enabled']

    def set_result(self, name: str, value):
        self.settings.child('results', name).setValue(value)

    @abstractmethod
    def apply(self, field: Field, support: np.ndarray) -> Field:
        """ Return a new Field, the operation applied to field

        Parameters
        ----------
        field: Field
            the field before the operation (not to be modified)
        support: np.ndarray of bool
            the pixels where the amplitude is above the threshold of the Field Tool
        """
        ...

    @staticmethod
    def new_field(field: Field, phase: np.ndarray = None, amplitude: np.ndarray = None) -> Field:
        """ A copy of field with a new phase and/or amplitude"""
        return Field(field.name,
                     amplitude=np.array(field.amplitude if amplitude is None else amplitude, dtype=float),
                     phase=np.array(field.phase if phase is None else phase, dtype=float),
                     pixel_sizes=field.pixels_sizes)


class OperationFactory:
    """The factory of the operations of the Field Tool"""

    operation_registry: dict[str, type[FieldOperation]] = {}

    @classmethod
    def register_operation(cls) -> Callable:
        """Class decorator registering a FieldOperation subclass by its OPERATION_NAME"""

        def inner_wrapper(wrapped_class: type[FieldOperation]) -> type[FieldOperation]:
            if wrapped_class.OPERATION_NAME not in cls.operation_registry:
                cls.operation_registry[wrapped_class.OPERATION_NAME] = wrapped_class
            return wrapped_class

        return inner_wrapper

    @classmethod
    def get_operation(cls, operation_name: str) -> type[FieldOperation]:
        if operation_name not in cls.operation_registry:
            raise ValueError(f'{operation_name} is not a supported Field operation.')
        return cls.operation_registry[operation_name]

    @classmethod
    def operations(cls) -> list[str]:
        return list(cls.operation_registry.keys())


def register_operations(parent_module_name: str = 'pymodaq_plugins_beam_shaping') -> list:
    """ Import the modules of the field.operations package so that their operations are registered"""
    modules = []
    package = import_module(f'{parent_module_name}.field.operations')
    for file in Path(package.__path__[0]).iterdir():
        if file.is_file() and file.suffix == '.py' and file.stem not in ('__init__', 'base', 'compute'):
            try:
                modules.append(import_module(f'.{file.stem}', package.__name__))
            except Exception as e:
                logger.warning(str(e))
    return modules
