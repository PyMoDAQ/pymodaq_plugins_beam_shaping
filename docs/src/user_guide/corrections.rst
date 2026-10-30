.. |deblur| image:: /_static/icons/deblur.png
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

.. |add_circle| image:: /_static/icons/add_circle.png
   :height: 20pt
   :alt: Correction to Shaper (OFF)
   :align: middle


Phase Corrections
=================

A real setup often features optical aberrations deteriorating the calculated shaping. A correction module (and interface
see :numref:`FIG-corrections`) is provided to add correction terms to the calculated modulator phase.

.. _sec-corrections-types:

Correction Types
----------------
Apply corrections to compensate for **optical aberrations** or **misalignments**:

.. list-table:: **Correction Types**
   :header-rows: 1
   :widths: 30 50 20

   * - **Correction**
     - **Description**
     - **Parameters**
   * - **Focal Length**
     - Corrects quadratic phase aberrations (defocus).
     - ``focal_length`` (mm)
   * - **Zernike**
     - Corrects higher-order aberrations (up to order 5).
     - Order ``n``, coefficient ``m``
   * - **Linear (Tilt)**
     - Corrects beam tilt (misalignment).
     - ``tilt_x``, ``tilt_y`` (radians)

.. _sec-corrections-applying:

Applying Corrections
--------------------
1. **Open the Corrections Panel**: Click **Corrections** (|deblur|) in the toolbar.
2. **Adjust Sliders**: Set **focal length**, **Zernike coefficients**, or **tilt angles**.

3. **Send to SLM**: Enable **Correction to shaper** (|ink_eraser|) to apply corrections to the SLM.

.. _sec-corrections-actuators:

Adding Corrections as Actuators
--------------------------------
To integrate corrections into PyMoDAQ’s **Dashboard** (e.g., for automation):

1. Click **Add Corrections** (|add_circle|) in the toolbar.
2. The following actuators will appear in the Dashboard:
   - ``FocalLength``
   - ``Zernike_1_1``, ``Zernike_2_0``, etc. (up to the configured order).

.. _FIG-corrections:

.. figure:: /_images/corrections.png
   :alt: Phase Corrections Panel
   :width: 70%
   :align: center


   Corrections panel with sliders for (A) focal length, (B) Zernike coefficients, and (C) tilt angles.
   The **Add Corrections** button integrates these as actuators in PyMoDAQ.

