Shapers (SLM) and the Shaper actuator
=====================================

.. _sec-shapers-overview:

The Shaper actuator
-------------------

The extension sends the computed mask to the actuator named **Shaper** in the Dashboard (a ``DAQ_Move`` module). Any
instrument plugin can be used, as long as its actuator accepts a 2D array of the size of the modulator as target
(a phase in radians, or grey levels when the data carries the attribute ``as_grey_levels=True``).

The modulator can be of several kinds. Most spatial light modulators (SLM) are **phase only** (liquid crystal on silicon,
LCOS), but a shaper can also be **amplitude only**, such as a digital micromirror device (DMD) or other micromirror
arrays, or able to modulate both. The mask sent to the actuator is then a phase for a phase modulator and an amplitude
(or the binary pattern of a DMD) for an amplitude modulator, as declared by the ``modulator_type`` of the shaper
(see below). The list of algorithms of the extension only proposes those that can compute a mask for the modulator of
the shaper: each algorithm declares the modulators it supports in its ``MODULATOR_TYPES`` class attribute (a tuple of
``ModulatorType``, phase only by default), and a shaper modulating both phase and amplitude accepts any algorithm. See
:doc:`algorithms`.

The extension asks the actuator itself what the modulator is, once the actuator is initialized: number of pixels, size of
the pixels, name, type of modulation (phase, amplitude or both) and whether the shaper has an internal calibration
(conversion of a phase into grey levels done by the driver). This information is given by two read-only groups of
settings of the actuator, ``shaper_geometry`` and ``shaper_properties``, defined in the
``pymodaq_plugins_utils.hardware.shaper`` module of
`pymodaq_plugins_utils <https://github.com/PyMoDAQ/pymodaq_plugins_utils>`_ (version 5.3.4 or later). A plugin that
wants to be used as a Shaper only needs to add these groups to its parameters (``shaper_params()``) and to fill them in
``ini_stage`` (``fill_shaper_settings``); it does not depend on BeamShaping.

The shaper is read from the actuator when the experiment (preset) is set and whenever the actuator is initialized, and the
fields (input, target) are rebuilt for its number of pixels and pixel size. There is no list of shapers to configure. If
the actuator is absent, not initialized or does not provide these groups, the extension uses a **default shaper**, the
same for all the shapers, described in the ``[default_shaper]`` section of the configuration file of BeamShaping
(``name``, ``width``, ``height``, ``pixel_size`` in µm, ``has_internal_calibration``,
``modulator_type``). By default: 1920 x 1080 pixels of 8 µm, phase modulation, no internal calibration. Edit it there
for an instrument whose plugin does not tell what it is.

The choice *use internal calibration* is a preference of BeamShaping (``use_internal_calibration`` in the
``[calibration]`` section, checked by default). When the shaper has an internal calibration, the extension imposes
this preference to the setting of the same name of the ``shaper_properties`` group of the actuator, at its start, when
the experiment is set, when the actuator is initialized and when the preferences change. If it differs, the setting of
the actuator is overwritten and a warning is logged. When it is checked, the phase is sent in radians and converted by
the driver, otherwise it is converted to grey levels with the calibration file of the :doc:`calibration` of
BeamShaping. A shaper without internal calibration is never concerned.

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
     - Simulated shaper using the default shaper of the configuration file. For tests without hardware.
   * - Holoeye, HoloeyeFile, HoloeyeSplitScreen, HoloeyeMock
     - `pymodaq_plugins_holoeye <https://github.com/PyMoDAQ/pymodaq_plugins_holoeye>`_
     - Holoeye SLMs, with the SLM Display SDK 3 or 4. The phase is converted to grey levels by the SDK (internal
       calibration). *HoloeyeMock* needs no hardware.
   * - Slmsuite, SlmsuiteSimulated, SlmsuiteMeadowlark, SlmsuiteHoloeye
     - `pymodaq_plugins_slmsuite <https://github.com/PyMoDAQ/pymodaq_plugins_slmsuite>`_
     - Any SLM supported by *slmsuite*: Holoeye, Meadowlark, Santec, Hamamatsu, mirrored screens... (see :doc:`slmsuite`).

.. _sec-shapers-slmsuite:

slmsuite
--------

Any SLM supported by `slmsuite <https://github.com/holodyne/slmsuite>`_ can be used as Shaper through the actuators of
``pymodaq_plugins_slmsuite``. See the page :doc:`slmsuite`.
