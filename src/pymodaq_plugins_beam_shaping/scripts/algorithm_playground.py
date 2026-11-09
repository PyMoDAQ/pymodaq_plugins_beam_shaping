"""Run a shaping algorithm outside of the application, to try it and look at its results

Meant to be executed in an IDE (Spyder, VS Code, PyCharm...) or in Jupyter: run the cells one after the other, each one
starting with its settings to edit. The cells are delimited by ``# %%``, so ``jupytext --to ipynb`` turns it into a
notebook. The helpers are in ``pymodaq_plugins_beam_shaping.utilities.headless_algorithms``.

Not tested on hardware, nor in the extension: the algorithm gets the same calls as in the AlgoApp through a minimal
stand-in for the application. A QApplication is needed (the parameters are widgets), it is created if missing.
"""
from pymodaq_plugins_beam_shaping.algorithms.utils import ApplyMaskTo
from pymodaq_plugins_beam_shaping.utilities import headless_algorithms as pg

# %% Shaper
# Run pg.list_available() to see the available names (algorithms, initial phases, loaders) and their parameters.
# Each cell starts with its settings: edit them, then run the cell.

# The simulated shaper: the default one of the plugin configuration with some values overridden
SHAPER_PARAMS = dict()  # e.g. dict(width=512, height=512, pixel_size=8., modulator_type='amplitude')
shaper = pg.make_shaper(**SHAPER_PARAMS)

# The stand-in for the application, which owns the shaper and the masks
app = pg.HeadlessApp(shaper)

# The plots: 'matplotlib' (figures returned, to customize further) or 'qt' (the interactive viewers of PyMoDAQ: zoom,
# levels, ROI..., in Spyder set Preferences > IPython console > Graphics > Backend to Qt or Automatic)
# The axes of the plots are in um, their origin at the center of the field, as for the masks.
# Each plot_field below takes: log (intensity in log10 instead of the amplitude), clim and phase_clim (min, max of the
# colors), xlim and ylim (zoom, (min, max) in um). With 'qt' they give the starting state of the viewers.
PLOT_BACKEND = 'matplotlib'
overview = None  # the overview plot, updated (not created again) each time the overview cell is run

# %% Input field: the field entering the shaper, loader name and its parameters
INPUT_LOADER = 'GaussianIntensity'
INPUT_PARAMS = dict()  # e.g. dict(beam_size_x=..., beam_size_y=...)

input_field = pg.load_field(INPUT_LOADER, INPUT_PARAMS, app)
pg.plot_field(input_field, 'input', log=False, clim=None, xlim=None, ylim=None, backend=PLOT_BACKEND)

# %% Target field: the field to obtain after the shaper
TARGET_LOADER = 'ImageFiles'
TARGET_PARAMS = {'phase/load': False}  # only the amplitude of the default image (set 'amplitude/file' to use yours)

target_field = pg.load_field(TARGET_LOADER, TARGET_PARAMS, app)
# as loaded, with the axes of the modulator plane
pg.plot_field(target_field, 'target', log=False, clim=None, xlim=None, ylim=None, backend=PLOT_BACKEND)

# %% Algorithm
# Its parameters (names separated by / for groups) and the number of iterations (iterative algorithms only)
ALGORITHM = 'Gerchberg-Saxton'
ALGORITHM_PARAMS = dict()  # e.g. for 'Parallel Lee': dict(carrier_factor=1., remove_carrier=True)
N_ITERATIONS = 1
# The initial phase (algorithms using one): a phase of the factory as in the extension ('FlatPhase', 'RandomPhase',
# 'QuadraticPhase'...) with its parameters, or a 2D array of the shape of the fields. For 'RandomPhase', set
# dict(fixed_seed=True, seed=1) to get the same pattern at each run, and change the seed to get another one
INITIAL_PHASE = 'FlatPhase'
INITIAL_PHASE_PARAMS = dict()  # e.g. for 'QuadraticPhase': {'quadratic/auto': False, 'quadratic/x_quad': 0.5}

# Reload the module of the algorithm to use its current code: always do it, even the first time, so that after editing
# the algorithm one only has to run this cell and the following ones (not the ones loading the fields).
# A base class defined in another module is not reloaded: reload it in the Python console if you change it.
algo_class = pg.reload_algorithm(ALGORITHM)
algo = pg.create_algorithm(algo_class, app, ALGORITHM_PARAMS)
# the target is scaled by the algorithm to the target plane: pg.plot_field(pg.get_target_field(algo)) shows it
pg.set_fields(algo, input_field, target_field)

