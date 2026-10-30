.. _sec-acknowledgments:

Acknowledgments
===============

Documentation Assistance
------------------------
This documentation was generated with the assistance of **Vibe Code**, an AI agent developed by Mistral AI.
**Vibe Code** contributed to:

✅ **Code Analysis**: Analyzed the source code of the
   `pymodaq_plugins_beam_shaping <https://github.com/PyMoDAQ/pymodaq_plugins_beam_shaping>`_ plugin
   to extract its architecture, classes, and features.

✅ **Theoretical Integration**: Incorporated theoretical background from the scientific article:

   | **Rollo, V., Arbouet, A., & Weber, S. J. (2025).**
   | *PyMoDAQ-BeamShaping: a Python Toolbox to Spatially Shape Optical Beams.*
   | *(Manuscript provided via FileSender, CEMES-CNRS)*

✅ **Documentation Structuring**: Organized the documentation following the
   `PyMoDAQ <https://pymodaq.cnrs.fr/en/latest/>`_ style, including:

   - Clear **file hierarchy** (separate ``.rst`` files by topic).
   - **Cross-references** (``:numref:``, ``:ref:``).
   - **Placeholders for figures** (compatible with article images and screenshots).



Main Sources
------------
.. list-table:: **Primary Sources**
   :header-rows: 1
   :widths: 20 60 20

   * - **Type**
     - **Source**
     - **Link/Reference**
   * - **Plugin Code**
     - Official PyMoDAQ-BeamShaping repository
     - `GitHub: pymodaq_plugins_beam_shaping <https://github.com/PyMoDAQ/pymodaq_plugins_beam_shaping>`_
   * - **Scientific Article**
     - Full manuscript (PDF/LaTeX) provided by the authors (Rollo, Arbouet, Weber)
     - To be cited
   * - **PyMoDAQ Documentation**
     - Official guide for extensions and documentation style
     - `pymodaq.cnrs.fr <https://pymodaq.cnrs.fr/en/latest/>`_
   * - **Plugin Template**
     - Base structure for plugins (``pyproject.toml``, ``README.rst``)
     - `pymodaq_plugins_template <https://github.com/PyMoDAQ/pymodaq_plugins_template>`_
   * - **Icons**
     - Material Icons (Google)
     - `fonts.google.com/icons <https://fonts.google.com/icons>`_


Tools Used
----------
- **Sphinx** (with ``sphinx-rtd-theme``) for documentation generation.
- **reStructuredText** (``.rst``) for writing.
- **LaTeX** for mathematical equations (integrated via ``sphinx.ext.imgmath``).
- **HDF5** for describing the structure of ``.h5beam`` files.


.. note::

   The figures used in this documentation are either from the cited scientific article
   or screenshots of the PyMoDAQ-BeamShaping interface. All equations and theoretical formulations
   are directly derived from the article by Rollo et al. (2025).


How to Cite
-----------

If you use this toolbox in your work, please cite it with the article citation:

.. code-block:: bibtex

   @misc{BeamShapingDocs,
     author = {Weber, S{\'e}bastien and Rollo, Valentin and Arbouet, Arnaud and {Vibe Code}},
     title = {{PyMoDAQ-BeamShaping: User Documentation}},
     year = {2025},
     url = {https://github.com/PyMoDAQ/pymodaq_plugins_beam_shaping},
     note = {Documentation generated with the assistance of Vibe Code (Mistral AI)}
   }