Field Loaders
=============

.. _sec-fields-parameters:

Field Representation
--------------------

A **Field** is an advanced python object encapsulating the data values (numpy array) for both the amplitude and phase.
it also features attributes to add physical insight into the object such as the shape and the pixel width in microns.
It is inheriting from the base pymodaq data objects and as such is readily compatible with all the data management
PyMoDAQ provides.


Each field is defined by:

- **Amplitude**: ``np.ndarray`` (intensity distribution).
- **Phase**: ``np.ndarray`` (phase in radians).
- **Pixel Size**: ``Quantity`` see **pint** package (e.g., ``10 μm/pixel``, with units).

The **Field** object provides methods for padding, cropping, Fourier transforms, and normalization.


.. _sec-fields-types:

Supported Loader Field Types
----------------------------

Fields can be easily loaded/generated using the Field Loader. The first action is to select the *loader* type.

The **Input** and **Target Field Loaders** support multiple field loader types:

.. list-table:: **Field Loader Types**
   :header-rows: 1
   :widths: 40 60

   * - **Loader Type**
     - **Description**
   * - **Gaussian**
     - Simulated Gaussian beam.
   * - **Laguerre-Gauss**
     - Simulated Laguerre-Gauss modes (e.g., LG₀₁ for doughnut beams).
   * - **Multi-Spot**
     - Generate custom multi-spot patterns (e.g., 2x2, 3x3 grids).
   * - **Image**
     - Load from PNG/TIFF files (intensity and/or phase).
   * - **Camera**
     - Live acquisition from a detector (e.g., CCD, sCMOS).
   * - **HDF5**
     - Load from ``.h5`` files (PyMoDAQ format).

.. note::

   New loaders can easily be created with the help of the provided Factory Pattern. See developer section.


Field Loader UI
---------------

The FieldLoader interface, see :numref:`FIG-field-loader`, provides the controls select the type of loader
to apply th


.. _FIG-field-loader:

.. figure:: /_images/field_loader.png
   :alt: Field Loader Portfolio
   :width: 90%
   :align: center

   **FieldLoader User Interface**: has three panels, the left one is a tree-like structure offering
   the options to load and modify the fields. The middle panel is showing the loaded spatial amplitude
   while the right one is showing the spatial phase


.. note::
   You can use the **ROI selector** in the Field Loader Graphics to crop or mask regions of the field. The ROI
   Select of the amplitude and of the phase viewers is the same one: show, move or resize it in either viewer
   (or from the settings, *utils > roi_select*, where the center and the size are shown in µm, rounded to the micron) and the other follows. It is placed by the viewer (centered, 2/3 of
   the view) the first time it is shown, then it keeps its place.