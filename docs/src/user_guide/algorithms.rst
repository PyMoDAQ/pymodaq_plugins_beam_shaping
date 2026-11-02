Algorithms for Beam Shaping
===========================

.. _sec-algorithms-overview:

Overview
--------
PyMoDAQ-BeamShaping provides **11 algorithms** for beam shaping, categorized into **4 families**. The algorithm is chosen
by its name in the *Algorithm* settings of the extension. The list is built when the extension starts: the algorithms of
BeamShaping itself, then the ones provided by other installed packages (see :doc:`custom_algorithm`).

.. list-table:: **Algorithms, as named in the interface**
   :header-rows: 1
   :widths: 17 14 7 9 9 9 35

   * - **Family**
     - **Name in the interface**
     - **Setup**
     - **Iterative**
     - **Amplitude**
     - **Phase**
     - **Remarks**
   * - Direct application
     - Direct
     - no lens
     - ❌
     - ✅
     - ✅
     - Sends the selected target field to the modulator (phase, amplitude or both depending on the shaper).
   * - Direct diffractive modulation
     - Diffractive
     - 4f
     - ❌
     - ✅
     - ❌
     - Amplitude images with a phase-only modulator and a filter in the Fourier plane, several diffractive models
       (:cite:t:`Clark2016`).
   * - Direct diffractive modulation
     - OL2014 - Amplitude/Phase Checkerboard
     - 4f
     - ❌
     - ✅
     - ✅
     - Encodes phase and amplitude with a checkerboard (:cite:t:`mendoza-yero_encoding_2014`).
   * - Direct diffractive modulation
     - Binary Threshold
     - 4f
     - ❌
     - ❌
     - ✅
     - Binary hologram for amplitude modulators (DMD): the phase is encoded in a binary grating and one diffraction order
       is filtered in the Fourier plane (:cite:t:`bryngdahl_interferograms_1968`).
   * - Direct diffractive modulation
     - Parallel Lee
     - 4f
     - ❌
     - ✅
     - ✅
     - Lee hologram for amplitude modulators (DMD): amplitude and phase are encoded in the width and the position of the
       fringes of a binary grating (:cite:t:`lee_binary_1974`).
   * - Direct diffractive modulation
     - Superpixel
     - 4f
     - ❌
     - ✅
     - ✅
     - Superpixel hologram for amplitude modulators (DMD): blocks of mirrors whose on / off pattern gives a complex
       value (:cite:t:`goorden_superpixel-based_2014`).
   * - Iterative alternating projections
     - Gerchberg-Saxton
     - 2f
     - ✅
     - ✅
     - ❌
     - Classic phase retrieval (:cite:t:`gerchberg_practical_1972`).
   * - Iterative alternating projections
     - Projections
     - 2f
     - ✅
     - ✅
     - ❌
     - Gerchberg-Saxton with options: weighting (:cite:t:`Wu2021`) and Mixed-Region
       Amplitude Freedom (MRAF, :cite:t:`pasienski_high-accuracy_2008`) with a region of interest.
   * - Iterative alternating projections
     - slmsuite Hologram
     - 2f
     - ✅
     - ✅
     - ❌
     - GS and weighted GS methods (WGS-Leonardo, -Kim, -Nogrette, -Wu, -tanh), optionally on the GPU. Provided by
       ``pymodaq_plugins_slmsuite``, listed once installed with its ``beamshaping`` extra
       (see :doc:`slmsuite`).
   * - Iterative cost function minimization
     - Minimize
     - 2f
     - ✅
     - ✅
     - ✅
     - Minimization of a loss function with ``pytorch`` and ``pytorch-minimize``
       (:cite:t:`bowman_high-fidelity_2017`). The modulated quantity depends on the loss.
   * - Iterative cost function minimization
     - TorchOptim
     - 2f
     - ✅
     - ✅
     - ✅
     - Minimization of a loss function with the L-BFGS optimizer of ``pytorch`` (same reference as *Minimize*).

The settings of each algorithm are detailed in :doc:`algorithm_reference`.

