Troubleshooting
===============

.. list-table:: **Common Issues and Solutions**
   :header-rows: 1
   :widths: 35 30 35

   * - **Issue**
     - **Possible Cause**
     - **Solution**
   * - SLM not responding
     - ``Shaper`` module not loaded in Dashboard.
     - Load the ``Shaper`` module in PyMoDAQ’s Dashboard and initialize it. Otherwise the default shaper of the
       configuration file is used (see :doc:`user_guide/shapers`).
   * - Calibration error
     - Missing calibration file.
     - Run calibration via **Shaping > Calibration**.
   * - Algorithm not converging
     - Inadequate parameters or initial phase.
     - Increase iterations, adjust stopping criteria, or try a quadratic initial phase.
   * - Blurry output field
     - Uncorrected aberrations.
     - Apply Zernike/focal corrections or recalibrate the SLM.
   * - ``.h5beam`` file not loading
     - SLM size mismatch.
     - Check that the size and pixel size of the Shaper actuator (``shaper_geometry`` group) are those of the file.
   * - Slow performance
     - Large field size or complex algorithm.
     - Reduce field size or use a simpler algorithm (e.g., ``DirectPhase``).
   * - Speckle in output
     - Random initial phase.
     - Use a **quadratic initial phase** or MRAF algorithm.
   * - Ghosting in measurements
     - Back-reflections in the setup.
     - Use anti-reflection coatings or adjust the optical path.