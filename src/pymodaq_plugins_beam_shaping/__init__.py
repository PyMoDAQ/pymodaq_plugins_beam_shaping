from pathlib import Path
from pymodaq_utils.logger import set_logger, get_module_name  # to be imported by other modules.
from pymodaq_utils.utils import get_version
from .utils import Config

__version__ = get_version(__package__)


config = Config()  # before field loader factory otherwise it will generate an error

from .field import LoaderFactory, register_loaders
from .algorithms.factory import AlgorithmFactory, register_algorithms
from .algorithms.ini_phase import register_phases
from .algorithms.stopping import register_stoppings

logger = set_logger(get_module_name(__file__))


logger.info('****************************************')
logger.info('Registering Optical Shaping algorithms')
register_algorithms()
logger.info('****************************************')

logger.info('****************************************')
logger.info('Registering Optical Shaping ini phases')
register_phases()
logger.info('****************************************')


logger.info('****************************************')
logger.info('Registering Optical Shaping stopping criteria')
register_stoppings()
logger.info('****************************************')


logger.info('****************************************')
logger.info('Registering Optical Shaping Field loaders')
register_loaders()
logger.info('****************************************')
logger.info('****************************************')

algo_factory = AlgorithmFactory()
loader_factory = LoaderFactory()

#check the presence of all registered algorithm in the config
registered_algorithms = algo_factory.algorithms
config_algorithms = config('algo', 'default_algo')

# add registered in config list
for algo in registered_algorithms:
    if algo not in config_algorithms:
        config_algorithms.append(algo)

#remove those that are not in registered
for algo in config_algorithms[:]:
    if algo not in registered_algorithms:
        config_algorithms.remove(algo)
config['algo', 'default_algo'] = config_algorithms

#check the presence of all registered field loader in the config
registered_field_loader = loader_factory.field_loaders
config_target_field_loader = config('target', 'default_loader')
config_input_field_loader = config('input', 'default_loader')

# add registered in config list
for loader in registered_field_loader:
    if loader not in config_target_field_loader:
        config_target_field_loader.append(loader)
    if loader not in config_input_field_loader:
        config_input_field_loader.append(loader)

#remove those that are not in registered
for loader in config_input_field_loader[:]:
    if loader not in registered_field_loader:
        config_input_field_loader.remove(loader)
# remove those that are not in registered
for loader in config_target_field_loader[:]:
    if loader not in registered_field_loader:
        config_target_field_loader.remove(loader)

config['target', 'default_loader'] = config_target_field_loader
config['input', 'default_loader'] = config_input_field_loader
config.save()