With *Minimize* and *TorchOptim*, the losses that shape the amplitude only (*LeastSquares*, *MSELoss*, *SmoothL1Loss*,
*LeastExponent*) work well. The three losses that try to shape the amplitude **and** the phase (*Chicken*,
*ChickenArnaud*, *LSQAmplitudePhase*, after :cite:t:`bowman_high-fidelity_2017`) give results that are not satisfactory yet and do not
seem to reproduce the ones of the paper.

*Minimize* and *TorchOptim* are only listed if ``pytorch`` is installed (``pip install
pymodaq_plugins_beam_shaping[pytorch]``). **Setup** is the propagation model assumed between the modulator and the
output plane (see :ref:`sec-algorithms-propagation`).

.. _sec-algorithms-theory:

Theoretical Formulation
------------------------
Beam shaping is formulated as an **inverse problem**:
Find a **modulation pattern** ( :math:`\theta` ) (e.g., phase mask for an SLM) such that the **output field**
(:math:`U_{out}`) matches a **target field** (:math:`U_{\text{target}}`).

.. math::
   U_m(\mathbf{r}_{m}) = \mathcal{M}\!\left(U_{in}(\mathbf{r}_{in}); \theta\right),
   \quad
   U_{out}(\mathbf{r}_{out}) = \mathcal{P}\{U_m(\mathbf{r}_{m})\},

where:

- :math:`\mathcal{M}`: **Modulator transformation** (e.g., phase-only, amplitude-only).
- :math:`\mathcal{P}`: **Propagation operator** (e.g., 2f, 4f).
- :math:`\theta`: **Control parameters** (e.g., SLM phase pixels).


.. _sec-algorithms-propagation:

Propagation Models
------------------
The **propagation operator** :math:`\mathcal{P}` depends on the optical setup.

.. _sec-2f-config:

**2f Configuration (Fraunhofer Diffraction)**
+++++++++++++++++++++++++++++++++++++++++++++

   The field in the **back focal plane** of a lens is proportional to the **Fourier transform** of the field in the **modulator plane**:

   .. math::
      U_{out}(\mathbf{r}_{out}) \propto \mathcal{F}\{U_m(\mathbf{r}_{m})\},

   where :math:`\mathcal{F}` is the **2D Fourier Transform** (implemented via FFT).

.. _sec-4f-config:

**4f Configuration (Fourier-Plane Filtering)**
++++++++++++++++++++++++++++++++++++++++++++++

   Two lenses separated by the sum of their focal lengths. The first lens maps the **modulator plane** to a **Fourier plane** (where filtering can be applied). The second lens transforms the filtered spectrum to the **output plane**:

   .. math::
      U_{out} = \mathcal{F}^{-1}\left\{ H(\mathbf{k})\,\mathcal{F}\{U_m\} \right\},

   where :math:`H(\mathbf{k})` is an **aperture or filter** in the Fourier plane.

.. note::
   **Fresnel propagation** (near-field) is **not yet implemented** in the current version of the toolbox.
   The architecture supports its future integration (see :ref:`sec-theory-fresnel`).

.. _sec-algorithms-iterative:

Iterative Alternating Projections (IAP)
---------------------------------------

IAP algorithms alternate between **modulator constraints** (e.g., phase-only) and **target constraints** (e.g., intensity-only in a ROI).

**Mathematical Formulation** (Equation 10 in the article):

.. math::
   U_m^{(k+1)} = \Pi_M\!\left( \mathcal{P}^{-1}\left[ \Pi_T\!\left( \mathcal{P}\{U_m^{(k)}\} \right) \right] \right),

where:

- :math:`\Pi_M`: Projection onto the **modulator constraint** (e.g., phase-only).
- :math:`\Pi_T`: Projection onto the **target constraint** (e.g., intensity-only in a ROI).

**Examples**:
- **Gerchberg-Saxton (GS)** (Equation 9 in the article):

  .. math::
     U_{out}(\mathbf{r}_{out}) \leftarrow \sqrt{I_{\mathrm{target}}(\mathbf{r}_{out})} \exp\!\left(i\,\arg(U_{out}(\mathbf{r}_{out}))\right).

- **MRAF** (Equation 11 in the article):

