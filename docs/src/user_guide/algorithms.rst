Algorithms for Beam Shaping
===========================

.. _sec-algorithms-overview:

Overview
--------
PyMoDAQ-BeamShaping provides **8 algorithms** for beam shaping, categorized into **4 families**. The algorithm is chosen
by its name in the *Algorithm* settings of the extension. The list is built when the extension starts: the algorithms of
BeamShaping itself, then the ones provided by other installed packages (see :ref:`sec-algorithms-external`).

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

.. _sec-algorithms-external:

Algorithms provided by other packages
-------------------------------------

Another Python package can add algorithms to the list of BeamShaping. It writes an algorithm class derived from
``AlgoBase``, registers it with the decorator ``AlgorithmFactory.register_algorithm()`` and declares the module
containing it in the entry point group ``pymodaq_plugins_beam_shaping.algorithms`` of its ``pyproject.toml``:

.. code-block:: toml

   [project.entry-points."pymodaq_plugins_beam_shaping.algorithms"]
   my_algorithms = "my_package.algorithms"

BeamShaping imports these modules when it starts, after its own algorithms. A package that cannot be imported is
reported in the log and ignored.


.. _sec-algorithms-playground:

Trying an algorithm outside of the extension
--------------------------------------------

The script ``scripts/algorithm_playground.py`` runs an algorithm without opening the extension: it is meant to be
executed in an IDE (Spyder, VS Code...) or turned into a notebook (``jupytext --to ipynb algorithm_playground.py``).
The file is made of cells delimited by ``# %%``. Copy it somewhere, edit the first cell, then run the cells one after
the other:

* ``SHAPER_PARAMS``: values overriding the default shaper of the configuration (``width``, ``height``, ``pixel_size``,
  ``modulator_type``...);
* ``ALGORITHM`` and ``ALGORITHM_PARAMS``: the name of the algorithm as shown in the extension and the values of its
  parameters, given by name (``'carrier_factor'``), with dots for parameters in a group (``'phase.load'``). An unknown
  name raises an error listing the possible ones. ``N_ITERATIONS`` and ``INITIAL_PHASE`` ('zero', 'random' or an array)
  complete the run;
* ``INPUT_LOADER`` / ``INPUT_PARAMS`` and ``TARGET_LOADER`` / ``TARGET_PARAMS``: the loaders of the
  :doc:`field loader <fields>` and their parameters, an image then a Laguerre-Gauss beam by default;
* ``APPLY_TARGET_MASK`` and ``APPLY_INTERMEDIATE_MASK``: set them to ``True`` to apply a mask (algorithms such as
  *DMD Lee* need the one of the intermediate plane), its region being given in um around the center of the field.

The next cells create the algorithm and the fields, apply the masks, run the algorithm and plot the output, the
modulator and the metrics with matplotlib, through the ``plot`` method of the data objects. The last cell gives the
results as ``Field`` objects. ``list_available()`` of the helper module
``pymodaq_plugins_beam_shaping.utilities.headless_algorithms`` prints the algorithms and the loaders with the names of
their parameters.

After editing the code of an algorithm, do not run the whole script again: run again the cell creating the algorithm
and the following ones. The cell starts with ``pg.reload_algorithm(ALGORITHM)``, which reloads the module of the
algorithm and registers the new class again (the factory would otherwise keep the old one). It is used for the first
run as well, so there is a single way of running. A base class defined in another module is not reloaded, do it
yourself with ``importlib.reload`` if you change it, and a syntax error in the algorithm raises while the previous
version stays usable.

.. note::

   The parameters of the algorithms are widgets, so a ``QApplication`` is needed. The helpers create it if there is none,
   no event loop is required. Matplotlib must be installed. The algorithm receives the same calls as in the extension
   through a minimal stand-in for it, but the script has not been tested on hardware.
