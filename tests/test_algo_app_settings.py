"""The settings of the AlgoApp are saved in a config file and loaded back: the ones of the app (per algorithm) and the
own settings of the algorithm. Tested on a fake config in memory, not the one of the user"""
import pytest
from qtpy import QtWidgets

from pymodaq_utils.config import ConfigError
from pymodaq_gui.utils.dock import DockArea

OL2014 = 'OL2014 - Amplitude-Phase Checkerboard'


class FakeConfig:
    """ What the ConfigSaverLoader asks to a config: a call with the path, item assignment, save"""

    def __init__(self):
        self.data = {}

    def __call__(self, *path):
        if tuple(path) not in self.data:
            raise ConfigError(path)
        return self.data[tuple(path)]

    def __setitem__(self, path, value):
        self.data[tuple(path)] = value

    def save(self):
        pass


@pytest.fixture
def config(monkeypatch):
    from pymodaq_plugins_beam_shaping.algorithms import algorithm_app
    fake = FakeConfig()
    monkeypatch.setattr(algorithm_app, 'algo_config', fake)
    return fake


@pytest.fixture
def make_app(qtbot, config):
    windows = []

    def make():
        from pymodaq_plugins_beam_shaping.algorithms.algorithm_app import AlgoApp
        area = DockArea()
        window = QtWidgets.QMainWindow()
        window.setCentralWidget(area)
        qtbot.addWidget(window)
        window.show()
        windows.append(window)
        return AlgoApp(area)

    return make


def set_app_settings(app, values):
    for path, value in values.items():
        app.settings.child(*path.split('/')).setValue(value)


def app_settings(app, paths):
    return {path: app.settings[tuple(path.split('/'))] for path in paths}


APP_VALUES = {'crosstalk/apply': True, 'crosstalk/value': 0.8, 'phase_manipulation/wrap_value': 4,
              'ini_phase_group/ini_phase_factory': 'QuadraticPhase',
              'compensation_group/compensation_params/DivideByInput/min_input_level': 0.4}


def test_no_algorithm_has_a_slash_in_its_name():
    """ The name is a section of the config file, a slash would make a path of it"""
    from pymodaq_plugins_beam_shaping.algorithms.factory import AlgorithmFactory
    assert all('/' not in name for name in AlgorithmFactory.algorithms_registry)
    assert OL2014 in AlgorithmFactory.algorithms_registry


def test_the_settings_of_the_app_are_back_after_a_restart(make_app):
    """ Not only the first one of the tree: loading a setting must not save the others as they are"""
    app = make_app()
    app.set_algorithm('Parallel Lee')
    set_app_settings(app, APP_VALUES)
    restarted = make_app()
    restarted.set_algorithm('Parallel Lee')
    assert app_settings(restarted, APP_VALUES) == APP_VALUES


def test_the_settings_of_an_algorithm_do_not_leak_to_another(make_app):
    app = make_app()
    app.set_algorithm('Parallel Lee')
    set_app_settings(app, APP_VALUES)
    app.set_algorithm(OL2014)
    set_app_settings(app, {'crosstalk/apply': False, 'crosstalk/value': 0.1,
                           'compensation_group/compensation_params/DivideByInput/min_input_level': 0.7})
    app.set_algorithm('Parallel Lee')
    assert app_settings(app, APP_VALUES) == APP_VALUES
    app.set_algorithm(OL2014)
    assert app_settings(app, ['crosstalk/apply', 'crosstalk/value']) == {'crosstalk/apply': False,
                                                                         'crosstalk/value': 0.1}


def test_the_default_compensation_of_an_algorithm_does_not_replace_what_was_saved_for_another(make_app, config):
    app = make_app()
    app.set_algorithm('Parallel Lee')
    app.settings.child('compensation_group', 'compensation_factory').setValue('NoCompensation')
    app.set_algorithm(OL2014)  # its default is DivideByInput
    assert config.data[('Parallel Lee', 'compensation_group', 'compensation_factory')] == 'NoCompensation'
    app.set_algorithm('Parallel Lee')
    assert app.settings['compensation_group', 'compensation_factory'] == 'NoCompensation'


def test_the_own_settings_of_the_algorithm_are_saved_and_loaded(make_app, config):
    app = make_app()
    app.set_algorithm('Parallel Lee')
    app.algorithm.settings.child('px').setValue(8)
    app.algorithm.settings.child('binarize').setValue(False)
    app.set_algorithm('Gerchberg-Saxton')
    app.set_algorithm('Parallel Lee')
    assert app.algorithm.settings['px'] == 8 and app.algorithm.settings['binarize'] is False
    restarted = make_app()
    restarted.set_algorithm('Parallel Lee')
    assert restarted.algorithm.settings['px'] == 8 and restarted.algorithm.settings['binarize'] is False


def test_loading_the_own_settings_does_not_run_the_algorithm(make_app):
    """ OL2014 is recomputed when one of its settings changes: not while loading them"""
    app = make_app()
    app.set_algorithm(OL2014)
    app.algorithm.settings.child('block_size').setValue(7)
    app.set_algorithm('Parallel Lee')
    commands = []
    app.command_runner.connect(commands.append)  # what asks the runner to compute
    app.set_algorithm(OL2014)
    assert app.algorithm.settings['block_size'] == 7 and commands == []
    app.algorithm.settings.child('block_size').setValue(6)  # a change of the user does run it
    assert len(commands) == 1
