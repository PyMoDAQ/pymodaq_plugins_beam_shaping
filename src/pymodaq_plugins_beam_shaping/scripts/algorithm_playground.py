"""Run a shaping algorithm outside of the application, to try it and look at its results

Meant to be executed in an IDE (Spyder, VS Code, PyCharm...) or in Jupyter: edit the values of the first cell then
run the cells one after the other. The cells are delimited by ``# %%``, so ``jupytext --to ipynb`` turns it into a
notebook.

Nothing here is tested on hardware, nor in the extension itself: the algorithm gets the same calls as in the
AlgoApp (input field, target field, optional masks, initial phase, then the computation) but through a minimal
stand-in for the application.

Qt: the parameters of algorithms and loaders are widgets, so a QApplication is needed. It is created here if missing,
no event loop is needed.
"""
import numpy as np

from pymodaq_plugins_beam_shaping.field.factory import LoaderFactory, register_loaders
from pymodaq_plugins_beam_shaping.algorithms.factory import AlgorithmFactory, register_algorithms
from pymodaq_plugins_beam_shaping.algorithms.utils import ApplyMaskTo
from pymodaq_plugins_beam_shaping.utilities import regions, sizing
from pymodaq_plugins_beam_shaping.utilities.masking import MaskType
from pymodaq_plugins_beam_shaping.utilities.shaper import Shaper, get_default_shaper
from pymodaq_data import Q_


# %% Settings: edit them
# Run the last cell of this file (or call list_available()) to see the available names and their parameters.

# The simulated shaper. None means the default one of the plugin configuration
SHAPER = None  # or Shaper('mine', width=1920, height=1080, pixel_size=8., has_internal_calibration=False,
#                         use_internal_calibration=False, modulator_type='phase')
# SHAPER_PARAMS = dict(width=512, height=512, pixel_size=8., modulator_type='phase') overrides the values of the default
SHAPER_PARAMS = dict()

# The algorithm, its parameters (dotted paths for the parameters in groups) and the number of iterations
ALGORITHM = 'Gerchberg-Saxton'
ALGORITHM_PARAMS = dict()  # e.g. for 'DMD Lee': dict(carrier_factor=1., remove_carrier=True)
N_ITERATIONS = 1  # only used by iterative algorithms
INITIAL_PHASE = 'zero'  # 'zero', 'random' or a 2D array of the shape of the fields

# The field entering the shaper: loader name and its parameters (see list_available())
INPUT_LOADER = 'ImageFiles'
INPUT_PARAMS = {'phase.load': False}  # only the amplitude of the default image

# The field to obtain after the shaper
TARGET_LOADER = 'LaguerreGaussian'
TARGET_PARAMS = dict()

# Masks, slices in um as ((start, stop) along y, (start, stop) along x), in the plane of the target or of the
# intermediate plane (4f setups). Only applied if the boolean is True
APPLY_TARGET_MASK = False
TARGET_MASK = ((-100., 100.), (-100., 100.))  # centered on the field, like in the app
TARGET_MASK_TYPE = 'elliptical'  # or 'square'
APPLY_INTERMEDIATE_MASK = False
INTERMEDIATE_MASK = ((-100., 100.), (-100., 100.))
INTERMEDIATE_MASK_TYPE = 'elliptical'

# Plots: matplotlib is used through the plot method of the data objects
SHOW_PLOTS = True


# %% Machinery, no need to edit
def ensure_qapp():
    from pymodaq_gui.qt_utils import mkQApp
    return mkQApp('AlgorithmPlayground')


def set_parameters(manager, values: dict):
    """ Set the values of the parameters of an algorithm or a loader, without using the Parameter objects.

    Keys are the names of the parameters, dotted for groups: ``'phase.load'``. Unknown names raise a KeyError
    listing the possible ones.
    """
    for key, value in values.items():
        path = key.split('.')
        try:
            manager.settings.child(*path).setValue(value)
        except Exception as e:
            raise KeyError(f'{key} is not a parameter of {type(manager).__name__}, '
                           f'possible ones: {parameter_names(manager)}') from e


