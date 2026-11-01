"""Run a shaping algorithm outside of the application, to try it and look at its results

Meant to be executed in an IDE (Spyder, VS Code, PyCharm...) or in Jupyter: edit the values of the first cell then run
the cells one after the other. The cells are delimited by ``# %%``, so ``jupytext --to ipynb`` turns it into a
notebook. The helpers are in ``pymodaq_plugins_beam_shaping.utilities.headless_algorithms``.

Not tested on hardware, nor in the extension: the algorithm gets the same calls as in the AlgoApp through a minimal
stand-in for the application. A QApplication is needed (the parameters are widgets), it is created if missing.
"""
from pymodaq_plugins_beam_shaping.algorithms.utils import ApplyMaskTo
from pymodaq_plugins_beam_shaping.utilities import headless_algorithms as pg

# %% Settings: edit them
# Run pg.list_available() to see the available names and their parameters.

# The simulated shaper: the default one of the plugin configuration with some values overridden
SHAPER_PARAMS = dict()  # e.g. dict(width=512, height=512, pixel_size=8., modulator_type='amplitude')

# The algorithm, its parameters (dotted names for groups), the number of iterations (iterative algorithms only)
ALGORITHM = 'Gerchberg-Saxton'
ALGORITHM_PARAMS = dict()  # e.g. for 'DMD Lee': dict(carrier_factor=1., remove_carrier=True)
N_ITERATIONS = 1
# The initial phase (algorithms using one): a phase of the factory as in the extension ('FlatPhase', 'RandomPhase',
# 'QuadraticPhase'...) with its parameters, or a 2D array of the shape of the fields
INITIAL_PHASE = 'FlatPhase'
INITIAL_PHASE_PARAMS = dict()  # e.g. for 'QuadraticPhase': {'quadratic.auto': False, 'quadratic.x_quad': 0.5}

# The field entering the shaper: loader name and its parameters
INPUT_LOADER = 'GaussianIntensity'
INPUT_PARAMS = dict()  # e.g. dict(beam_size_x=..., beam_size_y=...), see pg.list_available()

# The field to obtain after the shaper
TARGET_LOADER = 'ImageFiles'
TARGET_PARAMS = {'phase.load': False}  # only the amplitude of the default image (set 'amplitude.file' to use yours)

# Masks: slices in um as ((start, stop) along y, (start, stop) along x) around the center of the field, in the plane
# of the target or the intermediate plane (4f setups)
APPLY_TARGET_MASK = False
TARGET_MASK = ((-100., 100.), (-100., 100.))
TARGET_MASK_TYPE = 'elliptical'  # or 'square'
APPLY_INTERMEDIATE_MASK = False
INTERMEDIATE_MASK = ((-100., 100.), (-100., 100.))
INTERMEDIATE_MASK_TYPE = 'elliptical'

# %% Shaper, algorithm and fields
shaper = pg.make_shaper(**SHAPER_PARAMS)
app = pg.HeadlessApp(shaper)

# Reload the module of the algorithm to use its current code: always do it, even the first time, so that after editing
# the algorithm one only has to run this cell and the following ones (not the settings cell, nor the whole script).
# A base class defined in another module is not reloaded: reload it in the Python console if you change it.
algo_class = pg.reload_algorithm(ALGORITHM)
algo = pg.create_algorithm(algo_class, app, ALGORITHM_PARAMS)

# %% Input field
input_field = pg.load_field(INPUT_LOADER, INPUT_PARAMS, app)
pg.plot_field(input_field, 'input')

# %% Target field
# Given to the algorithm with the input field: the plotted target is the one the algorithm uses, scaled to the target
# plane (the axes are the ones of this plane) and normalized to the intensity of the input field
target_field = pg.load_field(TARGET_LOADER, TARGET_PARAMS, app)
pg.set_fields(algo, input_field, target_field)
pg.plot_field(pg.get_target_field(algo), 'target')

# %% Masks
pg.set_mask(app, ApplyMaskTo.TARGET, TARGET_MASK if APPLY_TARGET_MASK else None, TARGET_MASK_TYPE)
pg.set_mask(app, ApplyMaskTo.INTERMEDIATE, INTERMEDIATE_MASK if APPLY_INTERMEDIATE_MASK else None,
            INTERMEDIATE_MASK_TYPE)

# %% Run
pg.run_algorithm(algo, N_ITERATIONS, INITIAL_PHASE, INITIAL_PHASE_PARAMS)
print(f'fitness = {algo.fitness:.4g}, efficiency = {algo.efficiency:.4g}')

# %% Plots
pg.plot(algo)

# %% The results as Field objects, to go further
output_field = algo.output_field
modulator_field = algo.modulator_field
intermediate_field = algo.intermediate_field  # None for algorithms without intermediate plane
