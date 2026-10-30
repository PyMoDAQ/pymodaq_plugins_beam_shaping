Algorithm reference
===================

This page details every algorithm of the list of the extension (see :ref:`sec-algorithms-overview` for the overview
table): what it does, for which setup and the settings that appear in the *Algorithm* settings when it is selected.
Sizes of pixels in these settings follow the shaper (see :doc:`shapers`).

Settings shared by the algorithms
---------------------------------

Most algorithms start from an *initial phase* of the modulator, which is also a choice in the settings:

* **Random**: a random phase.
* **Quadratic**: a quadratic phase ``R (p² + q²) + D (p cos θ + q sin θ)`` (``p`` and ``q`` are the normalized pixel
  indexes, see `Bowman et al., Optics Express 25(10), 2017 <https://doi.org/10.1364/OE.25.011692>`_) with the groups *Quadratic
  Amplitude* (``Auto`` computes the X and Y amplitudes from the size of the target mask, ``X Quad.``, ``Y Quad.``,
  ``Coeff`` as a multiplicative coefficient) and *Linear Shift* (``Auto`` computes the shift from the position of the
  target mask, ``X Shift``, ``Y shift``).

*Direct* does not use an initial phase.

Direct
------

Sends the selected target field directly to the modulator: its phase, its amplitude or both depending on the type of
modulation of the shaper. No propagation model is involved (no lens) and the algorithm is not iterative.

*Settings*: none.

Diffractive
-----------

Creates an amplitude image with a **phase-only** modulator in a **4f** line with a circular filter in the Fourier plane
that removes the undiffracted light. Not iterative. Implements the five methods A to E discussed in
`Clark et al., Optics Express, 2016 <https://doi.org/10.1364/OE.24.006249>`_.

*Settings*:

* ``Gamma`` (default 4): period of the modulation grating, in pixels.
* ``Diffractive Models``: *Relative Amplitude* (method A), *Scattering* (B), *Davis* (C), *Bolduc* (D) or *Arrizon* (E).
* ``Order N`` (default 10).

OL2014 - Amplitude/Phase Checkerboard
-------------------------------------

Creates **amplitude and phase** images with a phase-only modulator in a **4f** line with a filter in the Fourier plane,
by encoding the complex field on a checkerboard (Mendoza-Yero et al., Optics Letters 39(7), 1740, 2014). Not iterative.

*Settings*:

* ``Mask block size (pxls)`` (default 5): size of the blocks of the checkerboard.
* ``amplitude divider`` (default 1).

Gerchberg-Saxton
----------------

The classic iterative phase retrieval (Gerchberg and Saxton, 1972) for an amplitude image with a phase-only modulator
in the Fourier plane of a lens (**2f**). The wavelength and the focal length of the lens are those of the experimental
setup.

*Settings*: none.

Projections
-----------

Gerchberg-Saxton with variants, **2f** setup, iterative.

* **Weighting**: weights the target amplitude with the difference to the calculated output amplitude
  (`Wu et al., Optics Express, 2021 <https://doi.org/10.1364/OE.413723>`_).
* **MRAF** (Mixed-Region Amplitude Freedom, `Pasienski and DeMarco, Optics Express, 2008
  <https://doi.org/10.1364/OE.16.002176>`_): the amplitude is imposed in a signal region and left free in the rest. A
  region of interest (rectangular or elliptical) has to be selected in the target plane.

*Settings*:

* ``Weighting`` (default off).
* ``Mixing ratio`` (default 0.5, between 0 and 1): the MRAF parameter. 1 is the standard Gerchberg-Saxton algorithm.

slmsuite Hologram
-----------------

Gerchberg-Saxton and weighted Gerchberg-Saxton methods computed by slmsuite, **2f** setup, iterative. Provided by
``pymodaq_plugins_slmsuite`` (:doc:`slmsuite`).

*Settings*: ``Method`` (GS, WGS-Leonardo, WGS-Kim, WGS-Nogrette, WGS-Wu, WGS-tanh), ``Iterations per step``, and the
settings of the chosen method (feedback exponent, feedback factor, iteration at which the phase is fixed) with the
defaults of slmsuite, see :doc:`slmsuite`.

Minimize and TorchOptim
-----------------------

Both minimize a **loss function** between the output and the target fields with respect to the phase of the modulator
(**2f** setup, iterative), based on `Bowman et al., Optics Express 25(10), 2017 <https://doi.org/10.1364/OE.25.011692>`_ (conjugate gradient
minimisation) and implemented with ``pytorch``. They are only listed if ``pytorch`` is installed
(``pip install pymodaq_plugins_beam_shaping[pytorch]``, which also installs ``pytorch-minimize`` used by *Minimize*).
The calculation runs on the GPU if one is available.

* **Minimize** uses the minimizers of ``pytorch-minimize``.
* **TorchOptim** uses the L-BFGS optimizer of ``pytorch``.

*Settings* (both):

* ``Max Iterations`` (default 100) and ``Tolerance`` (default 1e-9).
* ``Loss``: the loss function and, in *Loss Parameters*, its own settings (the value of the loss is displayed in
  ``Loss Value``).

  .. list-table::
     :header-rows: 1
     :widths: 30 70

     * - **Loss**
       - **Settings (default)**
     * - LeastSquares
       - none
     * - MSELoss
       - none
     * - SmoothL1Loss
       - ``Beta`` (0.5)
     * - LeastExponent
       - ``Loss exponent`` (4)
     * - Chicken
       - ``Power exponent`` (9), ``Sum exponent`` (2)
     * - ChickenArnaud
       - ``Ratio`` (1)
     * - LSQAmplitudePhase
       - ``Amplitude exponent`` (1), ``Phase exponent`` (1)

*Minimize* only: ``Method`` of the minimizer (default l-bfgs): bfgs, l-bfgs, cg, newton-cg, newton-exact, dogleg,
trust-ncg, trust-exact or trust-krylov.
