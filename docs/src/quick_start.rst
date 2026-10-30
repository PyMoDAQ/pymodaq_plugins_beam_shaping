Quick Start
===========


.. |save| image:: /_static/icons/save.png
   :height: 20pt
   :alt: Save
   :align: middle

.. |file_open| image:: /_static/icons/file_open.png
   :height: 20pt
   :alt: Load
   :align: middle

.. |target| image:: /_static/icons/target.png
   :height: 20pt
   :alt: Target
   :align: middle

.. |input| image:: /_static/icons/input.png
   :height: 20pt
   :alt: Input
   :align: middle

.. |deblur| image:: /_static/icons/deblur.png
   :height: 20pt
   :alt: Corrections
   :align: middle

.. |equalizer| image:: /_static/icons/equalizer.png
   :height: 20pt
   :alt: Calibration
   :align: middle

.. |grid_on| image:: /_static/icons/grid_on.png
   :height: 20pt
   :alt: Algo to Shaper (ON)
   :align: middle

.. |grid_off| image:: /_static/icons/grid_off.png
   :height: 20pt
   :alt: Algo to Shaper (OFF)
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
   :alt: Add Corrections
   :align: middle



.. _sec-launch:

Launching the Extension
-----------------------

There are **three ways** to launch the BeamShaping extension:

1. **Direct Launch (Standalone Mode)**
   Run the extension directly (you can load an experiment in the Dashboard afterwards):

   .. code-block:: bash

      beam_shaping

   *Use case*: Quick testing or development without loading the full PyMoDAQ Dashboard.

2. **From PyMoDAQ Dashboard**

   - Launch PyMoDAQ Dashboard:

     .. code-block:: bash

        dashboard

   - Open the extension via **``Extensions > BeamShaping``** in the menu bar.

   *Use case*: Full integration with PyMoDAQ’s actuators, detectors, and viewers.

3. **From PyMoDAQ Launcher**

   - Launch the PyMoDAQ Launcher:

     .. code-block:: bash

        pymodaq

   - Select **``BeamShaping``** from the list and click **Launch**.

   *Use case*: Ideal for managing multiple PyMoDAQ modules (e.g., SLM + camera + actuators) in a single session.

.. _sec-quick-start-workflow:

Basic Workflow
--------------

Follow these steps to perform your first beam shaping:

1. **Load Fields**

   - Click **Input Beam Selection** |input| to load the **input field** (e.g., Gaussian beam from a camera or simulation).
   - Click **Target Selection** |target| to load the **target field** (e.g., multi-spot pattern, Laguerre-Gauss mode, or custom image).

2. **Select an Algorithm**

   - In the **Algorithm** panel, choose an algorithm (e.g., **Gerchberg-Saxton** or **MRAF**).

3. **Run the Shaping**

   - Enable **Algo to shaper** |grid_on| to send the calculated phase to the SLM.
   - Enable **Correction to shaper** |ink_eraser| to apply phase corrections.

4. **Visualize Results**

   - The **Modulator Plane** viewer shows the phase/amplitude sent to the SLM.
   - The **Output Plane** viewer displays the simulated or measured output field.

For more details on the interface, see :numref:`FIG-quick-start`.

.. _FIG-quick-start:

.. figure:: /_images/main_app.png
   :alt: BeamShaping User Interface
   :width: 100%


   BeamShaping user interface.
   All modules are controlled from this interface.

   - **Green buttons**: Algorithm selection.
   - **Dark green buttons**: Reset initial phase and propagate field forward.
   - **Yellow buttons**: Open FieldLoaders (input/target) and Intermediate Field Viewer.
   - **Purple buttons**: Send phase/corrections to the SLM (Dashboard integration).
   - **Cyan buttons**: Save/load computed fields (modulated/output).
   - **Dark blue buttons**: SLM calibration and Zernike corrections.


