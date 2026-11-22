"""Helpers to run a shaping algorithm outside of the application, used by scripts/algorithm_playground.py

Nothing here is tested on hardware, nor in the extension itself: the algorithm gets the same calls as in the AlgoApp
(input field, target field, optional masks, initial phase, then the computation) but through a minimal stand-in for
the application (:class:`HeadlessApp`).

Qt: the parameters of algorithms and loaders are widgets, so a QApplication is needed (:func:`ensure_qapp`). No event
loop is needed.
"""
import importlib
import sys
from pathlib import Path
from typing import Iterable, Optional, Union

import numpy as np

from pymodaq_plugins_beam_shaping.field.factory import LoaderFactory, register_loaders
from pymodaq_plugins_beam_shaping.algorithms.factory import AlgorithmFactory, register_algorithms
from pymodaq_plugins_beam_shaping.algorithms.ini_phase import PhaseFactory, register_phases
from pymodaq_plugins_beam_shaping.algorithms.compensation import CompensationFactory, Compensations, register_compensations
from pymodaq_plugins_beam_shaping.algorithms.utils import ApplyMaskTo
from pymodaq_plugins_beam_shaping.utilities import regions, sizing
from pymodaq_plugins_beam_shaping.utilities.masking import MaskType
from pymodaq_plugins_beam_shaping.utilities.h5saving import RunSaver, algorithm_name_settings
from pymodaq_plugins_beam_shaping.field.h5 import settings_to_xml
from pymodaq_plugins_beam_shaping.utilities.shaper import Shaper, get_default_shaper
from pymodaq_data import Q_


def ensure_qapp():
    from qtpy import QtWidgets
    app = QtWidgets.QApplication.instance()
    if app is not None:  # mkQApp applies the theme again at each call, which crashes after many calls
        return app
    from pymodaq_gui.qt_utils import mkQApp
    return mkQApp('AlgorithmPlayground')


def make_compensation(name: str = Compensations.DivideByInput, params: Optional[dict] = None):
    """ A compensation of the input beam (see :mod:`algorithms.compensations`) with its parameters set"""
    from pyqtgraph.parametertree import Parameter
    register_compensations()
    compensation_class = CompensationFactory.get_compensation(name)
    settings = Parameter.create(name=name, type='group', children=compensation_class.params)
    compensation = compensation_class(settings)
    set_parameters(compensation, params or {})  # names separated by '/' for the parameters in a group
    return compensation


def set_compensation(app, name: str = Compensations.DivideByInput, params: Optional[dict] = None):
    """ Choose the compensation of the input beam of the app (as the settings of the AlgoApp do): ``'NoCompensation'``
    or ``'DivideByInput'`` with the parameter ``min_input_level``"""
    app.compensation = make_compensation(name, params)


def set_compensate_input_phase(app, compensate: bool = True):
    """ Compensate the input phase in the target phase (as the checkbox of the AlgoApp): only used by the
    algorithms that control the output phase (ALGOTYPE not AMPLITUDE)"""
    app.compensate_input_phase = bool(compensate)


def set_parameters(manager, values: dict):
    """ Set the values of the parameters of an algorithm or a loader, without using the Parameter objects.

    Keys are the names of the parameters, separated by ``/`` for groups: ``'phase/load'``. Unknown names raise a KeyError
    listing the possible ones.
    """
    for key, value in values.items():
        path = key.split('/')
        try:
            manager.settings.child(*path).setValue(value)
        except Exception as e:
            raise KeyError(f'{key} is not a parameter of {type(manager).__name__}, '
                           f'possible ones: {parameter_names(manager)}') from e


def parameter_names(manager) -> list[str]:
    """ The names of the parameters, with ``/`` between groups, that can be set"""
    names = []

    def browse(param, prefix=''):
        for child in param.children():
            name = f'{prefix}{child.name()}'
            if child.hasChildren():
                browse(child, f'{name}/')
            else:
                names.append(name)

    browse(manager.settings)
    return names


