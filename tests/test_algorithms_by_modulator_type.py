"""The algorithms offered follow the modulation type of the shaper"""
import numpy as np
import pytest
from qtpy import QtWidgets

from pymodaq_gui.utils.dock import DockArea

from pymodaq_plugins_beam_shaping.algorithms import AlgorithmFactory, AlgoBase
from pymodaq_plugins_beam_shaping.algorithms.algorithm_app import AlgoApp
from pymodaq_plugins_beam_shaping.utilities.shaper import ModulatorType, Shaper


def _shaper(modulator_type):
    return Shaper('SLM', 640, 480, 12., False, False, ModulatorType(modulator_type))


@pytest.fixture
def amplitude_algorithm():
    """A registered algorithm computing a mask for amplitude modulators only"""
    from pymodaq_plugins_beam_shaping.algorithms.algorithms.direct import Direct

    class DirectAmplitude(Direct):
        ALGO_NAME = 'DirectAmplitudeForTest'
        MODULATOR_TYPES = (ModulatorType.AMPLITUDE, )

    AlgorithmFactory.register_algorithm()(DirectAmplitude)
    yield DirectAmplitude
    AlgorithmFactory.algorithms_registry.pop(DirectAmplitude.ALGO_NAME)


def test_default_is_phase_and_both_accepts_everything():
    assert AlgoBase.MODULATOR_TYPES == (ModulatorType.PHASE, )
    assert AlgoBase.supports(ModulatorType.PHASE) and not AlgoBase.supports(ModulatorType.AMPLITUDE)
    assert AlgoBase.supports(ModulatorType.BOTH)


def test_factory_lists_the_algorithms_of_a_modulator_type(amplitude_algorithm):
    name = amplitude_algorithm.ALGO_NAME
    assert name in AlgorithmFactory.algorithms_for(ModulatorType.AMPLITUDE)
    assert name not in AlgorithmFactory.algorithms_for(ModulatorType.PHASE)
    assert name in AlgorithmFactory.algorithms_for(ModulatorType.BOTH)


@pytest.fixture
def dockarea(qtbot):
    window = QtWidgets.QMainWindow()
    area = DockArea()
    window.setCentralWidget(area)
    qtbot.addWidget(window)
    window.show()
    yield area


def test_algo_app_follows_the_shaper(qtbot, dockarea, amplitude_algorithm):
    app = AlgoApp(dockarea, shaper=_shaper('phase'))
    combo = app.get_action('algorithms')
    items = lambda: [combo.itemText(ind) for ind in range(combo.count())]
    assert amplitude_algorithm.ALGO_NAME not in items()
    phase_algorithms = items()
    assert phase_algorithms

    app.shaper = _shaper('amplitude')  # the current algorithm cannot be used anymore: another one is selected
    assert items() == [amplitude_algorithm.ALGO_NAME]  # the only one for an amplitude shaper
    assert all(AlgorithmFactory.get_algorithm(name).supports(ModulatorType.AMPLITUDE) for name in items())
    assert combo.currentText() in items()

    app.shaper = _shaper('phase')
    assert items() == phase_algorithms
