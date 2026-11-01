"""The status of an algorithm (written by hand in its class) is shown next to its name, the broken ones are hidden"""
import pytest
from qtpy import QtCore, QtWidgets

from pymodaq_gui.utils.dock import DockArea

from pymodaq_plugins_beam_shaping import config as plugin_config
from pymodaq_plugins_beam_shaping.algorithms import AlgorithmFactory, AlgoBase
from pymodaq_plugins_beam_shaping.algorithms.algorithm_app import AlgoApp, show_broken_algorithms
from pymodaq_plugins_beam_shaping.algorithms.utils import AlgoStatus
from pymodaq_plugins_beam_shaping.utilities.shaper import ModulatorType, Shaper


def _shaper(modulator_type='phase'):
    return Shaper('SLM', 640, 480, 12., False, False, ModulatorType(modulator_type))


def test_every_algorithm_of_the_package_declares_its_status():
    assert AlgoBase.STATUS == AlgoStatus.UNTESTED  # an external algorithm that says nothing
    for name, algo in AlgorithmFactory.algorithms_registry.items():
        if algo.__module__.startswith('pymodaq_plugins_beam_shaping.algorithms.algorithms'):
            assert 'STATUS' in vars(algo), name
            assert AlgoStatus(algo.STATUS) in AlgoStatus


@pytest.fixture
def statuses():
    """Two registered phase algorithms, one tested and one broken, put first in the configuration"""
    from pymodaq_plugins_beam_shaping.algorithms.algorithms.direct import Direct

    class Good(Direct):
        ALGO_NAME = 'GoodForTest'
        STATUS = AlgoStatus.TESTED
        STATUS_NOTE = 'checked on the bench'

    class Bad(Direct):
        ALGO_NAME = 'BadForTest'
        STATUS = AlgoStatus.BROKEN

    for klass in (Good, Bad):
        AlgorithmFactory.register_algorithm()(klass)
    default_algo = plugin_config('algo', 'default_algo')
    show_broken = show_broken_algorithms()
    plugin_config['algo', 'default_algo'] = [Good.ALGO_NAME, Bad.ALGO_NAME] + list(default_algo)
    yield Good, Bad
    plugin_config['algo', 'default_algo'] = default_algo
    plugin_config['algo', 'show_broken'] = show_broken
    for klass in (Good, Bad):
        AlgorithmFactory.algorithms_registry.pop(klass.ALGO_NAME)


@pytest.fixture
def dockarea(qtbot):
    window = QtWidgets.QMainWindow()
    area = DockArea()
    window.setCentralWidget(area)
    qtbot.addWidget(window)
    window.show()
    yield area


def _items(app):
    combo = app.get_action('algorithms').widget
    return [combo.itemText(ind) for ind in range(combo.count())]


def test_status_next_to_the_name_and_broken_hidden(qtbot, dockarea, statuses):
    good, bad = statuses
    plugin_config['algo', 'show_broken'] = False
    app = AlgoApp(dockarea, shaper=_shaper())
    combo = app.get_action('algorithms').widget
    label = app.get_action('algorithm_status').widget

    assert bad.ALGO_NAME not in _items(app)
    assert combo.currentText() == good.ALGO_NAME
    assert 'tested' in label.text()
    assert 'checked on the bench' in label.toolTip()
    assert 'tested' in combo.itemData(0, QtCore.Qt.ToolTipRole)
    assert not combo.itemIcon(0).isNull()

    combo.setCurrentIndex(1)  # the label follows the selection
    other = AlgorithmFactory.get_algorithm(combo.currentText())
    assert str(other.STATUS) in label.text()


def test_broken_shown_if_the_configuration_asks(qtbot, dockarea, statuses):
    good, bad = statuses
    plugin_config['algo', 'show_broken'] = True
    app = AlgoApp(dockarea, shaper=_shaper())
    assert bad.ALGO_NAME in _items(app)
