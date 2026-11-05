"""The files written by the plugin say which version of it wrote them (PyMoDAQ writes its own versions)"""
import numpy as np
import pytest
from qtpy import QtWidgets

from pymodaq_data.h5modules.data_saving import DataLoader
from pymodaq_gui.utils.dock import DockArea

import pymodaq_plugins_beam_shaping
from pymodaq_plugins_beam_shaping.field import Field
from pymodaq_plugins_beam_shaping.field.h5 import save_field_to_h5
from pymodaq_plugins_beam_shaping.utilities import headless_algorithms as pg

VERSION_ATTRIBUTE = 'pymodaq_plugins_beam_shaping_version'


def check_version(path):
    with DataLoader(path) as loader:
        attributes = loader.h5saver.root().attrs
        assert attributes.get(VERSION_ATTRIBUTE) == pymodaq_plugins_beam_shaping.__version__
        assert attributes.get('pymodaq_version') is not None  # PyMoDAQ's own ones are still there


@pytest.fixture
def dockarea(qtbot):
    window = QtWidgets.QMainWindow()
    area = DockArea()
    window.setCentralWidget(area)
    qtbot.addWidget(window)
    window.show()
    yield area


def prepared_algorithm(modulator_type='phase'):
    headless = pg.HeadlessApp(pg.make_shaper(width=64, height=64, pixel_size=8., modulator_type=modulator_type))
    algo = pg.create_algorithm(pg.reload_algorithm('Gerchberg-Saxton'), headless)
    pg.set_fields(algo, pg.load_field('GaussianIntensity', None, headless),
                  pg.load_field('LaguerreGaussian', None, headless))
    return headless, algo


def test_field_file_has_the_version(tmp_path):
    save_field_to_h5(Field('f', amplitude=np.ones((8, 8)), phase=np.zeros((8, 8))), tmp_path / 'field.h5')
    check_version(tmp_path / 'field.h5')


def test_run_saved_during_the_iterations_has_the_version(qapp, tmp_path):
    headless, algo = prepared_algorithm()
    pg.run_algorithm(algo, 2, save_fields=('modulator/phase',), h5file=tmp_path / 'run.h5', verbose=False)
    check_version(tmp_path / 'run.h5')


def test_algorithm_file_of_the_app_has_the_version(qtbot, dockarea, tmp_path):
    from pymodaq_plugins_beam_shaping.algorithms.algorithm_app import AlgoApp

    headless, algo = prepared_algorithm()
    pg.run_algorithm(algo, 1, verbose=False)
    app = AlgoApp(dockarea, shaper=headless.shaper)
    app._algorithm = algo
    app.save(tmp_path / 'algo.h5')
    check_version(tmp_path / 'algo.h5')
