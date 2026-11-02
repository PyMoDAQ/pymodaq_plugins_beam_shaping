How to add a custom Algorithm
=============================

An algorithm computes, from an *input field* (the beam on the modulator) and a *target field* (the beam to obtain),
the phase and/or the amplitude to display on the modulator. Adding one means writing a class derived from ``AlgoBase``
and registering it in the factory: the extension then lists it, creates its settings and runs it like the other
ones, nothing else has to be changed.

.. contents::
   :local:
   :depth: 1

The spirit
----------

* An algorithm is a *state machine over fields*: the extension gives it the fields once (input, target), then asks it
  to compute, as many times as needed. It does not know about the interface, the shaper hardware or the plots.
* The algorithm owns four fields (``Field`` objects, amplitude and phase with calibrated axes):

  - ``_input_field``: the beam illuminating the modulator;
  - ``_modulator_field``: the field right after the modulator, the one the algorithm computes. It is the input
    field modified by the phase and/or the amplitude to display;
  - ``_target_field``: the field to obtain;
  - ``_output_field``: the field obtained, to compare with the target.

  A ``4f`` setup also has an ``intermediate_field``, in the Fourier plane (where a filter is applied).
* The algorithm writes its result in the modulator field with the methods of ``AlgoBase``
  (``set_phase_in_modulator_plane``, ``set_amplitude_in_modulator_plane`` or ``set_field_in_modulator_plane``, which
  chooses according to the type of the shaper) so that the crosstalk and the phase wrap options of the extension are
  applied for you.
* Everything physical (wavelength, focal lengths, pixel sizes) comes from the plugin configuration and the shaper,
  never from a global of your own.

The factory
-----------

``AlgorithmFactory`` (``pymodaq_plugins_beam_shaping.algorithms.factory``) keeps a registry of the algorithms by
name. A class registers itself with a decorator:

.. code-block:: python

   from pymodaq_plugins_beam_shaping.algorithms import AlgoBase
   from pymodaq_plugins_beam_shaping.algorithms.factory import AlgorithmFactory

   @AlgorithmFactory.register_algorithm()
   class MyAlgo(AlgoBase):
       ALGO_NAME = 'My algorithm'
       ...

The decorator raises ``NotImplementedError`` if ``ALGO_NAME`` or ``SETUP_TYPE`` is missing. The name must be unique:
**the factory keeps the first class registered under a name** and ignores the next ones (this is why the script of
:ref:`sec-algorithms-playground` has to remove the entry before reloading a module).

The module must be imported to register its class:

* a module placed in ``pymodaq_plugins_beam_shaping/algorithms/algorithms/`` is imported automatically when the package
  is imported;
* a module of another package is declared in the entry point group ``pymodaq_plugins_beam_shaping.algorithms`` (see
  below).

The algorithm also appears in the list of the *Algorithm* settings: ``default_algo`` of the plugin configuration is
completed at start with the registered names, and the list shown is filtered by the type of the current shaper (see
``MODULATOR_TYPES``).

The class attributes
--------------------

