"""Helpers to run a shaping algorithm outside of the application, used by scripts/algorithm_playground.py

Nothing here is tested on hardware, nor in the extension itself: the algorithm gets the same calls as in the AlgoApp
(input field, target field, optional masks, initial phase, then the computation) but through a minimal stand-in for
the application (:class:`HeadlessApp`).

Qt: the parameters of algorithms and loaders are widgets, so a QApplication is needed (:func:`ensure_qapp`). No event
loop is needed.
"""
import importlib
import sys
from typing import Optional, Union

import numpy as np

from pymodaq_plugins_beam_shaping.field.factory import LoaderFactory, register_loaders
from pymodaq_plugins_beam_shaping.algorithms.factory import AlgorithmFactory, register_algorithms
from pymodaq_plugins_beam_shaping.algorithms.utils import ApplyMaskTo
from pymodaq_plugins_beam_shaping.utilities import regions, sizing
from pymodaq_plugins_beam_shaping.utilities.masking import MaskType
from pymodaq_plugins_beam_shaping.utilities.shaper import Shaper, get_default_shaper
from pymodaq_data import Q_


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
        loader = loader_class(parent=HeadlessApp(get_default_shaper()))
        print(f'  {name}: {[n for n in parameter_names(loader) if n != "progress"]}')


class HeadlessApp:
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


def make_shaper(shaper: Optional[Shaper] = None, **overrides) -> Shaper:
    """ The given shaper (default: the one of the plugin configuration) with some values overridden, e.g.
    ``make_shaper(width=512, height=512, pixel_size=8., modulator_type='amplitude')``"""
    shaper = shaper if shaper is not None else get_default_shaper()
    values = dict(shaper.__dict__)
    values.update(overrides)
    if 'pixel_size' in overrides and 'pixel_size_y' not in overrides:
        values['pixel_size_y'] = None
    return Shaper(**values)


def reload_algorithm(name: str) -> type:
    """ Reload the module of an algorithm, to take into account the changes made in its code, and return its class

    The factory keeps the first class registered under a name, so the entry is removed before the module is reloaded
    and registers the new class again. Only the module defining the algorithm is reloaded, not the modules it imports
    (a base class defined elsewhere, for instance).

    Also use it for the first run: it makes sure that the algorithms are registered.
    """
    ensure_qapp()
    register_algorithms()
    algo_class = AlgorithmFactory.get_algorithm(name)
    del AlgorithmFactory.algorithms_registry[name]
    try:
        importlib.reload(sys.modules[algo_class.__module__])
    except Exception:
        AlgorithmFactory.algorithms_registry[name] = algo_class  # keep the previous version usable
        raise
    return AlgorithmFactory.get_algorithm(name)


def create_algorithm(algo_class: type, app: HeadlessApp, params: Optional[dict] = None):
    """ Create the algorithm (the class given by :func:`reload_algorithm`) for the shaper of the app, with its
    parameters set"""
    algo = algo_class(parent=None)
    algo.shaper = app.shaper
    algo.parent_app = app
    app.algorithm = algo
    set_parameters(algo, params or {})
    if not algo.supports(app.shaper.modulator_type):
        print(f'Warning: {algo_class.ALGO_NAME} does not support {app.shaper.modulator_type} shapers')
    return algo


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


def load_field(loader_name: str, params: Optional[dict], app: HeadlessApp):
    """ Load a field with a loader (see :func:`list_available`) and fit it to the size needed by the shaper"""
    ensure_qapp()
    register_loaders()
    loader = LoaderFactory.get_loader(loader_name)(parent=app)
    set_parameters(loader, params or {})
    field = loader.load_field(notify=False)
    shape = sizing.get_effective_needed_field_size(app.shaper)
    pixel_size = Q_(sizing.get_effective_slm_pixel_size(app.shaper), 'um')
    return fit_to_shape(field, shape, (pixel_size, pixel_size))


def set_fields(algo, input_field, target_field):
    """ Give the input and target fields to the algorithm, as the app does (the target is scaled by the algo)"""
    algo.set_modulator_field(input_field.deepcopy())
    algo.set_input_field(input_field)
    algo.set_target_field(algo.scale_target_with_geometry(target_field))


def set_mask(app: HeadlessApp, apply_to: ApplyMaskTo, slices_um: Optional[tuple], mask_type: str = 'elliptical'):
    """ Apply a mask given as ((start, stop) along y, (start, stop) along x) in um around the center of the field,
    None to remove it"""
    app.masks[str(apply_to)] = None if slices_um is None else (tuple(slice(*s) for s in slices_um), mask_type)


def initial_phase(algo, kind: Union[str, np.ndarray] = 'zero') -> np.ndarray:
    """ 'zero', 'random' or the given array"""
    if isinstance(kind, np.ndarray):
        return kind
    if kind == 'random':
        return np.random.default_rng(0).uniform(-np.pi, np.pi, algo.shape)
    return np.zeros(algo.shape)


def run_algorithm(algo, n_iterations: int = 1, ini_phase: Union[str, np.ndarray] = 'zero'):
    """ Run the algorithm (iterations only for the iterative ones), the results are in its fields"""
    phase = initial_phase(algo, ini_phase)
    algo.do_things_after_init()
    if algo.INI_PHASE:
        algo.define_input_phase(phase)
    algo.compute_forward_fft(update_plots=False)
    for index in range(n_iterations if algo.ITERATIVE else 1):
        algo.start()
        algo.compute_phase_and_or_amplitude(do_step=True, ini_phase=phase if index == 0 else None)
        algo.stop()
    return algo


def plot(algo, show: bool = True):
    """ Plot all the data of the algorithm (output, modulator, metrics, intermediate plane) with matplotlib"""
    from matplotlib import pyplot as plt
    figure = algo.get_fields_to_plot().plot('matplotlib')
    figure.set_size_inches(9, 14)  # one row per data, make room for the titles
    figure.tight_layout()
    if show:
        plt.show()
    return figure