def list_available():
    """ Print the algorithms, the initial phases and the loaders with their parameters"""
    ensure_qapp()
    register_loaders()
    register_algorithms()
    register_phases()
    print('Algorithms (name: parameters)')
    for name in AlgorithmFactory.algorithms_registry:
        algo = AlgorithmFactory.get_algorithm(name)(parent=None)
        print(f'  {name}: {parameter_names(algo)}')
    print('Initial phases (name: parameters)')
    for name, phase_class in PhaseFactory._registry.items():
        print(f'  {name}: {parameter_names(_phase_settings(phase_class))}')
    print('Loaders (name: parameters)')
    for name, loader_class in LoaderFactory.loader_registry.items():
        loader = loader_class(parent=HeadlessApp(get_default_shaper()))
        print(f'  {name}: {[n for n in parameter_names(loader) if n != "progress"]}')


class HeadlessApp:
    """ The little the loaders and the algorithms ask to the application that owns them"""

    def __init__(self, shaper: Shaper):
        self.shaper = shaper
        self.algorithm = None
        self.compensation = None  # the compensation of the input beam, see set_compensation (None: the default one)
        self.compensate_input_phase = True  # the target phase is corrected for the input phase, see set_compensate_input_phase
        self.loaded_fields = []  # (field, loader, shape before fitting) of the fields loaded with load_field
        self.field_loaders = {'input': None, 'target': None}  # the loaders of the fields given to the algorithm
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
        # as in the app, the region is given in the frame of the extension: its origin is the corner of the field
        return regions.slices_to_indexes(slices_um, pixel_sizes, shape)

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
    ini_shape = tuple(field.shape)
    shape = sizing.get_effective_needed_field_size(app.shaper)
    pixel_size = Q_(sizing.get_effective_slm_pixel_size(app.shaper), 'um')
    field = fit_to_shape(field, shape, (pixel_size, pixel_size))
    app.loaded_fields.append((field, loader, ini_shape))
    return field


def loader_settings(app: HeadlessApp, field, loader, ini_shape: tuple) -> list:
    """ The settings of a loader to save with the field it produced, laid out as the loader app of the extension does
    when it saves a field: all its settings (those of ``FieldLoaderApp.params``) and the ones of the loader

    The loader app does not exist here: its settings are created from the same definition, and set to what the script
    did (the loader, the size of the file and the needed size, the scaling to fit the field), the other ones (flips,
    smoothing, normalisation, masking, ROI) are not used by the script and keep their default value"""
    import copy
    from pyqtgraph.parametertree import Parameter
    from pymodaq_plugins_beam_shaping.field.field_loader_app import FieldLoaderApp
    loader_app = Parameter.create(name=FieldLoaderApp.settings_name, type='group',
                                  children=copy.deepcopy(FieldLoaderApp.params))
    needed = app.settings.child('needed_size')
    values = {('loader',): type(loader).LOADER_NAME,
              ('ini_size', 'height'): int(ini_shape[0]), ('ini_size', 'width'): int(ini_shape[1]),
              ('utils', 'sizing', 'height'): int(field.shape[0]), ('utils', 'sizing', 'width'): int(field.shape[1]),
              ('utils', 'sizing', 'scaling'): float(min(np.array(field.shape) / np.array(ini_shape)))}
    values.update({('needed_size', child.name()): child.value() for child in needed.children()})
    for path, value in values.items():
        loader_app.child(*path).setValue(value)
    return [loader_app, loader.settings]


def set_fields(algo, input_field, target_field):
    """ Give the input and target fields to the algorithm, as the app does (the target is scaled by the algo)"""
    app = algo.parent_app
    for role, field in (('input', input_field), ('target', target_field)):  # keep the loader of each, to save it
        app.field_loaders[role] = next(((field, loader, ini_shape) for loaded, loader, ini_shape in app.loaded_fields
                                        if loaded is field), None)
    algo.set_modulator_field(input_field.deepcopy())
    algo.set_input_field(input_field)
    algo.set_target_field(algo.scale_target_with_geometry(target_field))


def get_target_field(algo):
    """ The target as the algorithm uses it, after :func:`set_fields`: scaled to the target plane (its axes are the
    ones of the target plane) and normalized to the intensity of the input field"""
    return algo._target_field


