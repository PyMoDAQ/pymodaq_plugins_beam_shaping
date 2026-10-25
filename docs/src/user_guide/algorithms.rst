Algorithms for Beam Shaping
===========================

.. _sec-algorithms-overview:

Overview
--------
PyMoDAQ-BeamShaping implements **8 algorithms** for beam shaping, categorized into **3 families**:

.. list-table:: **Implemented Algorithms**
   :header-rows: 1
   :widths: 25 10 10 10 10 35

   * - **Algorithm Family**
     - **Setup**
     - **Iterative**
     - **Amplitude**
     - **Phase**
     - **Remarks**
   * - Direct Application
     - 2f
     - ❌
     - ✅
     - ✅
     - Direct application of target phase/amplitude.
   * - Direct Diffractive Modulation
     - 4f
     - ❌
     - ✅
     - ❌
     - Various implementations (Clark 2016).
   * - Direct Diffractive Modulation (CheckerBoard)
     - 4f
     - ❌
     - ✅
     - ✅
     - Encodes phase+amplitude (Mendoza-Yero 2014).
   * - Gerchberg-Saxton (GS)
     - 2f
     - ✅
     - ✅
     - ❌
     - Classic phase retrieval (Gerchberg 1972).
   * - Weighted Gerchberg-Saxton
     - 2f
     - ✅
     - ✅
     - ❌
     - Improved convergence (Wu 2021).
   * - MRAF
     - 2f
     - ✅
     - ✅
     - ❌
     - Mixed-Region Amplitude Freedom (Pasienski 2008).
   * - Iterative Cost Function Minimization (PyTorch)
     - 2f
     - ✅
     - ✅
     - ✅
     - Gradient-based optimization.
   * - Iterative Cost Function Minimization (Scipy)
     - 2f
     - ✅
     - ✅
     - ✅
     - Scipy-based optimization.

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
   ``/RawData/Algorithm/``. See :numref:`sec-h5beam-structure` for details.

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
