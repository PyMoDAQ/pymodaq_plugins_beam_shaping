from importlib import import_module
from importlib.metadata import entry_points
from pathlib import Path

from typing import Callable


from pymodaq_utils.logger import set_logger, get_module_name
from pymodaq_plugins_beam_shaping.algorithms.algo_base import AlgoBase

logger = set_logger(get_module_name(__file__))


ENTRY_POINT_GROUP = 'pymodaq_plugins_beam_shaping.algorithms'


def register_external_algorithms(group: str = ENTRY_POINT_GROUP):
    """ Load the modules declared by other packages in the entry point group of the algorithms

    A package providing algorithms declares, in the entry point group *pymodaq_plugins_beam_shaping.algorithms*, a
    module whose import registers its algorithms with the decorator *AlgorithmFactory.register_algorithm*. A package
    failing to load is reported in the log and ignored.
    """
    modules = []
    for entry_point in entry_points(group=group):
        try:
            modules.append(entry_point.load())
        except Exception as e:  # a broken third party package should not prevent BeamShaping to start
            logger.warning(f'Could not load the algorithms of {entry_point.value} ({entry_point.name}): {e!r}')
    return modules


def register_algorithms(parent_module_name: str = 'pymodaq_plugins_beam_shaping'):
    """ Browse modules containing algorithms for optical shaping and register them in the factory

    The algorithms provided by other packages through the entry point group *ENTRY_POINT_GROUP* are registered last.
    """
    algorithms = []
    try:
        algorithm_module = import_module(f'{parent_module_name}.algorithms.algorithms')

        algorithm_path = Path(algorithm_module.__path__[0])

        for file in algorithm_path.iterdir():
            if file.is_file() and 'py' in file.suffix and file.stem != '__init__':
                try:
                    algorithms.append(import_module(f'.{file.stem}', algorithm_module.__name__))
                except (ModuleNotFoundError, NotImplementedError) as e:
                    logger.warning(str(e))
    except ModuleNotFoundError as e:
        logger.warning(str(e))
    finally:
        algorithms.extend(register_external_algorithms())
        return algorithms


class AlgorithmFactory:
    """The factory class for creating Algorithm"""

    algorithms_registry = {}

    @classmethod
    def register_algorithm(cls) -> Callable:
        """Class decorator method to register algo class to the internal registry. Must be used as
        decorator above the definition of an AlgoBase inherited class.

        The Algorithm class must implement specific class attributes and methods

        returns:
            the exporter class
        """

        def inner_wrapper(wrapped_class: type[AlgoBase]) -> type[AlgoBase]:
            algo_name = wrapped_class.ALGO_NAME
            if algo_name is None:
                raise NotImplementedError('The reimplemented algorithm must have a valid ALGO_NAME string attribute')
            if wrapped_class.SETUP_TYPE is None:
                raise NotImplementedError('The reimplemented algorithm must have a valid SETUP_TYPE LensSetup enum'
                                          ' attribute')

            if algo_name not in cls.algorithms_registry:
                cls.algorithms_registry[algo_name] = wrapped_class
            # Return wrapped_class
            return wrapped_class

        # Return decorated function
        return inner_wrapper

    @classmethod
    def get_algorithm(cls, algo_name: str) -> type[AlgoBase]:
        """Factory command to get registered algorithms
        .
        This method gets the appropriate executor class from the registry

        Parameters
        ----------
        algo_name: str
            The name of the algorithm as specified during registration

        Returns
        -------
        an instance of the executor created
        """

        if algo_name not in cls.algorithms_registry:
            raise ValueError(f".{algo_name} is not a supported Algorithm.")

        return cls.algorithms_registry[algo_name]

    @property
    def algorithms(self):
        return list(self.algorithms_registry.keys())