def set_mask(app: HeadlessApp, apply_to: ApplyMaskTo, slices_um, mask_type: str = 'elliptical'):
    """ Apply a mask given by its region in um, None to remove it.

    The region is in the frame of the extension, where the origin is the corner of the field (the slices shown by the
    extension and by its mask settings can be pasted as is). The plots of this module are centered on the field, their
    outline of the mask is shifted accordingly.

    The region is given as the slices shown by the field loader and the extension, as text or not
    (``'(slice(-100, 100, None), slice(-50, 50, None))'``, along y then along x), so that they can be copied and pasted,
    or as ((start, stop) along y, (start, stop) along x)
    """
    slices = regions.as_slices(slices_um)
    app.masks[str(apply_to)] = None if slices is None else (slices, mask_type)


def mask_to_str(slices_um) -> str:
    """ The region of a mask as text, in the form of the field loader and the extension, to copy it"""
    return regions.slices_to_str(regions.as_slices(slices_um))


def default_mask(algo, apply_to: ApplyMaskTo, fraction: float = 2 / 3) -> tuple:
    """ The default region of a mask, as in the extension: centered and covering 2/3 of the effective area of the SLM
    in the plane (target or intermediate), given as slices along y then along x in um in the frame of the extension
    (origin at the corner of the field), rounded to the um, as shown by the extension"""
    if str(apply_to) == str(ApplyMaskTo.INTERMEDIATE):
        pixel_sizes = algo.intermediate_pixel_sizes
    else:
        pixel_sizes = algo._target_field.pixels_sizes
    slices = regions.default_slices(algo.shaper, pixel_sizes, fraction)
    return tuple(slice(round(_slice.start), round(_slice.stop)) for _slice in slices)


def _phase_settings(phase_class):
    """ The parameters of an initial phase, as the group the app gives it"""
    from pyqtgraph.parametertree import Parameter
    holder = type('PhaseSettings', (), {})()
    holder.settings = Parameter.create(name=phase_class.__name__, type='group',
                                       children=[dict(child) for child in phase_class.params])
    return holder


def initial_phase(algo, kind: Union[str, np.ndarray] = 'FlatPhase', params: Optional[dict] = None) -> np.ndarray:
    """ The initial phase computed by one of the phases of the factory, as in the app (see :func:`list_available`
    for the names and their parameters), or the given array"""
    if isinstance(kind, np.ndarray):
        return kind
    register_phases()
    phase_class = PhaseFactory.get_phase(kind)
    holder = _phase_settings(phase_class)
    set_parameters(holder, params or {})
    return phase_class(holder.settings, algo).compute_phase()


def run_settings(algo, app: HeadlessApp, ini_phase: Union[str, np.ndarray] = 'FlatPhase',
                 ini_phase_params: Optional[dict] = None, n_iterations: int = 1):
    """ The settings of a run, laid out as the settings of the extension (initial phase, masks) with the number of
    iterations, to be saved with the settings of the algorithm"""
    from pyqtgraph.parametertree import Parameter
    ini_phase_name = ini_phase if isinstance(ini_phase, str) else 'array'
    phase_children = []
    if isinstance(ini_phase, str) and algo.INI_PHASE:
        holder = _phase_settings(PhaseFactory.get_phase(ini_phase))
        set_parameters(holder, ini_phase_params or {})
        phase_children = [holder.settings]
    children = [
        {'name': 'n_iterations', 'title': 'Iterations', 'type': 'int', 'value': int(n_iterations)},
        {'name': 'ini_phase_group', 'title': 'Initial Phase', 'type': 'group', 'children': [
            {'name': 'ini_phase_factory', 'title': 'Phase type:', 'type': 'str', 'value': ini_phase_name},
            {'name': 'phase_params', 'title': 'Phase Parameters', 'type': 'group', 'children': phase_children}]}]
    for apply_to in (ApplyMaskTo.TARGET, ApplyMaskTo.INTERMEDIATE):
        mask = app.masks[str(apply_to)]
        children.append(
            {'name': str(apply_to), 'title': f'{str(apply_to).capitalize()} Masking', 'type': 'group', 'children': [
                {'name': 'apply_mask', 'title': 'Apply Mask', 'type': 'bool', 'value': mask is not None},
                {'name': 'mask_type', 'title': 'Mask Type', 'type': 'str',
                 'value': str(MaskType(mask[1])) if mask is not None else ''},
                {'name': 'slices', 'title': 'Slices (um):', 'type': 'str',
                 'value': mask_to_str(mask[0]) if mask is not None else ''}]})
    return Parameter.create(name='settings', type='group', children=children)


