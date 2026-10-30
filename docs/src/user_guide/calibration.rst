.. |equalizer| image:: /_static/icons/equalizer.png
   :height: 20pt
   :alt: Calibration
   :align: middle

.. |ink_eraser| image:: /_static/icons/ink_eraser.png
   :height: 20pt
   :alt: Correction to Shaper (ON)
   :align: middle

.. |ink_eraser_off| image:: /_static/icons/ink_eraser_off.png
   :height: 20pt
   :alt: Correction to Shaper (OFF)
   :align: middle

SLM Calibration
===============

.. _sec-calibration-why:

Why Calibrate?
--------------
SLMs do **not** linearly convert **gray levels** (0–255) to **optical phase** (0–2π).
Calibration establishes the **gray-level-to-phase mapping** for accurate beam shaping.

.. _sec-calibration-procedure:

Calibration Procedure
---------------------
1. **Open the Calibration Tool**: Click **Calibration** |equalizer| in the toolbar or navigate to **Shaping > Calibration > Calibration**.

2. **Select the SLM**: Ensure the **Shaper** module is loaded in PyMoDAQ’s Dashboard.

3. **Run Calibration**: The tool performs a **double-slit experiment**:

     - Apply a **gray-level ramp** to half of the SLM (passing through one slit).
     - Measure the **interference pattern** on a camera (in the Dashboard).
     - Extract the **relative phase** from the interference fringes.

4. **Save the Calibration**: The curve is saved to:
     ::

        ~/.pymodaq/beam_shaping/calibration.h5

.. _FIG-calibration:

.. figure:: /_images/calibration.png
   :alt: SLM Calibration Module
   :width: 60%
   :align: center

   SLM Calibration Module.
   (a) Interference pattern cropped and integrated perpendicularly to the fringes as a function of gray levels.
   (b) Relative phase of the oscillations in the interference pattern.
   The phase is locally saved and used to apply computed holograms to the SLM.


For a result on the calibration process, see :numref:`FIG-calibration`.

.. _sec-calibration-using:

Using Calibration
-----------------


If no calibration file is found, an error message will prompt you to calibrate first.

.. note::
   Some SLMs (e.g., Holoeye Pluto) support **internal calibration**. The Shaper actuator tells it to the extension
   (``has_internal_calibration`` in its ``shaper_properties`` group, see :doc:`shapers`). Whether it is used is the
   preference *use_internal_calibration* (``[default_shaper]``, checked by default), imposed by the extension to the
   actuator: no pymodaq calibration is then needed (but you'll have to trust the internal calibration). Uncheck it to
   use the calibration of BeamShaping.
