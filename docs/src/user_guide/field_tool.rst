.. _sec-field-tool:

Field Tool
==========

The **Field Tool** takes one field, applies a chain of operations to it (remove a linear phase, Zernike modes,
unwrap or wrap the phase...) and shows the field **before**, **after** and their **difference**. It is meant to
analyse a field, for instance to remove the tilt and the defocus of the output phase and look at what remains while
the algorithm runs.

The tool only reads the field: nothing is sent back to the algorithm or to the shaper.


Opening the Field Tool
----------------------

* **From the extension**: menu *Tools > Shaping > Field Tool*, or the *Field Tool* button of the toolbar. The
  window works on the fields of the algorithm.
* **On its own**, without the Dashboard, to work on saved fields (``.h5field`` files):

  .. code-block:: bash

     field_tool
     # or
     python -m pymodaq_plugins_beam_shaping.field.field_tool_app

.. _FIG-field-tool:

.. figure:: /_images/field_tool.png
   :alt: Field Tool
   :width: 100%
   :align: center

   **Field Tool**: the settings and the chain of operations on the left; on the right, the amplitude and the phase
   of the field before the operations (top row), after (middle row) and their difference (bottom row). Here a linear
   phase then piston, tilts and defocus are removed: what remains is the residual phase.


Settings
--------

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - **Setting**
     - **Description**
   * - **Field**
     - The field to work on: ``output``, ``modulator``, ``intermediate``, ``target`` or ``input`` (the planes of the
       algorithm, with their complex values), or ``file``. On its own, the tool only has ``file``.
   * - **File**
     - Shown when *Field* is ``file``: the path of a ``.h5field`` file (as saved by the field loaders or by the
       tool itself) and a *Load!* button to read it again.
   * - **Active**
     - When checked, the tool recomputes each time the algorithm gives new fields (and when the input or the target
       is loaded again), as long as its window is shown. Uncheck it to freeze the field.
   * - **Threshold (%)**
     - Defines the **support** of the field: the pixels where the amplitude is above this percentage of its maximum.
       Outside the beam the phase is noise, so the fits are done on the support only.
   * - **Mask phase**
     - Show the phases as 0 outside the support.
   * - **Save Field!**
     - Save the field after the operations in a ``.h5field`` file. The settings, including the chain of operations
       and their results, are saved as metadata. The file can be opened by the *SavedField* loader or by the tool.
   * - **Operations**
     - The chain of operations, applied from top to bottom. The *Add* list at its bottom adds an operation at the
       end. Right click on an operation to **Move up**, **Move down** or **Remove** it. Each operation has an
       *Enabled* box to switch it off without removing it.

Any change of a setting or of the order of the chain recomputes the result on the last field, even when the
algorithm is stopped.


Display
-------

Each row shows the amplitude and the phase, with the axes of the field (in m):

* **Before**: the field as given by its source (a copy: the field of the algorithm is never modified).
* **After**: the field after the enabled operations.
* **Difference**: the amplitude after - before, and the phase difference
  :math:`\arg\left(E_{after} \, E_{before}^{*}\right)`, wrapped in :math:`]-\pi, \pi]`.


Operations
----------

A wrapped phase stays wrapped after the removal operations, and a phase unwrapped by *Unwrap phase* stays unwrapped.
The slopes and coefficients found are shown, read only, in the *Results* group of each operation.

.. list-table::
   :header-rows: 1
   :widths: 22 48 30

   * - **Operation**
     - **What it does**
     - **Settings / Results**
   * - **Remove linear phase**
     - Removes a phase :math:`k_x x + k_y y` (tilt, carrier). Method **FFT** (default): the slopes come from the peak
       of the spectrum of the field on the support, located to the sub-pixel; it works on the wrapped phase.
       Method **PLANE**: a plane fitted by least squares on the unwrapped phase of the support.
     - *FFT padding* (zero padding of the FFT), *Weighted* (PLANE: weight by the intensity). Results:
       :math:`k_x, k_y` in rad/pixel and rad/mm.
   * - **Remove Zernike**
     - Fits piston, tilt X, tilt Y and defocus together on a pupil (least squares on the unwrapped phase), and
       removes the checked ones. The pupil is a disk centered on the barycenter of the intensity.
     - *Remove* (the modes to remove), *Radius* (pixels, 0: the largest disk inside the support), *Weighted*.
       Results: the coefficients in rad (unit RMS on the pupil, Noll normalisation; the piston wrapped in
       :math:`]-\pi, \pi]`), the center and the radius used.
   * - **Unwrap phase**
     - Unwraps the phase (scikit-image ``unwrap_phase``).
     - *Only on support*: unwrap only where the amplitude is above the threshold, the phase outside is kept.
   * - **Wrap phase**
     - Wraps the phase on the whole field.
     - *Range*: ``SYMMETRIC`` for :math:`]-\pi, \pi]`, ``POSITIVE`` for :math:`[0, 2\pi[`.
   * - **Log10 amplitude**
     - Replaces the amplitude by :math:`\log_{10}(A / A_{max})`, clipped at a floor, to see the weak parts of the
       field (side lobes, noise floor). The phase is kept. Put it at the end of the chain, as the fits of the other
       operations are weighted by the intensity.
     - *Floor*: the smallest relative amplitude kept (avoids :math:`\log_{10}(0)`, default :math:`10^{-4}`). Result:
       the minimum of the log10 amplitude.


Adding an operation
-------------------

Operations are registered in a factory, as the algorithms and the field loaders are. A new operation is a class
derived from ``FieldOperation`` in a module of the ``pymodaq_plugins_beam_shaping.field.operations`` package (the
modules of this package are imported at start up). It declares its settings in ``params``, the values it finds in
``results`` (shown read only), and implements ``apply``, which returns a new ``Field``:

.. code-block:: python

   import numpy as np
   from scipy.ndimage import gaussian_filter

   from pymodaq_plugins_beam_shaping.field import Field
   from pymodaq_plugins_beam_shaping.field.operations.base import FieldOperation, OperationFactory


   @OperationFactory.register_operation()
   class SmoothPhase(FieldOperation):
       """ Gaussian smoothing of the phase"""
       OPERATION_NAME = 'Smooth phase'
       params = [{'title': 'Sigma (pxl)', 'name': 'sigma', 'type': 'float', 'value': 2., 'min': 0.}]
       results = [{'title': 'Phase RMS (rad)', 'name': 'rms', 'type': 'float', 'value': 0.}]

       def apply(self, field: Field, support: np.ndarray) -> Field:
           phase = gaussian_filter(field.phase, self.settings['sigma'])
           self.set_result('rms', float(np.std(phase[support])))
           return self.new_field(field, phase=phase)

``support`` is the boolean array given by the threshold of the tool. The numerical functions of the existing
operations live in ``field.operations.compute`` (no Qt), and can be used in scripts.