_data_folder_saver = None  # saves the runs without a given file


def run_algorithm(algo, n_iterations: int = 1, ini_phase: Union[str, np.ndarray] = 'FlatPhase',
                  ini_phase_params: Optional[dict] = None, save_fields: Union[bool, Iterable[str]] = False,
                  save_metrics: bool = False, h5file: Union[None, str, Path] = None, verbose: bool = True,
                  save_final: bool = False):
    """ Run the algorithm (iterations only for the iterative ones), the results are in its fields

    With ``verbose`` (default), the index of the iteration and the metrics (fitness, efficiency) are printed after each
    iteration of an iterative algorithm.

    The initial phase is the name of a phase of the factory with its parameters, or an array.

    With ``save_fields`` and/or ``save_metrics``, the output of each iteration is saved in a h5 file in the format of
    the continuous saving of the extension (a group /RawData/ShapingXXX per run, the data enlarged along a 'step' axis):
    ``save_fields`` True for all the fields (output and modulator amplitude and phase, intermediate intensity) or the
    full names of some of them ('modulator/phase'...), ``save_metrics`` for the metrics. ``h5file``: the file to add
    the run to (created if needed), None for a file in the PyMoDAQ data folder as the extension, created at the first
    saved run and holding the next ones. The path of the file is stored in ``algo.saved_h5file``.

    ``save_final`` saves all the fields and the metrics of the last iteration once, at the end of the run (as the Save
    action of the extension), in a sub group ``Final`` of the group of the run, next to the data saved at each
    iteration, so with the same settings. It can be used alone or with the two other options."""
    phase = initial_phase(algo, ini_phase, ini_phase_params) if algo.INI_PHASE else np.zeros(algo.shape)
    saver = None
    if save_fields or save_metrics or save_final:
        global _data_folder_saver
        if h5file is not None:
            saver = RunSaver()
            saver.open_file(h5file)
        else:  # one file in the data folder for the session (the file name has a one second resolution)
            if _data_folder_saver is None:
                _data_folder_saver = RunSaver()
            saver = _data_folder_saver
        saver.fields, saver.metrics = save_fields, save_metrics
        saver.start(settings_as_xml=settings_to_xml((
            algorithm_name_settings(type(algo).ALGO_NAME),
            run_settings(algo, algo.parent_app, ini_phase, ini_phase_params, n_iterations), algo.settings)))
        # the input and target fields as used by the algorithm, with the settings of their loaders
        app = algo.parent_app
        saver.add_loaded_fields(
            algo._input_field, algo._target_field,
            *[loader_settings(app, *app.field_loaders[role]) if app.field_loaders[role] is not None else ()
              for role in ('input', 'target')])
    try:
        algo.do_things_after_init()
        if algo.INI_PHASE:
            algo.define_input_phase(phase)
        algo.compute_forward_fft(update_plots=False)
        n_steps = n_iterations if algo.ITERATIVE else 1
        for index in range(n_steps):
            algo.start()
            algo.compute_phase_and_or_amplitude(do_step=True, ini_phase=phase if index == 0 else None)
            algo.stop()
            if verbose and algo.ITERATIVE:
                print(f'iteration {index + 1}/{n_steps}: fitness = {algo.fitness:.4g}, '
                      f'efficiency = {algo.efficiency:.4g}')
            if saver is not None:
                saver.add(algo.get_fields_to_plot())
        if saver is not None and save_final:
            saver.add_final(algo.get_fields_to_plot())
    finally:
        if saver is not None:
            algo.saved_h5file = saver.file_path
            saver.close_file()
    return algo


_qt_viewers = []  # keep the qt viewers alive (they would be garbage collected otherwise)


