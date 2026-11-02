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

.. _sec-theory-amplitude-modulation:

Amplitude Modulation with Binary Holograms
------------------------------------------
Some modulators, such as the DMDs, can only switch each pixel on or off: they modulate the **amplitude** (a binary one),
not the phase. The field of a target amplitude :math:`A` and phase :math:`\phi` is then encoded in a **hologram**, a
grating of carrier :math:`\boldsymbol{\nu}` whose fringes are shifted by the phase and, for the methods that can,
whose contrast or width follows the amplitude. A filter in the Fourier plane of a 4f line selects one diffraction order,
which is the target field. The presentation follows the review :cite:t:`gutierrez-cuevas_binary_2024`, to which the
equation numbers refer.

**Grey off-axis hologram.** The ideal (grey levels, not feasible on a DMD) transmittance of the modulator is

.. math::
   T(\mathbf{r}) = \frac{1}{2} + \frac{A(\mathbf{r})}{2}\cos\left(2\pi\boldsymbol{\nu}\cdot\mathbf{r} - \phi(\mathbf{r})\right)
   \quad \text{(Eq. 5)}.

It is the sum of the zero order, and of the two first orders :math:`\frac{A}{4}e^{\pm i\phi}` at :math:`\pm\boldsymbol{\nu}`.
The order :math:`(-1, 0)`, at :math:`-\boldsymbol{\nu}` in the Fourier plane, carries the target field :math:`\frac{A}{4} e^{i\phi}`: it is the one
to filter to get the target field (the one at :math:`+\boldsymbol{\nu}` carries the opposite phase).

**Binary threshold.** The first binary hologram (:cite:t:`bryngdahl_interferograms_1968`) cuts the grey pattern at its
mean:

.. math::
   T(\mathbf{r}) = \frac{1}{2} + \frac{1}{2}\,\mathrm{sgn}\left[\cos\left(2\pi\boldsymbol{\nu}\cdot\mathbf{r} - \phi\right)\right]
   \quad \text{(Eq. 9)}.

A pixel is on where the cosine is positive whatever :math:`A`: the amplitude is lost and only the phase, coded in the
position of the fringes, is kept. This is a **phase-only** method.

**Parallel Lee hologram.** The width of the on fringes is made to follow the amplitude (:cite:t:`lee_binary_1974`,
:cite:t:`brown_complex_1966`): a pixel is on where

.. math::
   \cos\left(2\pi\boldsymbol{\nu}\cdot\mathbf{r} - \phi\right) > \cos(\pi q), \qquad A = \sin(\pi q)
   \quad \text{(Eq. 11)}.

Fringes of relative width :math:`q` have a first order of amplitude :math:`\sin(\pi q)/\pi = A/\pi` : the relation between the
amplitude and the width is not linear, and amplitude and phase are coded along the same direction, which couples
them (the number of amplitude levels is limited by the period of the grating).

**Orthogonal Lee hologram.** The phase is coded in the position of the fringes along :math:`\boldsymbol{\nu}` and the
amplitude in their height, along a direction :math:`\boldsymbol{\nu}_\perp` orthogonal to it (Eq. 16), so that the
two are independent. It is not implemented in the toolbox.

**Tilted lattices.** The carrier :math:`\boldsymbol{\nu} = (1/p_x, -1/p_y)` with :math:`p_y/p_x = k` an integer, tilts
the fringes on the pixel lattice, and gives more phase values for the same period. The review proposes
:math:`p_y = p_x^2` as a compromise. The aligned grating is the case :math:`\boldsymbol{\nu} = (1/p, 0)`.

**Superpixels.** In the Haskell and superpixel holograms the modulator is cut into blocks of :math:`p \times p`
pixels, each block being given the on/off pattern whose Fourier coefficient is the closest to the complex value of the
target (:cite:t:`goorden_superpixel-based_2014`). They reach more amplitude and phase values than the Lee holograms.
They are not available yet in the toolbox.

The algorithms of the toolbox that use these holograms are described in :ref:`sec-algo-amplitude-modulation`.