# %% Snap: one step of the algorithm without masks, to see the intermediate plane (4f setups) before placing its mask
snapped_intermediate = pg.snap(algo, INITIAL_PHASE, INITIAL_PHASE_PARAMS)  # None without intermediate plane
snap_plot = None  # the plot of the snap, updated by the masks cell
if snapped_intermediate is not None:
    snap_plot = pg.plot_field(snapped_intermediate, 'intermediate (snap, no mask)', log=True, clim=None, xlim=None,
                              ylim=None, backend=PLOT_BACKEND)

# %% Masks: slices in um, along y then along x, around the center of the field, as shown by the field loader and the
# extension: they can be pasted as is, e.g. TARGET_MASK = (slice(-100, 100, None), slice(-50, 50, None)), as text or as
# ((-100, 100), (-50, 50)).
# None: the default region of the extension, centered and covering 2/3 of the effective area of the SLM in the plane
# (printed below, copy and edit it). Run this cell again to adjust the intermediate mask: its outline is drawn on the
# plot of the snap, which is updated
APPLY_TARGET_MASK = False  # in the plane of the target
TARGET_MASK = None
TARGET_MASK_TYPE = 'square'  # or 'elliptical'
APPLY_INTERMEDIATE_MASK = False  # in the intermediate plane (4f setups)
INTERMEDIATE_MASK = None
INTERMEDIATE_MASK_TYPE = 'elliptical'

target_mask = intermediate_mask = None
if APPLY_TARGET_MASK:
    target_mask = TARGET_MASK if TARGET_MASK is not None else pg.default_mask(algo, ApplyMaskTo.TARGET)
    print(f'TARGET_MASK = {pg.mask_to_str(target_mask)}')
if APPLY_INTERMEDIATE_MASK:
    intermediate_mask = (INTERMEDIATE_MASK if INTERMEDIATE_MASK is not None
                         else pg.default_mask(algo, ApplyMaskTo.INTERMEDIATE))
    print(f'INTERMEDIATE_MASK = {pg.mask_to_str(intermediate_mask)}')
pg.set_mask(app, ApplyMaskTo.TARGET, target_mask, TARGET_MASK_TYPE)
pg.set_mask(app, ApplyMaskTo.INTERMEDIATE, intermediate_mask, INTERMEDIATE_MASK_TYPE)
if snap_plot is not None and intermediate_mask is not None:  # the plot of the snap is updated, not created again
    pg.plot_field(snapped_intermediate, 'intermediate (snap) and its mask', log=True, clim=None, xlim=None, ylim=None,
                  mask=(intermediate_mask, INTERMEDIATE_MASK_TYPE), backend=PLOT_BACKEND, figure=snap_plot)

# %% Run
# Optional saving at each iteration, in the format of the continuous saving of the extension: one group
# /RawData/ShapingXXX per run, the data enlarged along a 'step' axis
SAVE_FIELDS = False  # True: all the fields (output, modulator, intermediate), or some, e.g. ('modulator/phase',)
SAVE_METRICS = False  # the metrics (fitness, efficiency...)
SAVE_FINAL = False  # all the fields and the metrics of the last iteration, once at the end (sub group 'Final' of the run)
SAVE_FILE = None  # None: a file in the PyMoDAQ data folder for the session, or a path. The runs are added to the file

pg.run_algorithm(algo, N_ITERATIONS, INITIAL_PHASE, INITIAL_PHASE_PARAMS, save_fields=SAVE_FIELDS,
                 save_metrics=SAVE_METRICS, save_final=SAVE_FINAL, h5file=SAVE_FILE)
if SAVE_FIELDS or SAVE_METRICS or SAVE_FINAL:
    print(f'saved in {algo.saved_h5file}')
print(f'fitness = {algo.fitness:.4g}, efficiency = {algo.efficiency:.4g}')

# %% Overview, as in the extension: the output, modulator and intermediate planes (a dock each with qt, the rows of
# subplots with matplotlib, with their amplitude and phase) and the metrics. Run it again to update the plot
overview = pg.plot(algo, backend=PLOT_BACKEND, figure=overview)

# %% Plot of the output field, to customize
pg.plot_field(algo.output_field, 'output', log=False, clim=None, xlim=None, ylim=None, backend=PLOT_BACKEND)

# %% Plot of the intermediate plane (4f setups), its intensity in log scale by default
if algo.intermediate_field is not None:
    pg.plot_field(algo.intermediate_field, 'intermediate', log=True, clim=None, xlim=None, ylim=None,
                  backend=PLOT_BACKEND)

# %% The results as Field objects, to go further
output_field = algo.output_field
modulator_field = algo.modulator_field
intermediate_field = algo.intermediate_field  # None for algorithms without intermediate plane