def _image_axes(figure):
    """ The axes of a figure showing 2D data (pcolormesh), not the 1D plots"""
    from matplotlib.collections import QuadMesh
    return [ax for ax in figure.axes if any(isinstance(c, QuadMesh) for c in ax.collections)]


def equal_aspect(figure):
    """ Same scale along both axes for the 2D data of a figure"""
    for ax in _image_axes(figure):
        ax.set_aspect('equal')
    return figure


def log_intensity(field, decades: float = 6., name: str = ''):
    """ The intensity of a field in log10, clipped ``decades`` below its maximum, as a data object to plot"""
    intensity = field.intensity
    floor = intensity.max() * 10 ** -decades if intensity.max() > 0 else 1.
    dwa = field.intensity_as_dwa(name, name='log10_intensity')
    dwa.data = [np.log10(np.maximum(intensity, floor))]
    dwa.labels = ['log10(Intensity)']
    return dwa


def customize(figure, clims: Optional[list] = None, xlim: Optional[tuple] = None, ylim: Optional[tuple] = None,
              units: str = 'um'):
    """ Customize a matplotlib figure of fields: color limits of each image (a list, one (min, max) or None per image,
    in the plotting order), zoom along x and y given in um (the axes are in ``units``)"""
    for ax, clim in zip(_image_axes(figure), clims or []):
        if clim is not None:
            for mesh in ax.collections:
                mesh.set_clim(*clim)
    for lim, setter in ((xlim, 'set_xlim'), (ylim, 'set_ylim')):
        if lim is not None:
            values = [Q_(value, 'um').m_as(units) for value in lim]
            for ax in _image_axes(figure):
                getattr(ax, setter)(*values)
    return figure


def customize_qt(dispatcher, clims: Optional[list] = None, xlim: Optional[tuple] = None, ylim: Optional[tuple] = None,
                 units: str = 'um'):
    """ Starting state of the qt viewers of a field (one per data, in the plotting order): color levels (a list, one
    (min, max) or None per viewer) and zoom along x and y given in um (the axes are in ``units``). Both can then be
    changed interactively"""
    x_range = None if xlim is None else [Q_(value, 'um').m_as(units) for value in xlim]
    y_range = None if ylim is None else [Q_(value, 'um').m_as(units) for value in ylim]
    for index, viewer in enumerate(dispatcher.viewers):
        view = getattr(viewer, 'view', None)
        if view is None or not hasattr(view, 'histogrammer'):  # not a 2D viewer
            continue
        clim = (clims or [])[index] if index < len(clims or []) else None
        if clim is not None:
            view.histogrammer.get_histogram('red').setLevels(*clim)
        if x_range is not None or y_range is not None:
            view.plotitem.vb.setRange(xRange=x_range, yRange=y_range, padding=0)
    return dispatcher


def center_axes(dte):
    """ Axes of the 2D data in um with their origin at the center of the field, as the masks and the zoom"""
    for dwa in dte:
        if dwa.dim.name == 'Data2D':
            for axis in dwa.axes:
                if axis.units:
                    axis.scaling = Q_(axis.scaling, axis.units).m_as('um')
                    axis.units = 'um'
                axis.offset = -axis.scaling * axis.size / 2
    return dte


def mask_in_plot_frame(dte, mask):
    """ The mask ((slices in the frame of the extension, type) as given to :func:`set_mask`) in the frame of the plots,
    centered on the field (see :func:`center_axes`, to be called first)"""
    if mask is None:
        return None
    slices, mask_type = mask
    dwa = next(dwa for dwa in dte if dwa.dim.name == 'Data2D')
    centered = []
    for dim, _slice in enumerate(regions.as_slices(slices)):
        axis = dwa.get_axis_from_index(dim)[0]
        half_um = Q_(-axis.offset, axis.units or 'um').m_as('um')  # center_axes puts the origin at the center
        centered.append(slice(_slice.start - half_um, _slice.stop - half_um))
    return tuple(centered), mask_type


