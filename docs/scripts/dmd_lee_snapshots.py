"""Makes the figure of the DMD Lee algorithm of the documentation (docs/src/_images/dmd_lee_binarization.png)

The same target (the default *ImageFiles* loader: its image as amplitude and its associated phase) is computed
with the algorithm, with and without the binarization of the pattern (by width modulation of the stripes), with the
helpers of the script
``scripts/algorithm_playground.py``. Run it with ``python dmd_lee_snapshots.py`` (the figure is written next to the
other images of the documentation).
"""
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt
import numpy as np

from pymodaq_plugins_beam_shaping.algorithms.utils import ApplyMaskTo
from pymodaq_plugins_beam_shaping.utilities import headless_algorithms as pg, regions

OUTPUT = Path(__file__).parent.parent / 'src' / '_images' / 'dmd_lee_binarization.png'
SUPER_PIXEL = 10  # pixels, the period of the grating: the wider, the more amplitude levels the binary pattern has
MASK_HALF_SIZE = 150.  # um, half size of the elliptical mask of the intermediate plane around the selected order

pg.ensure_qapp()
app = pg.HeadlessApp(pg.make_shaper(modulator_type='amplitude'))
input_field = pg.load_field('GaussianIntensity', None, app)
target_field = pg.load_field('ImageFiles', None, app)  # the default image and its associated phase

def make_algorithm(binarize: bool):
    algo = pg.create_algorithm(pg.reload_algorithm('DMD Lee'), app, {'binarize': binarize, 'super_pixel': SUPER_PIXEL})
    pg.set_fields(algo, input_field, target_field)
    return algo


# the selected order is searched once, on the intermediate plane without mask (a snap of the algorithm)
algo = make_algorithm(True)
pg.set_mask(app, ApplyMaskTo.INTERMEDIATE, None)
intensity = pg.snap(algo).intensity.copy()
rows, columns = np.indices(intensity.shape)
centre = np.array(intensity.shape) // 2
intensity[(rows - centre[0]) ** 2 + (columns - centre[1]) ** 2 < 30 ** 2] = 0  # not the zero order
order = np.array(np.unravel_index(np.argmax(intensity), intensity.shape))
y, x = (order - centre) * regions.pixel_sizes_in_um(algo.intermediate_pixel_sizes)
if x - y > 0:  # the order at the positive frequency carries the opposite phase: take the other one
    y, x = -y, -x
mask = ((y - MASK_HALF_SIZE, y + MASK_HALF_SIZE), (x - MASK_HALF_SIZE, x + MASK_HALF_SIZE))

results = {}
for binarize in (False, True):
    algo = make_algorithm(binarize)
    pg.set_mask(app, ApplyMaskTo.INTERMEDIATE, mask, 'elliptical')
    pg.run_algorithm(algo)
    output = algo.output_field
    results[binarize] = (output.amplitude, output.phase, algo.modulator_field.amplitude)
    reference = pg.get_target_field(algo).amplitude  # the same for both
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

figure, axes = plt.subplots(2, 3, figsize=(11, 6.6), constrained_layout=True)
for row, (binarize, label) in enumerate(((False, 'Without binarization'), (True, 'With binarization'))):
    amplitude, phase, pattern = results[binarize]
    amplitude = amplitude / amplitude[window].max()
    axes[row, 0].imshow(amplitude[window], extent=extent, origin='lower', cmap='viridis', vmin=0, vmax=1)
    axes[row, 0].set_title(f'{label}\nAmplitude (correlation with the target image: '
                           f'{correlation(results[binarize][0][target_region], reference[target_region]):.2f})', fontsize=9)
    shown_phase = np.where(amplitude > 0.1, phase, np.nan)  # the phase only where there is light
    image = axes[row, 1].imshow(shown_phase[window], extent=extent, origin='lower', cmap='twilight', vmin=-np.pi, vmax=np.pi)
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
for binarize in (False, True):
    print(f'binarize={binarize}: correlation of the amplitude with the target image = '
          f'{correlation(results[binarize][0][target_region], reference[target_region]):.3f}')