.. list-table::
   :header-rows: 1
   :widths: 22 78

   * - Attribute
     - Meaning
   * - ``ALGO_NAME``
     - **Required.** Name shown in the interface and key in the factory and in the configuration.
   * - ``SETUP_TYPE``
     - **Required.** ``LensSetup.NoLens``, ``LensSetup.TwoF`` or ``LensSetup.FourF`` (module
       ``algorithms.utils``). It sets the physical size of the pixels of the target (``get_target_pixels_size``), the
       existence of an intermediate plane (``4f``) and the masks offered in the interface.
   * - ``ALGOTYPE``
     - ``AlgoType.AMPLITUDE`` (default: the intensity of the output is compared to the one of the target),
       ``AlgoType.PHASE`` (the phase is compared) or ``AlgoType.AMPLITUDE_PHASE`` (fidelity of the complex fields).
       It selects the *fitness* displayed (``fitness`` property, overridable).
   * - ``MODULATOR_TYPES``
     - Tuple of ``ModulatorType`` the algorithm can compute for, ``(ModulatorType.PHASE,)`` by default. A shaper
       modulating both phase and amplitude accepts any algorithm. Use ``(ModulatorType.AMPLITUDE,)`` for a DMD.
   * - ``INI_PHASE``
     - True (default) if the extension should provide an initial phase (the *Initial Phase* settings are then shown).
   * - ``ITERATIVE``
     - True if the algorithm is run again and again (Gerchberg-Saxton like): the *stopping criteria* settings are then
       shown.
   * - ``MANUAL_LOOP``
     - True (default): the extension calls ``compute_phase_and_or_amplitude`` in a loop. False if the algorithm loops
       by itself (see the minimizer ones) and should refresh the plots during the course of its run.
   * - ``RECOMPUTE_ON_CHANGE``
     - False by default. True to compute again each time a setting changes (non iterative algorithms).
   * - ``STATUS``
     - How far the algorithm has been validated, written by hand by its developer: ``AlgoStatus.TESTED``,
       ``AlgoStatus.IN_PROGRESS``, ``AlgoStatus.UNTESTED`` (default) or ``AlgoStatus.BROKEN`` (module
       ``algorithms.utils``). It is shown next to the name in the extension (a colored disc and the word). A broken
       algorithm is not listed, unless ``show_broken = true`` in the ``[algo]`` section of the plugin configuration.
   * - ``STATUS_NOTE``
     - One sentence on what was checked or what is known not to work, shown in the tooltip of the status.
   * - ``params``
     - List of dictionaries defining the settings of the algorithm, see below.

The settings
------------

``params`` is a list of ``pyqtgraph`` parameter definitions, as in all PyMoDAQ settings:

.. code-block:: python

   params = [
       {'title': 'Super Pixel size (pxls)', 'name': 'super_pixel', 'type': 'int', 'value': 5, 'min': 1},
       {'title': 'Remove carrier:', 'name': 'remove_carrier', 'type': 'bool', 'value': True},
   ]

They are displayed in the *Algorithm* settings and read in the code with ``self.settings['super_pixel']``. When the
user changes one, ``value_changed(param)`` is called: the default one calls ``parent_app.algo_settings_changed()``;
set ``RECOMPUTE_ON_CHANGE = True`` to run the algorithm again at once (as *Parallel Lee* does) or reimplement the method. The values are saved in the configuration of the extension
with the other settings.

The methods to write
--------------------

The constructor only forwards the parent application (``None`` when the algorithm is run from the script):

.. code-block:: python

   def __init__(self, parent=None, *args, **kwargs):
       super().__init__(parent)

The extension then calls, in this order:

1. ``set_modulator_field`` and ``set_input_field`` (the input field, hook ``do_things_after_set_input``);
2. ``get_target_pixels_size`` to scale the target (the default implementation follows ``SETUP_TYPE`` and the
   configuration, reimplement it if the pixel size of your target plane is different), then ``set_target_field``
   (hook ``do_things_after_set_target``, the target is normalized to the intensity of the input);
3. ``do_things_after_init`` (hook) when the algorithm is started;
4. for each computation: ``start()``, **``compute_phase_and_or_amplitude(do_step=True, ini_phase=...)``**, then
   ``stop()``. ``ini_phase`` is the initial phase when the algorithm is (re)initialised and ``None`` for the next
   iterations;
5. ``get_fields_to_plot()`` to display the results.

The only method you *must* write is ``compute_phase_and_or_amplitude``. The simplest algorithm, *Direct*, sends the
target to the modulator:

.. code-block:: python

   @AlgorithmFactory.register_algorithm()
   class Direct(AlgoBase):
       ALGO_NAME = 'Direct'
       ALGOTYPE = AlgoType.AMPLITUDE_PHASE
       SETUP_TYPE = LensSetup.NoLens
       INI_PHASE = False

       def compute_phase_and_or_amplitude(self, do_step=True, **kwargs):
           self.set_field_in_modulator_plane(self.normalize_wrt(self._target_field, self._input_field))

An iterative algorithm propagates and corrects, here the Gerchberg-Saxton of the module ``projections.py`` (the
forward propagation uses the 2f setup of the configuration):