def draw_mask(figure, slices_um, mask_type: str = 'elliptical', units: str = 'um', color: str = 'red'):
    """ Draw the outline of a mask (slices in um around the center of the field, as the plots of this module, see
    :func:`mask_in_plot_frame`) on the 2D data of a matplotlib figure (axes in ``units``)"""
    from matplotlib.patches import Ellipse, Rectangle
    (y0, y1), (x0, x1) = [[Q_(value, 'um').m_as(units) for value in (_slice.start, _slice.stop)]
                          for _slice in regions.as_slices(slices_um)]
    for ax in _image_axes(figure):
        if MaskType(mask_type) == MaskType.ELLIPTICAL:
            patch = Ellipse(((x0 + x1) / 2, (y0 + y1) / 2), x1 - x0, y1 - y0)
        else:
            patch = Rectangle((x0, y0), x1 - x0, y1 - y0)
        patch.set(fill=False, edgecolor=color, linewidth=1.5)
        ax.add_patch(patch)
    return figure


def draw_mask_qt(dispatcher, slices_um, mask_type: str = 'elliptical', units: str = 'um', color: str = 'r'):
    """ Draw the outline of a mask on the 2D viewers of a ViewerDispatcher, replacing the previous one"""
    import pyqtgraph
    for plotitem, roi in getattr(dispatcher, 'mask_rois', []):
        plotitem.removeItem(roi)
    dispatcher.mask_rois = []
    if slices_um is None:
        return dispatcher
    (y0, y1), (x0, x1) = [[Q_(value, 'um').m_as(units) for value in (_slice.start, _slice.stop)]
                          for _slice in regions.as_slices(slices_um)]
    for viewer in dispatcher.viewers:
        view = getattr(viewer, 'view', None)
        if view is None or not hasattr(view, 'plotitem'):
            continue
        roi_class = pyqtgraph.EllipseROI if MaskType(mask_type) == MaskType.ELLIPTICAL else pyqtgraph.RectROI
        roi = roi_class((x0, y0), (x1 - x0, y1 - y0), pen=pyqtgraph.mkPen(color, width=2), movable=False,
                        resizable=False, rotatable=False)
        for handle in roi.getHandles():
            roi.removeHandle(handle)
        view.plotitem.addItem(roi)
        dispatcher.mask_rois.append((view.plotitem, roi))
    return dispatcher


def _clear(figure):
    """ Empty a figure to draw it again, its title included (Figure.clear keeps the previous one)"""
    for text in list(figure.texts):
        text.remove()
    figure._suptitle = None
    figure.clear()


def _draw_2d(figure, dte):
    """ Draw 2D data in a matplotlib figure, one row per data object (as the matplotlib plotter of PyMoDAQ, but in a
    given figure so that it can be updated)"""
    _clear(figure)
    for row, dwa in enumerate(dte):
        xaxis = dwa.get_axis_from_index(1)[0]
        yaxis = dwa.get_axis_from_index(0)[0]
        for column, array in enumerate(dwa):
            ax = figure.add_subplot(len(dte), len(dwa), row * len(dwa) + column + 1)
            ax.pcolormesh(xaxis.get_data(), yaxis.get_data(), array)
            ax.set_title(f'{dwa.name}/{dwa.labels[column]}')
            ax.set_xlabel(f'{xaxis.label} ({xaxis.units})')
            ax.set_ylabel(f'{yaxis.label} ({yaxis.units})')
    return figure


def _is_inline() -> bool:
    import matplotlib
    return 'inline' in matplotlib.get_backend().lower()


