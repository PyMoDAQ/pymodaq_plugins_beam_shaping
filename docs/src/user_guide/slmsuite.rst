slmsuite
========

.. _sec-slmsuite:

`slmsuite <https://github.com/holodyne/slmsuite>`_ is an open source Python package (MIT license, *slmsuite
Developers*, maintained by Holodyne Labs, `documentation <https://slmsuite.holodyne.com/>`_) for the control of spatial
light modulators (SLM) and the computation of holograms. If you use it through BeamShaping, please cite slmsuite (see
the reference to use on its project page) together with this package.

The package `pymodaq_plugins_slmsuite <https://github.com/PyMoDAQ/pymodaq_plugins_slmsuite>`_ makes it available in
PyMoDAQ, for the two roles it plays in BeamShaping: the **Shaper** (hardware) and an **algorithm** (computation).

Installation
------------

::

    pip install pymodaq_plugins_slmsuite[beamshaping]

The ``beamshaping`` extra installs BeamShaping together with the plugin; without it the actuators work but the algorithm
is not available. The driver (SDK) of the SLM has to be installed separately, see the slmsuite documentation of each
manufacturer.

.. _sec-slmsuite-shaper:

Shaper actuators
----------------

All the actuators follow the interface of the Shaper described in :doc:`shapers`: the target is a 2D array of the size of
the SLM (or one value spread over the SLM), displayed as a **phase in radians** converted to grey levels by slmsuite
(wrapping, look-up table, wavefront correction if loaded), or as raw **grey levels** if the ``Input as grey levels``
setting is checked or the data carries ``as_grey_levels=True``.

* **Slmsuite**: generic, choose the slmsuite class (``SLM type``) and give its constructor arguments as a Python
  dictionary
* **SlmsuiteSimulated**: simulated SLM of slmsuite, no hardware needed
* **SlmsuiteMeadowlark**: Meadowlark SLM (Windows only, Blink SDK)
* **SlmsuiteHoloeye**: Holoeye SLM (SLM Display SDK)

Name the actuator **Shaper** in the Dashboard. It tells the extension the number of pixels, the size of the pixels and
whether the SLM has an internal calibration: the Meadowlark SLMs (look-up table loaded from the hardware) or any SLM for
which slmsuite knows a look-up table. The working wavelength is a setting of the actuator. The Meadowlark and Holoeye
actuators have been validated on real devices by the maintainer.

.. _sec-slmsuite-algorithm:

The slmsuite Hologram algorithm
-------------------------------

Once installed, ``slmsuite Hologram`` appears in the list of the algorithms of BeamShaping
(:ref:`sec-algorithms-overview`). It computes the phase with ``slmsuite.holography.algorithms.Hologram.optimize``, in the
Fourier plane of a lens (2f setup, as for *Gerchberg-Saxton*): the amplitude of the input beam is the nearfield
amplitude and the target amplitude is the farfield one. It is iterative: each step runs ``Iterations per step``
iterations of the chosen ``Method`` and keeps the state of the optimization (weights, fixed farfield phase for WGS-Kim)
from step to step. Changing the input beam, the target or the initial phase restarts the optimization.

.. list-table:: **Methods**
   :header-rows: 1
   :widths: 18 40 42

   * - **Method**
     - **Reference**
     - **Specific settings (default)**
   * - GS
     - Gerchberg-Saxton
     - none
   * - WGS-Leonardo
     - https://doi.org/10.1364/OE.15.001913
     - ``Feedback exponent`` (0.8)
   * - WGS-Kim
     - https://doi.org/10.1364/OL.44.003178
     - ``Feedback exponent`` (0.8), ``Fix phase at iteration`` (10)
   * - WGS-Nogrette
     - https://doi.org/10.1103/PhysRevX.4.021034
     - ``Feedback factor`` (0.1)
   * - WGS-Wu
     - https://doi.org/10.1364/OE.413723
     - ``Feedback exponent`` (0.5)
   * - WGS-tanh
     - weights updated with a hyperbolic tangent
     - ``Feedback factor`` (0.2), ``Feedback exponent`` (0.5)

The defaults are the ones of slmsuite, restored when the method is changed. The weighted (WGS) methods give a more
uniform intensity on a set of spots or regions than GS. The GPU is used if ``cupy`` is installed. The conjugate gradient
method of slmsuite is not exposed yet. See the slmsuite documentation (``Hologram.optimize``) for the parameters.
