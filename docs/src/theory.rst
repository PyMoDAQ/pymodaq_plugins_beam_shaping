Theoretical Background
======================

.. _sec-theory-intro:

Introduction
------------
This section provides the **mathematical foundations** of beam shaping in PyMoDAQ-BeamShaping.
For an overview, see :ref:`sec-intro-overview`.

.. _sec-theory-planes:

Optical Planes
--------------
PyMoDAQ-BeamShaping distinguishes **four planes** in the optical setup:

.. list-table:: **Optical Planes**
   :header-rows: 1
   :widths: 30 70

   * - **Plane**
     - **Description**
   * - **Input**
     - Where the **incident field** :math:`U_{in}` is defined.
   * - **Modulator**
     - Where the **SLM** applies a constraint (e.g., phase modulation).
   * - **Intermediate**
     - **Fourier plane** in a 4f system (where filtering can be applied).
   * - **Output**
     - Where the **shaped field** :math:`U_{out}` is required to match the target.

In most cases, the **input** and **modulator** planes coincide physically.
In this situation, the "incident field" and the "modulated field" refer to the optical field defined on that same plane,
considered respectively **before modulation** (incident field) and **after interaction with the SLM** (modulated field).

For a visual representation of the optical planes, see {numref}`FIG-schema`.

.. _sec-theory-field-representation:

Optical Field Representation
----------------------------
In a plane perpendicular to the optical axis, the **complex field** of a quasi-monochromatic scalar optical field
at wavelength :math:`\lambda` is defined as:

.. math::
   U(\mathbf{r}_{k}) = A(\mathbf{r}_{k})\,e^{i\phi(\mathbf{r}_{k})},

where:
- :math:`\mathbf{r}_{k} = (x_{k}, y_{k})`: Transverse coordinates in plane :math:`k`.
- :math:`A(\mathbf{r}_{k}) \ge 0`: **Amplitude** (real and non-negative).
- :math:`\phi(\mathbf{r}_{k})`: **Phase** (in radians).

.. _sec-theory-problem-formulation:

Beam Shaping as an Inverse Problem
----------------------------------
The **computational beam shaping task** can be stated as an **inverse problem**:
Find a set of parameters :math:`\theta` such that the propagated field :math:`U_{out}` satisfies a desired constraint in the output plane.

The two common cases are:

1. **Intensity-Only Shaping** (Equation 4 in the article):

   .. math::
      |U_{out}(\mathbf{r}_{out})|^2 \approx I_{\mathrm{target}}(\mathbf{r}_{out}).

2. **Complex-Field Shaping** (Equation 5 in the article):

   .. math::
      U_{out}(\mathbf{r}_{out}) \approx U_{\mathrm{target}}(\mathbf{r}_{out}).

In either case, the feasible solutions are restricted by:
- The **modulator physics** encoded in :math:`\mathcal{M}`.
- The **optical configuration** encoded in :math:`\mathcal{P}`.
- The **limitations of the algorithm** used to solve the inverse problem.

.. _sec-theory-modulators:

Types of Spatial Light Modulation
---------------------------------
.. _sec-phase-only:

**Phase-Only Modulation**
   The field immediately after the modulator can be written as (Equation 5 in the article):

   .. math::
      U_m(\mathbf{r}_{m}) = A_{\mathrm{in}}(\mathbf{r}_{m})\,e^{i\phi(\mathbf{r}_{m})},

   where :math:`A_{\mathrm{in}} = |U_{\mathrm{in}}|` is the **incident amplitude** (preserved),
   and :math:`\phi(\mathbf{r}_{m})` is the **phase pattern** applied by the modulator.

   **Implementation**:

   - **Liquid-Crystal SLMs** (e.g., Holoeye Pluto, Hamamatsu LCOS): Each pixel modulates the optical path length
     via voltage-controlled liquid crystal orientation.

   **Transfer Function** (Equation 12 in the article):
   The modulator transformation :math:`\mathcal{M}` is modeled as a pointwise multiplication by a unitary complex transfer function :math:`T(\mathbf{r})`:

   .. math::
      U_m(\mathbf{r}_{m}) = T(\mathbf{r}_{m})\,U_{\mathrm{in}}(\mathbf{r}_{m}).

.. _sec-amplitude-only:

**Amplitude-Only Modulation**
   The field immediately after the modulator can be written as (Equation 16 in the article):

   .. math::
      U_m(\mathbf{r}_{m}) = U_{\mathrm{in}}(\mathbf{r}_{m})\, t(\mathbf{r}_{m}),

   where :math:`t(\mathbf{r}_{m})` is a **real transmission coefficient** (0 ≤ t ≤ 1).

.. _sec-binary-amplitude:

**Binary Amplitude Modulation (DMD)**
   In the case of **Digital Micromirror Devices (DMD)**, the transmission coefficient can only take the values 0 or 1 (Equation 17 in the article):

   .. math::
      U_m(\mathbf{r}_{m}) \in \{0,1\}.

   **Use Case**:
   Often used with a **4f system** to encode **effective complex modulation** in a selected diffraction order.

.. _sec-complex-modulation:

**Complex Modulation**
   Uses **multiple modulators** (e.g., one for amplitude, one for phase) to achieve **full complex control**:

   .. math::
      U_m(\mathbf{r}_{m}) = A_{\mathrm{target}}(\mathbf{r}_{m})\,e^{i\phi_{\mathrm{target}}(\mathbf{r}_{m})}.

   **Limitations**:
   - Requires **precise alignment** of modulators.
   - Higher cost (multiple devices).

.. _sec-theory-fresnel:

**Fresnel Propagation (Future Work)**
   Fresnel propagation (near-field) is **not yet implemented** in the current version of the toolbox,
   but the architecture supports its future integration. The mathematical formulation is (Equation 8 in the article):

   .. math::
      U_{out}(\mathbf{r}_{out}) = \frac{e^{ikz}}{i\lambda z}\,
      \exp\!\left(\frac{ik}{2z}\|\mathbf{r}_{out}\|^2\right) \times
      \mathcal{F}\!\left\{ U_m(\mathbf{r}_{m})\, \exp\!\left(\frac{ik}{2z}\|\mathbf{r}_{m}\|^2\right) \right\}

   where:
   - :math:`k = 2\pi/\lambda`: Wave number.
   - :math:`z`: Propagation distance.

   **Use Case**:
   Assessing the **robustness** of shaped fields (e.g., how the pattern degrades when the observation plane is displaced).