.. math::
   |U_{\mathrm{out}}^{(n+1)}(\mathbf{r}_{out})| =
   \begin{cases}
   m \sqrt{I_{\mathrm{target}}(\mathbf{r}_{out})} & \text{in SR}, \\
   (1-m) \sqrt{I_{\mathrm{out}}^{(n)}(\mathbf{r}_{out})} & \text{in NR},
   \end{cases}
   \quad \text{where } m \in [0,1] \text{ is the mixing parameter.}


.. _sec-algorithms-metrics:

Quality Metrics
---------------
PyMoDAQ-BeamShaping provides **quantitative metrics** to evaluate beam-shaping performance, either as the closeness
to the target (NRMSE or Fidelity) and the shaping efficiency. :numref:`FIG-metrics` displays calculated and measured
shaping for the MRAF algorithm using different initial phase type and mixing parameter.

**Intensity-Only Shaping**:
+++++++++++++++++++++++++++

- **Normalized Root Mean-Squared Error (NRMSE)** (Equation 18 in the article):

  .. math::
     \epsilon_\mathrm{rms} = \sqrt{ \frac{\sum_{\mathbf{r}\in S}\left(I_{out}(\mathbf{r}_{out}) - I_{\mathrm{target}}(\mathbf{r}_{out})\right)^2}{\sum_{\mathbf{r}_{out}\in S} I_{\mathrm{target}}(\mathbf{r}_{out})^2} }.

**Complex-Field Shaping**:
++++++++++++++++++++++++++

- **Field Fidelity** (Equation 19 in the article):

  .. math::
     \mathcal{F} = \frac{\left|\sum_{\mathbf{r}_{out}\in S} U_{\mathrm{target}}^*(\mathbf{r}_{out})\,U_{out}(\mathbf{r}_{out})\right|^2}{\sum_{\mathbf{r}_{out}\in S} I_{\mathrm{target}}(\mathbf{r}_{out})^2}.

- **Normalized Fidelity Error** (Equation 20 in the article):

  .. math::
     \epsilon_\mathcal{F} = \sqrt{1 - \mathcal{F}}.

**Shaping Efficiency** (Equation 21 in the article):
++++++++++++++++++++++++++++++++++++++++++++++++++++

.. math::
   \eta = \frac{\sum_{\mathbf{r}_{out}\in S} I_{out}(\mathbf{r}_{out})}{\sum_{\mathbf{r}_{in}} I_{in}(\mathbf{r}_{in})}.

.. _FIG-metrics:

.. figure:: /_images/measurement_amplitude.png
   :alt: Intensity-Only Shaping Results
   :width: 100%
   :align: center


   Results of intensity-only shaping for two targets (CEMES logo and butterfly image)
   using the **MRAF algorithm** (100 iterations). Each column corresponds to a different:
   **Mixing parameter** m and/or **Initial phase type** (quadratic or random). Metrics
   (NRMSE, Efficiency) are printed on the images.



.. note::
   The metrics (NRMSE, Fidelity, Efficiency) are **automatically saved** in the ``.h5beam`` file under
   ``/RawData/Algorithm/``. See :ref:`h5beam-structure` for details.

Algorithms provided by other packages
-------------------------------------

Another Python package can add algorithms to the list of BeamShaping, see :doc:`custom_algorithm` for how to write one
and how to declare it.


.. _sec-algorithms-playground:

Trying an algorithm outside of the extension
--------------------------------------------

The script ``scripts/algorithm_playground.py`` runs an algorithm without opening the extension: it is meant to be
executed in an IDE (Spyder, VS Code...) or turned into a notebook (``jupytext --to ipynb algorithm_playground.py``).
The file is made of cells delimited by ``# %%``, each one starting with its settings. Copy it somewhere, then run the
cells one after the other, editing the settings on the way:

* *Shaper*: ``SHAPER_PARAMS``, values overriding the default shaper of the configuration (``width``, ``height``,
  ``pixel_size``, ``modulator_type``...), and ``PLOT_BACKEND``, ``'matplotlib'`` or ``'qt'`` (see below);
* *Input field* and *Target field*: ``INPUT_LOADER`` / ``INPUT_PARAMS`` and ``TARGET_LOADER`` / ``TARGET_PARAMS``, the
  loaders of the :doc:`field loader <fields>` and their parameters, a Gaussian beam for the input and an image for the
  target by default. Each field is plotted once loaded (the target with the axes of the modulator plane, the algorithm
  scales it to the target plane: ``pg.plot_field(pg.get_target_field(algo))`` shows it after the next cell);