.. code-block:: python

   def compute_phase_and_or_amplitude(self, do_step=True, **kwargs):
       self.compute_forward_fft(update_plots=False)               # modulator -> output_field
       corrected = Field(amplitude=self._target_field.amplitude,  # target amplitude, obtained phase
                         phase=self._output_field.phase,
                         pixel_sizes=self._output_field.pixels_sizes)
       back = self.compute_backward_fft(corrected)                # output -> modulator plane
       self.set_phase_in_modulator_plane(back.phase)

Helpers of ``AlgoBase``
-----------------------

The code every algorithm of the same family needs is in ``AlgoBase``: use these helpers rather than copying it, so
that the normalisation of the transforms, the calibration of the axes and the options of the extension (crosstalk,
phase wrap, masks) behave the same for all algorithms.

.. list-table::
   :header-rows: 1
   :widths: 34 12 54

   * - Helper
     - Setup
     - What it does
   * - ``set_phase_in_modulator_plane(phase)``
     - all
     - Writes a phase in the modulator field (input amplitude kept), applying the crosstalk and phase wrap options.
   * - ``set_amplitude_in_modulator_plane(amplitude)``
     - all
     - Writes an amplitude in the modulator field.
   * - ``set_field_in_modulator_plane(field)``
     - all
     - Writes the phase, the amplitude or both depending on the type of the shaper.
   * - ``compute_forward_fft(update_plots)``
     - 2f
     - Output field = Fourier transform of the modulator field, with the axes of the target plane.
   * - ``compute_backward_fft(field)``
     - 2f
     - Inverse transform of a field of the output plane (returns a ``Field``).
   * - ``update_phase_and_propagate(phase)``
     - 2f
     - ``set_phase_in_modulator_plane`` then ``compute_forward_fft``: what a minimizer does at each step.
   * - ``back_propagate_amplitude(amplitude)``
     - 2f
     - The projection step of Gerchberg-Saxton like algorithms: keeps the phase of the output field, imposes the
       given amplitude, goes back to the modulator plane and sets the phase obtained.
   * - ``compute_intermediate_field(use_mask=True)``
     - 4f
     - Fourier transform of the modulator field into ``intermediate_field``, filtered by the mask of the
       intermediate plane (if applied) and with calibrated axes. The transform conserves the energy.
   * - ``compute_output_from_intermediate(field=None)``
     - 4f
     - Back transform of the intermediate field (or of the one given, if you modified it) into the output field,
       with the calibrated axes of the target plane.
   * - ``intermediate_pixel_sizes``
     - 4f
     - Pixel sizes of the intermediate plane (wavelength, first focal length, modulator pixels).
   * - ``compute_grid()``
     - all
     - The positions ``(x, y)`` of the pixels, in pixels, relative to the center of the array.
   * - ``normalize_wrt(field, ref_field)``
     - all
     - Scales a field to the energy of a reference one (the target is normalized to the input this way).
   * - ``apply_mask(plane)``, ``get_mask_slices(plane)``, ``get_mask_field(plane)``
     - all
     - The masks chosen in the interface (``ApplyMaskTo.TARGET`` or ``ApplyMaskTo.INTERMEDIATE``): whether it is
       applied, its slices and a ``Field`` of 1 inside and 0 outside to multiply with.
   * - ``scale_target_with_geometry(field)``, ``get_target_pixels_size()``
     - all
     - Calibrate the axes of a field of the target plane from the setup of the configuration.
   * - ``self.shaper``, ``self.shape``
     - all
     - The modulator (size, pixel size, type) and the shape of the arrays.

For anything physical, read the configuration (``plugin_config('setup', 'wavelength_nm')`` and the focal lengths)
and never use values of your own.

Two examples
------------

A 4f setup with a DMD (amplitude modulator): the grating is built from the phase of the target, the helpers do the
transform to the Fourier plane, the filtering by the mask and the transform back, with the right axes.

