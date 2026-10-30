User Interface
==============

.. _sec-ui-overview:

Overview
--------
The BeamShaping interface is organized into **dockable panels** for flexibility.

.. list-table:: **Main Docks/Panels**
   :header-rows: 1
   :widths: 30 50 20
   :class: longtable

   * - **Dock/Panel**
     - **Purpose**
     - **Key Features**
   * - **Input Field Loader**
     - Load/edit the **input beam** (source field).
     - Simulations, images,
       cameras.
   * - **Target Field Loader**
     - Load/edit the **target beam** (desired output).
     - ROI selection, masking.
   * - **Algorithm**
     - Configure the shaping algorithm.
     - Parameters, stopping criteria.
   * - **Modulator Plane**
     - Visualize the **phase/amplitude** sent to the SLM.
     - 2D plots, histogram.
   * - **Output Plane**
     - Visualize the **shaped beam** (simulated or measured).
     - Intensity, phase, cross-sections.
   * - **Metrics**
     - Display **performance metrics** (NRMSE, Fidelity, Efficiency).
     - Real-time updates.
   * - **Corrections**
     - Apply **phase corrections** (Zernike, focal, linear).
     - Interactive sliders.

.. _sec-ui-toolbar:


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

.. |deblur| image:: /_static/icons/deblur.png
   :height: 20pt
   :alt: Corrections
   :align: middle


Toolbar Actions
---------------
All toolbar buttons use **Material Icons** and provide quick access to common actions.

.. list-table:: **Toolbar Actions**
   :header-rows: 1
   :widths: 25 15 10 50

   * - **Action**
     - **Icon**
     - **Shortcut**
     - **Description**
   * - **Save**
     - |save|
     - Ctrl+S
     - Save all fields, algorithm settings, and corrections to a ``.h5beam`` file.
   * - **Load**
     - |file_open|
     - Ctrl+O
     - Load a ``.h5beam`` file.
   * - **Target Selection**
     - |target|
     - -
     - Show/hide the Target Field Loader.
   * - **Input Beam Selection**
     - |input|
     - -
     - Show/hide the Input Field Loader.
   * - **Corrections**
     - |deblur|
     - -
     - Show/hide the Corrections panel.
   * - **Calibration**
     - |equalizer|
     - -
     - Launch the **SLM calibration** tool.
   * - **Algo to Shaper**
     - |grid_on|/|grid_off|
     - -
     - Enable/disable sending the algorithm’s output to the SLM.
   * - **Correction to Shaper**
     - |ink_eraser|/|ink_eraser_off|
     - -
     - Enable/disable sending phase corrections to the SLM.
   * - **Add Corrections**
     - |add_circle|
     - -
     - Add corrections (Zernike, focal) as **actuators** in PyMoDAQ’s Dashboard.


For a detailed overview of the interface, see :numref:`FIG-quick-start`.