* *Algorithm*: ``ALGORITHM`` and ``ALGORITHM_PARAMS``, the name of the algorithm as shown in the extension and the
  values of its parameters, given by name (``'carrier_factor'``), with dots for parameters in a group
  (``'phase.load'``). An unknown name raises an error listing the possible ones. ``N_ITERATIONS`` completes the run, and
  ``INITIAL_PHASE`` / ``INITIAL_PHASE_PARAMS`` give the initial phase as chosen in the extension, from the initial
  phases factory (``'FlatPhase'``, ``'RandomPhase'``, ``'QuadraticPhase'``...) with its parameters, or a 2D array of the
  shape of the fields;
* *Snap*: ``pg.snap`` runs one step of the algorithm without any mask and plots the intermediate plane of 4f setups
  (intensity in log scale), to see where the mask has to be placed;
* *Masks*: set ``APPLY_TARGET_MASK`` or ``APPLY_INTERMEDIATE_MASK`` to ``True`` to apply a mask (algorithms such as
  *Binary Threshold*, *Parallel Lee* and *Superpixel* need the one of the intermediate plane), its region being given in um around the center of the field (``None``: the default region
  of the extension, centered and covering 2/3 of the effective area of the SLM in the plane, printed to be edited). The cell
  draws the outline of the intermediate mask on the plot of the snap, which is updated (not created again): run it
  again until the mask is right.

The last cells run the algorithm, plot an overview as in the extension, then the output field and the intermediate
plane of 4f setups (its intensity in log scale), and give the results as ``Field`` objects. The overview shows the
output, modulator and intermediate planes with their amplitude and phase, and the metrics: with ``'qt'`` a dock per field
titled with its name, each holding the viewers of the amplitude and of the phase, with ``'matplotlib'`` one figure made
of subplots, a row per field. Running the cell again updates the overview instead of creating a new one.
``list_available()`` of the helper module ``pymodaq_plugins_beam_shaping.utilities.headless_algorithms`` prints the
algorithms, the initial phases and the loaders with the names of their parameters.

Each field is plotted with ``pg.plot_field``, whose arguments are written in the script so as to be edited:

* ``log``: the intensity in log10 instead of the amplitude, down to ``decades`` (6 by default) below its maximum;
* ``clim`` and ``phase_clim``: the (min, max) of the colors of the amplitude (or log10 intensity) and of the phase;
* ``xlim`` and ``ylim``: a zoom, (min, max) in um, the axes of the plots being in um with their origin at the center of the
  field, as for the masks;
* ``mask``: (region, type) as for the masks, its outline is drawn;
* ``figure``: what a previous call returned (matplotlib ``Figure`` or qt ``ViewerDispatcher``), updated instead of
  creating a new plot. With the inline backend (static images), the updated figure is displayed again;
* ``backend``: with ``'matplotlib'`` the figure is returned, both axes at the same scale, to be customized further
  (``pg.customize(figure, clims, xlim, ylim)`` does the above on any figure). With ``'qt'``, the interactive viewers of
  PyMoDAQ are opened instead, amplitude and phase side by side (``field.split_as_dte().plot('qt')``): the options above
  give their starting state (``pg.customize_qt``), then zoom, color levels, ROI... are changed with the mouse. They need a Qt event
  loop in the console: in Spyder, set *Preferences > IPython console > Graphics > Backend* to *Qt* or *Automatic*.

After editing the code of an algorithm, do not run the whole script again: run again the *Algorithm* cell
and the following ones. The cell starts with ``pg.reload_algorithm(ALGORITHM)``, which reloads the module of the
algorithm and registers the new class again (the factory would otherwise keep the old one). It is used for the first
run as well, so there is a single way of running. A base class defined in another module is not reloaded, do it
yourself with ``importlib.reload`` if you change it, and a syntax error in the algorithm raises while the previous
version stays usable.

.. note::

   The parameters of the algorithms are widgets, so a ``QApplication`` is needed. The helpers create it if there is none,
   no event loop is required. Matplotlib must be installed. The algorithm receives the same calls as in the extension
   through a minimal stand-in for it, but the script has not been tested on hardware.