.. code-block:: python

   @AlgorithmFactory.register_algorithm()
   class GratingLee(AlgoBase):
       ALGO_NAME = 'Grating Lee'
       ALGOTYPE = AlgoType.PHASE
       MODULATOR_TYPES = (ModulatorType.AMPLITUDE, )
       SETUP_TYPE = LensSetup.FourF
       RECOMPUTE_ON_CHANGE = True

       params = [{'title': 'Period (pxls):', 'name': 'period', 'type': 'int', 'value': 5, 'min': 2}]

       def compute_phase_and_or_amplitude(self, do_step=True, **kwargs):
           xx, yy = self.compute_grid()
           pattern = 0.5 * (1 + np.cos(2 * np.pi * xx / self.settings['period'] - self._target_field.phase))
           self.set_amplitude_in_modulator_plane(pattern)
           self.compute_intermediate_field()
           self.compute_output_from_intermediate()

If the algorithm has to act on the field of the Fourier plane (as *Parallel Lee* does to remove the carrier), do it between
the two last calls, on ``self.intermediate_field``, or pass the modified field to ``compute_output_from_intermediate``.

A 2f setup with a phase only modulator, iterative: Gerchberg-Saxton is two calls.

.. code-block:: python

   @AlgorithmFactory.register_algorithm()
   class MyGerchbergSaxton(AlgoBase):
       ALGO_NAME = 'My Gerchberg-Saxton'
       ALGOTYPE = AlgoType.AMPLITUDE
       SETUP_TYPE = LensSetup.TwoF
       ITERATIVE = True

       def compute_phase_and_or_amplitude(self, do_step=True, **kwargs):
           self.compute_forward_fft(update_plots=False)
           self.back_propagate_amplitude(self._target_field.amplitude)

Both classes were run with the script of :ref:`sec-algorithms-playground` (they need the imports of ``direct.py``:
``AlgoBase``, ``AlgorithmFactory``, ``AlgoType``, ``LensSetup``, ``ModulatorType`` and ``numpy``). The first one needs
a mask applied to the intermediate plane to select an order of the grating.

What the user sees
------------------

``get_fields_to_plot`` returns the output field (amplitude and phase), the *metrics*, the modulator field and the
intermediate field if you have set ``self.intermediate_field``. The metrics are the *fitness* and the *efficiency*:
the properties ``fitness`` and ``efficiency`` of ``AlgoBase`` use the masks; reimplement them if your algorithm needs
another definition (and set ``self.fitness_name``, the label of the plot). The same goes for ``get_fields_to_plot``
to add your own data.

Developing the algorithm with the script
----------------------------------------

Restarting the application at each change of the code is slow. Develop the algorithm with the script described in
:ref:`sec-algorithms-playground` instead:

1. copy ``scripts/algorithm_playground.py`` and set ``ALGORITHM`` to the ``ALGO_NAME`` of your class, ``ALGORITHM_PARAMS``
   to the settings you want to test, the loaders of the input and target fields and, if needed, the masks;
2. run the cells; the cell creating the algorithm first calls ``reload_algorithm``, which imports again the module
   with your latest code;
3. look at the plots, edit the algorithm, run again **the cell creating the algorithm and the following ones**
   (not the settings): this takes a second;
4. when it behaves as expected, start the application once to check the settings and the interface.

The module must already be registered the first time: put it in ``algorithms/algorithms/`` of your clone of the
repository, or install your package with its entry point (below). ``list_available()`` of the helper module prints the
registered algorithms with their parameters. Note that the script does not run the interface, so what depends on it
(settings display, ``value_changed`` recomputing, threads) still has to be checked in the extension.

.. _sec-algorithms-external:

Algorithms provided by another package
--------------------------------------

Another Python package can add algorithms to the list of BeamShaping. It writes the classes as above, in a module
imported by nothing else, and declares the module in the entry point group
``pymodaq_plugins_beam_shaping.algorithms`` of its ``pyproject.toml``:

.. code-block:: toml

   [project.entry-points."pymodaq_plugins_beam_shaping.algorithms"]
   my_algorithms = "my_package.algorithms"

BeamShaping imports these modules when it starts, after its own algorithms. A package that cannot be imported is
reported in the log and ignored; its algorithms then do not appear in the list.
