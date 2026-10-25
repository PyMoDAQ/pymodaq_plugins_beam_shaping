from typing import Callable, List, Optional, Type, TypeVar
import re

from dataclasses import dataclass, fields, asdict
from pymodaq_data import Q_
try:
    from pymodaq_gui.managers.roi_viewer_manager import ROI2D_TYPES
except ImportError:  # pymodaq_gui < 5.3.x
    from pymodaq_gui.managers.roi_manager import ROI2D_TYPES
from pymodaq_gui.parameter import Parameter


@dataclass
class Element:
    index: int = -1

    def to_list(self) -> list[dict]:
        """ Return a list of dictionary to instantiate a Parameter """
        return [self.index_to_dict()] + self._to_list()

    def index_to_dict(self) -> dict:
        return {'title': 'Index', 'name': 'index', 'type': 'int', 'value': self.index}

    @classmethod
    def from_parameter(cls, param: Parameter):
        index = param['index']
        dict_param = cls._from_parameter(param)
        return cls(index, **dict_param)

    @classmethod
    def _from_parameter(cls, param: Parameter):
        return {}

    def _to_list(self) -> list[dict]:
        """ Return a list of dictionary to instantiate a Parameter

        To be optionally reimplemented by child class"""
        return []





ElementType = TypeVar("ElementType", bound=Element)


class ElementFactory:
    """The factory class for creating Optical elements"""

    _registry: dict = {}

    @classmethod
    def register_decorator(cls) -> Callable:
        """Class decorator method to register Elements class to the internal registry. Must be used as
        decorator above the definition of an ElementBase inherited class.

        This class must implement specific class methods in particular: serialize and deserialize
        """

        def inner_wrapper(wrapped_class: type[ElementType],) -> type[ElementType]:
            if wrapped_class.__name__ not in cls._registry:
                cls._registry[wrapped_class.__name__] = wrapped_class
            # Return wrapped_class
            return wrapped_class
        return inner_wrapper

    def get_elements(self) -> List[str]:
        return list(self._registry.keys())

    def get_element(self, name: str) -> ElementType:
        try:
            return self._registry[name]
        except KeyError:
            raise NotImplementedError(f"There is no known elemnet of type {name}") from KeyError

    def create_element(self, name: str, *args, **kwargs) -> Element:
        return self.get_element(name).__call__(*args, **kwargs)


@ElementFactory.register_decorator()
@dataclass
class Lens(Element):
    focal: Q_ = Q_(100, 'mm')

    def __post_init__(self, *args, **kwargs) -> None:
        assert self.index >= 0

    def _to_list(self) -> list[dict]:
        """ Return a list of dictionary to instantiate a Parameter """
        return [
            {'title': 'Focal:', 'name': 'focal', 'type': 'float', 'value': self.focal.m_as('mm'), 'suffix': 'mm'},
        ]

    @classmethod
    def _from_parameter(cls, param: Parameter):
        return {'focal': Q_(param['focal'], param.child('focal').opts['suffix'])}


@ElementFactory.register_decorator()
@dataclass
class Mask(Element):
    type: str = ROI2D_TYPES[0]
    types: tuple[str] = tuple(ROI2D_TYPES)
    center: tuple[Q_, Q_] = (Q_(0, 'mm'), Q_(0, 'mm'))
    size: tuple[Q_, Q_] = (Q_(1, 'mm'), Q_(1, 'mm'))

    def __post_init__(self, *args, **kwargs) -> None:
        assert self.type in self.types
        assert self.index >= 0

    def _to_list(self) -> list[dict]:
        """ Return a list of dictionary to instantiate a Parameter """
        return [
            {'title': 'Type:', 'name': 'type', 'type': 'list', 'value': self.type, 'limits': self.types},
            {'title': 'Center:', 'name': 'center', 'type': 'group', 'children': [
                {'title': 'X:', 'name': 'posx', 'type': 'float', 'value': self.center[0].m_as('mm'), 'suffix': 'mm'},
                {'title': 'Y:', 'name': 'posy', 'type': 'float', 'value': self.center[0].m_as('mm'), 'suffix': 'mm'},
            ]},
            {'title': 'Size:', 'name': 'size', 'type': 'group', 'children': [
                {'title': 'dX:', 'name': 'dx', 'type': 'float', 'value': self.size[0].m_as('mm'), 'suffix': 'mm'},
                {'title': 'dY:', 'name': 'dy', 'type': 'float', 'value': self.size[0].m_as('mm'), 'suffix': 'mm'},
            ]},
        ]

    @classmethod
    def _from_parameter(cls, param: Parameter):
        return  {'type': param['type'],
                 'center': (Q_(param['center', 'posx'], param.child('center', 'posx').opts['suffix']),
                            Q_(param['center', 'posy'], param.child('center', 'posy').opts['suffix'])),
                 'size': (Q_(param['size', 'dx'], param.child('size', 'dx').opts['suffix']),
                          Q_(param['size', 'dy'], param.child('size', 'dy').opts['suffix']))}


@ElementFactory.register_decorator()
@dataclass
class Target(Element):
    def __post_init__(self, *args, **kwargs) -> None:
        assert self.index >= 0


if __name__ == "__main__":
    factory = ElementFactory()
    print(factory.get_elements())

    for index, elt_name in enumerate(factory.get_elements()):
        elt_obj = factory.create_element(elt_name, index=index)
        print(elt_obj)

        param = Parameter.create(name='param', type='group', children=elt_obj.to_list())

        assert elt_obj == elt_obj.from_parameter(param)



