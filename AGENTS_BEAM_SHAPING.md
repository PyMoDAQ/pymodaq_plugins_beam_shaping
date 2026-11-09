# AGENTS_BEAM_SHAPING.md: `pymodaq_plugins_beam_shaping`

A PyMoDAQ extension that computes masks for spatial light modulators (SLM, DMD...) from an input field and a target
field, sends them to a **Shaper** actuator of the Dashboard and optionally optimizes them with a camera feedback.
Source in `src/pymodaq_plugins_beam_shaping/`. The generic PyMoDAQ guidance is in [AGENTS.md](AGENTS.md) (copied from the plugin template, keep it
close to the template so that it can be updated); this file is what is specific to this repository.

## Branches and PRs

- Target PyMoDAQ is **5.3.x** (`pymodaq>=5.3.2,<5.4`). `5.3.x` is the default and integration branch: branch from it
  (`feature/<topic>`) and open PRs against it. Never push to it directly.
- A feature in several steps is a stack of PRs: the second PR is based on the branch of the first and is retargeted to
  `5.3.x` once the first is merged (the binary holograms are #82, then the superpixel one in #83).
- Do not use the word "preset" (obsolete): say *experiment* and *state* (see section 4 of AGENTS.md).
- The version comes from git tags (`hatch-vcs`); do not edit it. Entry points are generated at build time by
  `hatch_build.py` from the `[features]` flags and the folders.

## Map of the code

| Where | What |
|---|---|
| `extensions/spatial_beam_shaping.py` | The Dashboard extension (`beam_shaping` script). Hosts the algorithm app, the field loaders, the Shaper actuator and the camera. |
| `field/field.py` | `Field`: the data class (a `DataRaw` with amplitude and phase, FFT helpers, pixel sizes) passed everywhere. |
| `field/utils.py`, `field/factory.py` | `FieldLoader` base class and `LoaderFactory`. |
| `field/loaders/` | The **field loaders**: `from_functions_loader.py` (Gaussian, Laguerre-Gauss, Hermite-Gauss, vortex...), `image_loader.py`, `save_field_loader.py` (h5), `dashboard_loader.py` (from a detector). |
| `field/field_loader_app.py` | The widget that lets the user choose and parametrize a loader (input field, target field). |
| `field/field_tool_app.py` | The standalone **Field Tool** (`field_tool` script): loads a Field and applies a chain of operations. |
| `field/operations/` | Field Tool operations: `base.py` (`FieldOperation`, `OperationFactory`), `linear_phase.py`, `unwrap.py`, `zernike.py`. The numerical helpers they use are in `compute.py` (centered grid, support mask, unwrap, linear phase fit, Zernike fit, wrap...). |
| `algorithms/algo_base.py` | `AlgoBase`: base of every algorithm (see below). |
| `algorithms/factory.py` | `AlgorithmFactory`, `register_algorithms()` and the entry point group `pymodaq_plugins_beam_shaping.algorithms` for third party algorithms. |
| `algorithms/algorithms/` | The **algorithms**, one module per family (see below). |
| `algorithms/ini_phases/`, `stoppings/`, `loss.py` | Initial phases, stopping criteria and loss functions used by iterative algorithms. |
| `algorithms/compensation.py`, `compensations/` | Compensation of the input beam profile (factory like the initial phases, chosen in the AlgoApp settings); an algorithm sets `INPUT_COMPENSATION = True` and calls `compensate_target`. |
| `algorithms/algorithm_app.py` | `AlgoApp`: the widget running an algorithm, owning the masks, the shaper and the fields. |
| `algorithms/utils.py` | Enums (`AlgoStatus`, `AlgoType`, `ApplyMaskTo`, `LensSetup`). |
| `utilities/shaper.py` | `Shaper` and `ModulatorType` (phase, amplitude, both), defined in `pymodaq_plugins_utils`; `get_default_shaper()` reads the config. |
| `utilities/` | Corrections, calibration (`calibrating.py`), `sizing.py` (needed field size), `regions.py`, h5 saving, and `headless_algorithms.py` (see "Testing"). |
| `daq_move_plugins/`, `daq_viewer_plugins/`, `hardware/` | Mock shaper, mock camera and autofocus instruments used for tests and demos; real shapers live in other packages. |
| `scanners/calibration.py` | Scan scheme for the SLM calibration. |
| `models/` | Optimizer / data mixer models (autofocus). |
| `scripts/` | `algorithm_playground.py` (see "Testing"), SLM calibration scripts. |
| `resources/` | `config_template.toml` (defaults, incl. `default_shaper`), sample fields. |

## Field loaders

A loader derives from `FieldLoader`, sets `LOADER_NAME`, declares its settings in `params`, implements the loading of
`self.field` and is registered with `@LoaderFactory.register_loader()`. `register_loaders()` imports every module of
`field/loaders/`, so **adding a loader = adding a file there** (or a class in an existing module); no other
registration is needed. Parameters of the needed size (pixel counts and sizes) come from the parent app
(`pixel_width`, `n_pixel_width`...).

## Algorithms

- A class derived from `AlgoBase` in a module of `algorithms/algorithms/`, registered with
  `@AlgorithmFactory.register_algorithm()`. Modules are discovered automatically: no import to add elsewhere.
- Class attributes to set: `ALGO_NAME` (unique, shown in the app), `MODULATOR_TYPES` (default phase only; amplitude
  modulators such as a DMD need `ModulatorType.AMPLITUDE`; an algorithm is only offered when it supports the shaper,
  and a shaper modulating both accepts all), `STATUS` / `STATUS_NOTE` (`AlgoStatus`, written by hand and honest: say
  what was verified and on what), `ITERATIVE`, `INI_PHASE`, `params`.
- Families: iterative/projection (`projections.py`: Gerchberg-Saxton, Projections), `direct.py`, `diffractive.py`
  (broken, see its status), `checker_board.py`, optimizers on PyTorch (`optim.py`, `minimizer.py`, `torch_base.py`,
  optional `pytorch` extra), and the **amplitude modulation** family for DMDs.
- Amplitude modulation / binary holograms: on 5.3.x today `dmd_lee.py` (`DMD Lee`) and `super_pixel.py`
  (`SuperPixels`). **PR #82 replaces both by `binary_holograms.py`** (base class `BinaryHologram` with the carrier
  grating `px`, `py` and the carrier removal; `Binary Threshold` phase only, `Parallel Lee` amplitude and phase), and
  PR #83 adds `Superpixel` to it. If those PRs are merged, the module is `binary_holograms.py` and the two old files
  are gone; check which state the branch you are on is in before editing.
