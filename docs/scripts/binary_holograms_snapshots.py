"""Makes the figure of the binary holograms of the documentation (docs/src/_images/binary_holograms.png)

The same target (the default *ImageFiles* loader: its image as amplitude and its associated phase) is computed with
each algorithm of the family (Binary Threshold, Parallel Lee, Superpixel), with the helpers of the script
``scripts/algorithm_playground.py``, and the part of the pattern sent to the modulator is shown. Run it with
``python binary_holograms_snapshots.py`` (the figure is written next to the other images of the documentation).
"""
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt
import numpy as np

from pymodaq_plugins_beam_shaping.algorithms.utils import ApplyMaskTo, AlgoType
from pymodaq_plugins_beam_shaping.utilities import headless_algorithms as pg, regions

OUTPUT = Path(__file__).parent.parent / 'src' / '_images' / 'binary_holograms.png'
ALGORITHMS = ('Binary Threshold', 'Parallel Lee', 'Superpixel')
# the periods of the grating, in pixels: wide for the amplitude levels of Parallel Lee, the superpixels are 4 x 4
PARAMS = {'Binary Threshold': {'px': 8, 'py': 64}, 'Parallel Lee': {'px': 8, 'py': 64}, 'Superpixel': {'px': 4}}
MASK_HALF_SIZE = 150.  # um, half size of the elliptical mask of the intermediate plane around the selected order

pg.ensure_qapp()
app = pg.HeadlessApp(pg.make_shaper(modulator_type='amplitude'))
input_field = pg.load_field('GaussianIntensity', None, app)
target_field = pg.load_field('ImageFiles', None, app)  # the default image and its associated phase

results = {}
for name in ALGORITHMS:
    algo = pg.create_algorithm(pg.reload_algorithm(name), app, PARAMS[name])
    pg.set_fields(algo, input_field, target_field)
    # the order to filter, as given by the algorithm, in um from the center of the intermediate plane
    y, x = np.array(algo.order_frequency()) * regions.pixel_sizes_in_um(algo.intermediate_pixel_sizes)
    center_y, center_x = np.array(algo.shape) * regions.pixel_sizes_in_um(algo.intermediate_pixel_sizes) / 2
    # in the frame of the extension: the origin is the corner of the field
    mask = ((center_y + y - MASK_HALF_SIZE, center_y + y + MASK_HALF_SIZE),
            (center_x + x - MASK_HALF_SIZE, center_x + x + MASK_HALF_SIZE))
    pg.set_mask(app, ApplyMaskTo.INTERMEDIATE, mask, 'elliptical')
    pg.run_algorithm(algo)
    output = algo.output_field
    results[name] = (output.amplitude, output.phase, algo.modulator_field.amplitude, algo.ALGOTYPE)
    reference = pg.get_target_field(algo).amplitude  # the same for both
    reference_phase = pg.get_target_field(algo).phase
    pixel_size = output.pixels_sizes[1].m_as('um')


def correlation(a, b):
    a, b = a - a.mean(), b - b.mean()
    return float((a * b).sum() / np.sqrt((a * a).sum() * (b * b).sum()))


# the region of the output plane holding the target, with some margin
rows, columns = np.nonzero(reference > 0.05 * reference.max())
margin = 30
window = (slice(max(rows.min() - margin, 0), rows.max() + margin), slice(max(columns.min() - margin, 0),
                                                                           columns.max() + margin))
target_region = (slice(rows.min(), rows.max()), slice(columns.min(), columns.max()))
ny, nx = reference.shape
extent = np.array([window[1].start - nx / 2, window[1].stop - nx / 2,
                   window[0].start - ny / 2, window[0].stop - ny / 2]) * pixel_size / 1000  # mm

figure, axes = plt.subplots(len(ALGORITHMS), 3, figsize=(11, 3.3 * len(ALGORITHMS)), constrained_layout=True)
for row, name in enumerate(ALGORITHMS):
    amplitude, phase, pattern, algotype = results[name]
    amplitude = amplitude / amplitude[window].max()
    axes[row, 0].imshow(amplitude[window], extent=extent, origin='lower', cmap='viridis', vmin=0, vmax=1)
    if algotype == AlgoType.PHASE:  # the amplitude of the target is not encoded
        axes[row, 0].set_title(f'{name}\nAmplitude (phase only: the amplitude of the target is not encoded)',
                               fontsize=9)
    else:
        axes[row, 0].set_title(f'{name}\nAmplitude (correlation with the target image: '
                               f'{correlation(results[name][0][target_region], reference[target_region]):.2f})',
                               fontsize=9)
    shown_phase = np.where(amplitude > 0.1, phase, np.nan)  # the phase only where there is light
    image = axes[row, 1].imshow(shown_phase[window], extent=extent, origin='lower', cmap='twilight', vmin=-np.pi,
                                vmax=np.pi)
    axes[row, 1].set_title('Phase (where the amplitude is above 10 %)', fontsize=9)
    centre = np.array(pattern.shape) // 2
    zoom = (slice(centre[0], centre[0] + 40), slice(centre[1], centre[1] + 40))
    axes[row, 2].imshow(pattern[zoom], cmap='gray', vmin=0, vmax=1, interpolation='nearest', origin='lower')
    axes[row, 2].set_title('Pattern on the modulator (40 x 40 pixels)', fontsize=9)
    for ax in axes[row, :2]:
        ax.set_xlabel('mm')
        ax.set_ylabel('mm')
    axes[row, 2].axis('off')
figure.colorbar(image, ax=axes[:, 1], label='rad', shrink=0.6, pad=0.02)
figure.savefig(OUTPUT, dpi=110)
print(f'written: {OUTPUT}')
for name in ALGORITHMS:
    if results[name][3] != AlgoType.PHASE:
        print(f'{name}: correlation of the amplitude with the target image = '
              f'{correlation(results[name][0][target_region], reference[target_region]):.3f}')
