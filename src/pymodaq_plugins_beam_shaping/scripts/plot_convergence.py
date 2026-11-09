"""Plot the convergence of the metrics saved during a (headless or app) run of an algorithm.

Metrics are saved when running with ``save_metrics=True`` in ``algorithm_playground.py`` (or with the continuous
saving of the AlgoApp), in ``/RawData/Shaping000/Metrics`` as one enlargeable dataset: one data array per metric,
all along the navigation axis ``step``.
"""
import numpy as np
from matplotlib import pyplot as plt

from pymodaq_data.h5modules.data_saving import DataLoader

FILE = 'Dataset_20261109_000.h5'
RUN = '/RawData/Shaping000'  # the group of the run (several runs in a file: Shaping001, ...)
METRICS_TO_PLOT = None  # None for all or a list of labels, for instance ['efficiency']
LOG_SCALE = {}  # labels to display in log scale, for instance {'Intensity NRMSE'}
SAVE_AS = 'convergence.pdf'  # None to not save

# plt.rcParams['text.usetex'] = True  # as in the other figure scripts
font = {'family': 'arial', 'color': 'black', 'weight': 'normal', 'size': 16}
font_title = {'family': 'arial', 'color': 'black', 'weight': 'normal', 'size': 10}

# %% load the metrics
with DataLoader(FILE) as loader:
    dwa_metrics = loader.load_all(f'{RUN}/Metrics')[0]  # all the metrics are in one data object, one label each

steps = dwa_metrics.get_axis_from_index(0)[0].get_data()
metrics = {label: np.squeeze(data) for label, data in zip(dwa_metrics.labels, dwa_metrics.data)}
if METRICS_TO_PLOT is not None:
    metrics = {label: metrics[label] for label in METRICS_TO_PLOT}

# %% plot, one panel per metric (they have different scales)
fig = plt.figure('Convergence', figsize=(5., 2.2 * len(metrics)))
fig.clf()
axes = fig.subplots(len(metrics), 1, sharex=True, squeeze=False)[:, 0]
for ax, (label, values) in zip(axes, metrics.items()):
    ax.plot(steps, values, '.-k', linewidth=1)
    ax.set_ylabel(label, fontdict=font_title)
    if label in LOG_SCALE:
        ax.set_yscale('log')
    ax.grid(alpha=0.3)
    ax.annotate(f'{values[-1]:.3f}', (steps[-1], values[-1]), xytext=(-4, 6), textcoords='offset points',
                ha='right', fontsize=8)
axes[-1].set_xlabel('Iteration', fontdict=font)
fig.tight_layout()

# %%
if SAVE_AS is not None:
    plt.savefig(SAVE_AS)
plt.show()