def _show(dte, backend: str, size, clims=None, xlim=None, ylim=None, show: bool = True, mask=None, figure=None,
          title: str = ''):
    """ Plot with matplotlib (returns the figure) or with the qt viewers of PyMoDAQ (returns the ViewerDispatcher,
    interactive when the IDE runs a Qt event loop, in Spyder: graphics backend set to Qt or Automatic)

    figure: a Figure or a ViewerDispatcher returned by a previous call, to update it instead of creating a new one
    """
    center_axes(dte)
    units = (str(dte[0].get_axis_from_index(1)[0].units) if len(dte[0].axes) else '') or 'um'
    mask = mask_in_plot_frame(dte, mask)
    if backend == 'qt':
        ensure_qapp()
        viewer = dte.plot('qt', viewer=figure)
        if figure is None:
            _qt_viewers.append(viewer)
        customize_qt(viewer, clims, xlim, ylim, units)
        if mask is not None or hasattr(viewer, 'mask_rois'):
            draw_mask_qt(viewer, *(mask if mask is not None else (None,)), units=units)
        return viewer
    from matplotlib import pyplot as plt
    reuse = figure is not None
    if all(dwa.dim.name == 'Data2D' for dwa in dte):
        figure = _draw_2d(figure if reuse else plt.figure(), dte)
    else:
        if reuse:
            plt.close(figure)
        figure = dte.plot('matplotlib')
        reuse = False
    figure.set_size_inches(*size)
    customize(figure, clims, xlim, ylim, units=units)
    if mask is not None:
        draw_mask(figure, *mask, units=units)
    equal_aspect(figure)
    if title:
        figure.suptitle(title)
    figure.tight_layout(rect=(0, 0, 1, 0.96 if title else 1))  # room for the title
    if show:
        _display(figure, reuse)
    return figure


def _display(figure, reuse: bool):
    """ Show a new figure, or redraw an updated one (displayed again with the inline backend of Spyder or Jupyter,
    whose figures are static images)"""
    from matplotlib import pyplot as plt
    if reuse and _is_inline():
        try:
            from IPython.display import display
            display(figure)
        except ImportError:
            pass
    elif reuse:
        figure.canvas.draw_idle()
        figure.show()
    else:
        plt.show()


def snap(algo, ini_phase: Union[str, np.ndarray] = 'FlatPhase', ini_phase_params: Optional[dict] = None):
    """ One step of the algorithm without any mask, to look at the intermediate plane (4f setups) before placing its
    mask: returns a copy of the intermediate field, None for algorithms without intermediate plane. The masks set in
    the app are kept for the next runs"""
    masks = dict(algo.parent_app.masks)
    try:
        for key in algo.parent_app.masks:
            algo.parent_app.masks[key] = None
        run_algorithm(algo, 1, ini_phase, ini_phase_params)
    finally:
        algo.parent_app.masks.update(masks)
    return None if algo.intermediate_field is None else algo.intermediate_field.deepcopy()


def plot_field(field, name: str = '', log: bool = False, decades: float = 6., clim: Optional[tuple] = None,
               phase_clim: Optional[tuple] = None, xlim: Optional[tuple] = None, ylim: Optional[tuple] = None,
               mask: Optional[tuple] = None, backend: str = 'matplotlib', figure=None, show: bool = True):
    """ Plot the amplitude (or with ``log`` the intensity in log10, down to ``decades`` below its maximum) and the
    phase of a field, the origin of the axes at the center of the field (as for the masks)

    clim / phase_clim: (min, max) of the colors of the amplitude (or log10 intensity) and of the phase
    xlim / ylim: zoom, (min, max) in um
    mask: (slices in um, mask type) as given to :func:`set_mask`, its outline is drawn
    backend: 'matplotlib' (returns the figure, to customize further) or 'qt' (interactive viewers of PyMoDAQ, the
    options above give their starting state)
    figure: what a previous call returned (Figure or ViewerDispatcher), updated instead of creating a new plot
    """
    from pymodaq_data.data import DataToExport
    data = field.split_as_dte(name).data  # amplitude and phase side by side
    if log:
        data[0] = log_intensity(field, decades, name=name)
    dte = DataToExport(name, data=data)
    reuse = figure is not None
    figure = _show(dte, backend, (9, 7), [clim, phase_clim], xlim, ylim, show=False, mask=mask, figure=figure,
                   title=name)
    if backend != 'qt' and show:
        _display(figure, reuse)
    return figure


def _overview_rows(algo) -> list:
    """ The fields of the overview: (title, data object with the amplitude and the phase), in um around the center.
    The intermediate plane (4f setups) is shown with its intensity in log scale"""
    from pymodaq_data.data import DataToExport
    rows = []
    for title, field, log in (('Output Plane', algo.output_field, False),
                              ('Modulator Plane', algo.modulator_field, False),
                              ('Intermediate Plane', algo.intermediate_field, True)):
        if field is None:
            continue
        data = field.split_as_dte(title).data
        if log:
            data[0] = log_intensity(field, name=title)
        rows.append((title, center_axes(DataToExport(title, data=data))))
    return rows