- User documentation of an algorithm: `docs/src/user_guide/algorithm_reference.rst` (reference, overview table),
  `algorithms.rst`, `custom_algorithm.rst` (how to write one, including from another package through the entry
  point group) and `theory.rst`.

## Shapers

The extension asks the **Shaper** actuator for its geometry and properties (read only settings groups
`shaper_geometry` and `shaper_properties`, defined in `pymodaq_plugins_utils.hardware.shaper`). Without such an
actuator the `default_shaper` section of the config is used. Do not hardcode a shaper size or modulator type.
Mock instruments for tests: `daq_move_MockShaper`, `daq_2Dviewer_MockShaperCamera`.

## Testing

```bash
pytest tests/                                   # whole suite (Qt is needed: tests use the qapp fixture)
pytest tests/test_algorithms_by_modulator_type.py
```

- `tests/conftest.py` imports `cv2` first and removes the Qt plugin path variables it sets; keep that.
- Tests by topic: algorithms (`test_algo_helpers.py`, `test_algorithm_status.py`, `test_algorithms_by_modulator_type.py`,
  `algorithm_entry_points_test.py`, `test_dmd_lee.py` or `test_binary_holograms.py` after #82), fields (`field_test.py`,
  `test_field_tool.py`), shapers and calibration (`test_shaper_interface.py`, `test_calibration.py`), apps
  (`test_custom_apps.py`), package structure (`test_plugin_package_structure.py`).
- On 5.3.x two tests of `test_shaper_interface.py` already fail; mention it instead of hiding it, and do not
  disable tests.
- **Script to try an algorithm without the GUI**: `scripts/algorithm_playground.py`, cells delimited by `# %%`, run
  in an IDE or Jupyter. It uses `utilities/headless_algorithms.py` (`list_available`, `make_shaper`, `HeadlessApp`,
  `load_field`, `create_algorithm`, `run_algorithm`, `plot_field`, `plot`...), the same helpers the tests use, and
  calls the algorithm as `AlgoApp` does. Prefer it, and tests built on `headless_algorithms`, to launching the
  Dashboard. It validates the code path only, not the hardware.

## Documentation (Sphinx)

- Sources in `docs/src/` (`index.rst`, `theory.rst`, `quick_start.rst`, `user_guide/*.rst`: interface, fields,
  field_tool, algorithms, algorithm_reference, custom_algorithm, shapers, slmsuite, calibration, corrections,
  data_management), bibliography in `docs/src/bibtex.bib`, figures in `docs/src/_images/`.
- Figures are generated by scripts in `docs/scripts/` (e.g. the binary holograms snapshots after #82); update the
  script and the image together.
- Build: `pip install -r docs/requirements.txt && make -C docs html` (config in `docs/src/conf.py`, Read the Docs in
  `readthedocs.yml`). A new algorithm, loader or operation needs its doc page entry in the same PR.
- Write the docs in the voice of the existing pages; cite papers through `bibtex.bib`.
