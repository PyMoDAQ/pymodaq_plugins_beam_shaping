Introduction
============

.. _sec-intro-overview:

Overview
--------
PyMoDAQ-BeamShaping is a **PyMoDAQ extension** for **spatial beam shaping** using **Spatial Light Modulators (SLMs)**.
It bridges **numerical simulations** and **experimental implementations** by providing:

- Algorithms for phase retrieval (Gerchberg-Saxton, IFTA, MRAF, etc.).
- Real-time visualization of input, modulator, and output fields.
- SLM calibration (gray levels → phase mapping).
- Phase corrections (Zernike, focal, linear).
- Compatibility with ``pymodaq_data`` for ``.h5beam`` files (HDF5-based).

Computational spatial beam shaping is widely used to generate tailored optical fields for applications
ranging from **optical trapping and microscopy** to **laser processing and quantum photonics** (see below).

.. _sec-intro-applications:

Applications
------------
.. list-table:: **Domain-Specific Use Cases**
   :header-rows: 1
   :widths: 30 70

   * - **Microscopy**
     - Structured illumination, STED, SIM (custom intensity patterns).
   * - **Optical Trapping**
     - Custom trap shapes (line traps, multi-spot arrays).
   * - **Laser Processing**
     - Beam shaping for material ablation (ring, square, or arbitrary shapes).
   * - **Quantum Optics**
     - Entangled photon pair generation (Laguerre-Gauss modes: LG₀₁, LG₃₁).
   * - **Metrology**
     - Wavefront correction (aberration compensation).

.. _FIG-schema:

.. figure:: /_images/layout.png
   :alt: General Beam-Shaping Problem
   :width: 90%
   :align: center


   **Figure 1:** General beam-shaping problem and algorithm steps.
   A laser beam incident in an **input plane** is modulated in a **modulator plane**,
   with the objective of generating, in an **output plane**, an optical field as close as possible
   to a prescribed complex target field (eventually restrained within a region of interest).
   The **2f** and **4f** optical configurations are shown in (b).
   *(From the article: Figure 1, ``layout.pdf``)*

.. _sec-theory:

.. toctree::
   :maxdepth: 1

   theory