def parameter_names(manager) -> list[str]:
    """ The dotted names of the parameters that can be set"""
    names = []

    def browse(param, prefix=''):
        for child in param.children():
            name = f'{prefix}{child.name()}'
            if child.hasChildren():
                browse(child, f'{name}.')
            else:
                names.append(name)

    browse(manager.settings)
    return names


def list_available():
    """ Print the algorithms and the loaders with their parameters"""
    ensure_qapp()
    register_loaders()
    register_algorithms()
    print('Algorithms (name: parameters)')
    for name in AlgorithmFactory.algorithms_registry:
        algo = AlgorithmFactory.get_algorithm(name)(parent=None)
        print(f'  {name}: {parameter_names(algo)}')
    print('Loaders (name: parameters)')
    for name, loader_class in LoaderFactory.loader_registry.items():
        loader = loader_class(parent=_HeadlessApp(get_default_shaper()))
        print(f'  {name}: {[n for n in parameter_names(loader) if n != "progress"]}')


class _HeadlessApp:
    """ The little the loaders and the algorithms ask to the application that owns them"""

    def __init__(self, shaper: Shaper):
        self.shaper = shaper
        self.algorithm = None
        self.masks = {str(ApplyMaskTo.TARGET): None, str(ApplyMaskTo.INTERMEDIATE): None}
        shape = sizing.get_effective_needed_field_size(shaper)
        pixel_size = sizing.get_effective_slm_pixel_size(shaper)
        from pymodaq_gui.parameter import ioxml  # noqa: F401 (make sure the parameter types are registered)
        from pyqtgraph.parametertree import Parameter
        self.settings = Parameter.create(name='settings', type='group', children=[
            {'name': 'needed_size', 'type': 'group', 'children': [
                {'name': 'height', 'type': 'int', 'value': int(shape[0])},
                {'name': 'width', 'type': 'int', 'value': int(shape[1])},
                {'name': 'pixel_height', 'type': 'float', 'value': pixel_size},
                {'name': 'pixel_width', 'type': 'float', 'value': pixel_size},
            ]}])

    # the masks: (slices in um, type) or None when not applied
    def apply_mask(self, apply_to) -> bool:
        return self.masks[str(apply_to)] is not None

    def get_mask_type(self, apply_to) -> MaskType:
        return MaskType(self.masks[str(apply_to)][1])

    def get_mask_as_slices(self, apply_to):
        if not self.apply_mask(apply_to):
            return None
        slices_um, _ = self.masks[str(apply_to)]
        if str(apply_to) == str(ApplyMaskTo.INTERMEDIATE):
            pixel_sizes = self.algorithm.intermediate_pixel_sizes
        else:
            pixel_sizes = self.algorithm._target_field.pixels_sizes
        shape = sizing.get_effective_needed_field_size(self.shaper)
        # like in the app the user gives the region around the center of the field: shift it to array coordinates
        pxl = regions.pixel_sizes_in_um(pixel_sizes)
        shifted = tuple(slice(_slice.start + shape[dim] * pxl[dim] / 2, _slice.stop + shape[dim] * pxl[dim] / 2)
                        for dim, _slice in enumerate(slices_um))
        return regions.slices_to_indexes(shifted, pixel_sizes, shape)

    def algo_settings_changed(self):
        pass

    def compute_phase_and_or_amplitude(self):
        pass  # the app recomputes when a parameter changes, here one calls run() again


def make_shaper() -> Shaper:
    shaper = SHAPER if SHAPER is not None else get_default_shaper()
    values = dict(shaper.__dict__)
    values.update(SHAPER_PARAMS)
    if 'pixel_size' in SHAPER_PARAMS and 'pixel_size_y' not in SHAPER_PARAMS:
        values['pixel_size_y'] = None
    return Shaper(**values)