def _plot_overview_matplotlib(algo, figure=None):
    """ One figure with subplots: a row per field (amplitude | phase, titled with the field), then the metrics"""
    from matplotlib import pyplot as plt
    rows = _overview_rows(algo)
    figure = plt.figure(figsize=(9, 3.5 * (len(rows) + 1))) if figure is None else figure
    _clear(figure)
    axes = figure.subplots(len(rows) + 1, 2, squeeze=False)
    for (title, dte), row_axes in zip(rows, axes):
        for ax, dwa in zip(row_axes, dte):
            xaxis, yaxis = dwa.get_axis_from_index(1)[0], dwa.get_axis_from_index(0)[0]
            ax.pcolormesh(xaxis.get_data(), yaxis.get_data(), dwa.data[0])
            ax.set_title(f'{title}: {dwa.labels[0]}')
            ax.set_xlabel(f'{xaxis.label} ({xaxis.units})')
            ax.set_ylabel(f'{yaxis.label} ({yaxis.units})')
            ax.set_aspect('equal')
    metrics = algo.metrics_as_dwa()
    ax = axes[-1][0]
    ax.bar(metrics.labels, [float(array[0]) for array in metrics.data])
    ax.set_title('Metrics')
    axes[-1][1].axis('off')
    figure.tight_layout()
    return figure


class QtOverview:
    """ The overview in the qt backend, built as in the extension: a dock per field, titled with the field, holding a
    ViewerDispatcher for its amplitude and phase (the intermediate plane shows its intensity in log scale), and a dock
    for the metrics"""

    def __init__(self, algo):
        from pymodaq_gui.utils.dock import Dock, DockArea
        from pymodaq_gui.plotting.data_viewers.viewer import ViewerDispatcher
        ensure_qapp()
        self.dockarea = DockArea()
        self.dockarea.setWindowTitle('Algorithm overview')
        self.docks, self.dispatchers = {}, {}
        titles = ['Metrics', 'Modulator Plane', 'Output Plane'] + (
            ['Intermediate Plane'] if algo.intermediate_field is not None else [])
        placement = {'Metrics': ('left', None), 'Modulator Plane': ('right', None),
                     'Output Plane': ('bottom', 'Modulator Plane'), 'Intermediate Plane': ('bottom', 'Metrics')}
        for title in titles:
            self.docks[title] = Dock(title)
            position, relative_to = placement[title]
            self.dockarea.addDock(self.docks[title], position, None if relative_to is None else self.docks[relative_to])
            area = DockArea()
            self.dispatchers[title] = ViewerDispatcher(area, title=title)
            self.docks[title].addWidget(area)
        self.dockarea.resize(1100, 800)
        self.dockarea.show()
        _qt_viewers.append(self)

    def update(self, algo):
        for title, dte in _overview_rows(algo):
            if title in self.dispatchers:
                self.dispatchers[title].show_data(dte)
        self.dispatchers['Metrics'].show_data(algo.metrics_as_dwa().split_as_dte('Metrics'))  # as in the extension
        return self


def plot(algo, backend: str = 'matplotlib', figure=None, show: bool = True):
    """ Overview of the algorithm: a plot per field (output, modulator and, in 4f setups, intermediate planes, each
    with its amplitude and phase) and the metrics, as in the extension. In different planes, so without zoom: use
    :func:`plot_field` on one field to customize its plot.

    backend: 'matplotlib' (one figure made of subplots, returned) or 'qt' (a dock per field, each with its viewers)
    figure: what a previous call returned, updated instead of creating a new plot
    """
    if backend == 'qt':
        overview = figure if figure is not None else QtOverview(algo)
        return overview.update(algo)
    reuse = figure is not None
    figure = _plot_overview_matplotlib(algo, figure)
    if show:
        _display(figure, reuse)
    return figure
