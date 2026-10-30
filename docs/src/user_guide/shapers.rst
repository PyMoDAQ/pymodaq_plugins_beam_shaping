Shapers (SLM) and the Shaper actuator
=====================================

.. _sec-shapers-overview:

The Shaper actuator
-------------------

The extension sends the computed mask to the actuator named **Shaper** in the Dashboard (a ``DAQ_Move`` module). Any
instrument plugin can be used, as long as its actuator accepts a 2D array of the size of the modulator as target
(a phase in radians, or grey levels when the data carries the attribute ``as_grey_levels=True``).

The extension asks the actuator itself what the modulator is, once the actuator is initialized: number of pixels, size of
the pixels, name, type of modulation (phase, amplitude or both) and whether the shaper has an internal calibration
(conversion of a phase into grey levels done by the driver). This information is given by two read-only groups of
settings of the actuator, ``shaper_geometry`` and ``shaper_properties``, defined in the
``pymodaq_plugins_utils.hardware.shaper`` module of
`pymodaq_plugins_utils <https://github.com/PyMoDAQ/pymodaq_plugins_utils>`_ (version 5.3.4 or later). A plugin that
wants to be used as a Shaper only needs to add these groups to its parameters (``shaper_params()``) and to fill them in
``ini_stage`` (``fill_shaper_settings``); it does not depend on BeamShaping.

If the actuator is not initialized or does not provide these groups, the extension falls back on the SLM described in
the configuration file of BeamShaping (``SLM`` section).

The choice *use internal calibration* of the ``shaper_properties`` group is the one of the user: when checked (default
if the shaper has an internal calibration), the phase is sent in radians and converted by the driver, otherwise it is
converted to grey levels with the calibration file of the :doc:`calibration` of BeamShaping.

.. _sec-shapers-list:

Available shapers
-----------------

.. list-table:: **Instrument plugins usable as Shaper**
   :header-rows: 1
   :widths: 28 22 50

   * - **Actuator**
     - **Package**
     - **Remarks**
   * - MockShaper
     - pymodaq_plugins_beam_shaping
     - Simulated shaper using the SLM of the configuration file. For tests without hardware.
   * - Holoeye, HoloeyeFile, HoloeyeSplitScreen, HoloeyeMock
     - `pymodaq_plugins_holoeye <https://github.com/PyMoDAQ/pymodaq_plugins_holoeye>`_
     - Holoeye SLMs, with the SLM Display SDK 3 or 4. The phase is converted to grey levels by the SDK (internal
       calibration). *HoloeyeMock* needs no hardware.
   * - Slmsuite, SlmsuiteSimulated, SlmsuiteMeadowlark, SlmsuiteHoloeye
     - `pymodaq_plugins_slmsuite <https://github.com/PyMoDAQ/pymodaq_plugins_slmsuite>`_
     - Any SLM supported by *slmsuite*: Holoeye, Meadowlark, Santec, Hamamatsu, mirrored screens... (see below).

.. _sec-shapers-slmsuite:

slmsuite
--------

`slmsuite <https://github.com/holodyne/slmsuite>`_ is an open source Python package (MIT license, *slmsuite
Developers*, maintained by Holodyne Labs, `documentation <https://slmsuite.holodyne.com/>`_) for the control of spatial
light modulators and the computation of holograms. If you use it through BeamShaping, please cite slmsuite (see the
reference to use on its project page) together with this package.

The package `pymodaq_plugins_slmsuite <https://github.com/PyMoDAQ/pymodaq_plugins_slmsuite>`_ makes it available in
PyMoDAQ:

* **Shaper actuators** for the SLMs supported by slmsuite, with the interface described above.
* **The slmsuite Hologram algorithm** in the list of algorithms of BeamShaping (GS and weighted GS methods, see
  :ref:`sec-algorithms-list`), installed with::

    pip install pymodaq_plugins_slmsuite[beamshaping]

The vendor driver of the SLM has to be installed separately (see the slmsuite documentation).