def fit_to_shape(field, shape, pixel_sizes):
    """ Scale (keeping the aspect ratio) and pad with zeros a loaded field to the needed shape, as the loader app does"""
    from skimage.transform import rescale
    if tuple(field.shape) != tuple(shape):
        ratio = min(np.array(shape) / np.array(field.shape))
        amplitude = rescale(field.amplitude, ratio)
        phase = rescale(field.phase, ratio)
        pad = [((n - s) // 2, (n - s) - (n - s) // 2) for n, s in zip(shape, amplitude.shape)]
        field.amplitude = np.pad(amplitude, pad)
        field.phase = np.pad(phase, pad)
    field.calibrate_axes(pixel_sizes)
    return field


def load_field(loader_name: str, params: dict, app: _HeadlessApp):
    loader = LoaderFactory.get_loader(loader_name)(parent=app)
    set_parameters(loader, params)
    field = loader.load_field(notify=False)
    shape = sizing.get_effective_needed_field_size(app.shaper)
    pixel_size = Q_(sizing.get_effective_slm_pixel_size(app.shaper), 'um')
    return fit_to_shape(field, shape, (pixel_size, pixel_size))


def run(algorithm: str = None, n_iterations: int = None):
    """ Prepare and run the algorithm with the settings of the first cell, returns the algorithm"""
    ensure_qapp()
    register_loaders()
    register_algorithms()
    algorithm = ALGORITHM if algorithm is None else algorithm
    n_iterations = N_ITERATIONS if n_iterations is None else n_iterations

    shaper = make_shaper()
    app = _HeadlessApp(shaper)
    algo = AlgorithmFactory.get_algorithm(algorithm)(parent=None)
    algo.shaper = shaper
    algo.parent_app = app
    app.algorithm = algo
    set_parameters(algo, ALGORITHM_PARAMS)

    if not algo.supports(shaper.modulator_type):
        print(f'Warning: {algorithm} does not support {shaper.modulator_type} shapers')

    input_field = load_field(INPUT_LOADER, INPUT_PARAMS, app)
    algo.set_modulator_field(input_field.deepcopy())
    algo.set_input_field(input_field)

    target_field = algo.scale_target_with_geometry(load_field(TARGET_LOADER, TARGET_PARAMS, app))
    algo.set_target_field(target_field)

    if APPLY_TARGET_MASK:
        app.masks[str(ApplyMaskTo.TARGET)] = (tuple(slice(*s) for s in TARGET_MASK), TARGET_MASK_TYPE)
    if APPLY_INTERMEDIATE_MASK:
        app.masks[str(ApplyMaskTo.INTERMEDIATE)] = (tuple(slice(*s) for s in INTERMEDIATE_MASK),
                                                    INTERMEDIATE_MASK_TYPE)

    ini_phase = initial_phase(algo)
    algo.do_things_after_init()
    if algo.INI_PHASE:
        algo.define_input_phase(ini_phase)
    algo.compute_forward_fft(update_plots=False)

    for index in range(n_iterations if algo.ITERATIVE else 1):
        algo.start()
        algo.compute_phase_and_or_amplitude(do_step=True, ini_phase=ini_phase if index == 0 else None)
        algo.stop()
    return algo


def initial_phase(algo) -> np.ndarray:
    if isinstance(INITIAL_PHASE, np.ndarray):
        return INITIAL_PHASE
    if INITIAL_PHASE == 'random':
        return np.random.default_rng(0).uniform(-np.pi, np.pi, algo.shape)
    return np.zeros(algo.shape)


def plot(algo):
    """ Plot all the data of the algorithm (output, modulator, metrics, intermediate plane) with matplotlib"""
    from matplotlib import pyplot as plt
    figure = algo.get_fields_to_plot().plot('matplotlib')
    figure.set_size_inches(9, 14)  # one row per data, make room for the titles
    figure.tight_layout()
    if SHOW_PLOTS:
        plt.show()
    return figure


# %% Run
if __name__ == '__main__':
    algo = run()
    print(f'fitness = {algo.fitness:.4g}, efficiency = {algo.efficiency:.4g}')

# %% Plots
if __name__ == '__main__':
    plot(algo)

# %% What exists
if __name__ == '__main__':
    list_available()
