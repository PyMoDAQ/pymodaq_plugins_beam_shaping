import types

import pytest

from pymodaq_gui.parameter import Parameter

from pymodaq_plugins_utils.hardware.shaper import (Shaper, ModulatorType, shaper_params, fill_shaper_settings,
                                                   GEOMETRY_NAME, PROPERTIES_NAME)
from pymodaq_plugins_beam_shaping.extensions.spatial_beam_shaping import BeamShaping
from pymodaq_plugins_beam_shaping.utilities.shaper import get_default_shaper


class FakeModule:
    """What the extension has: the DAQ_Move control module, with the settings tree of its plugin"""
    _hw_settings_name = 'actuator_settings'

    def __init__(self, children):
        self.settings = Parameter.create(name='settings', type='group', children=[
            {'name': self._hw_settings_name, 'type': 'group', 'children': children}])


def _extension(actuator):
    return types.SimpleNamespace(_shaper_actuator=actuator, _shaper=None, has_action=lambda name: False)


def test_extension_uses_the_actuator_once_initialized():
    module = FakeModule(shaper_params())
    extension = _extension(module)
    assert BeamShaping.shaper.fget(extension) == get_default_shaper()  # not initialized yet: default shaper

    fill_shaper_settings(module.settings.child('actuator_settings'), 'My SLM', 1920, 1080, 8., 9.,
                         modulator_type=ModulatorType.PHASE, has_internal_calibration=True)
    shaper = BeamShaping.shaper.fget(extension)
    assert (shaper.name, shaper.shape, shaper.pixel_size) == ('My SLM', (1080, 1920), 8.)
    assert shaper.has_internal_calibration and shaper.use_internal_calibration

    module.settings.child('actuator_settings', PROPERTIES_NAME, 'use_internal_calibration').setValue(False)
    assert not BeamShaping.shaper.fget(extension).use_internal_calibration


def test_extension_without_actuator_or_groups():
    assert BeamShaping.shaper.fget(_extension(None)) == get_default_shaper()
    assert BeamShaping.shaper.fget(_extension(FakeModule([]))) == get_default_shaper()


def test_mock_shaper_gives_the_default_shaper(qapp):
    from pymodaq.utils.plugin_testing import make_actuator
    from pymodaq_plugins_beam_shaping.daq_move_plugins.daq_move_MockShaper import DAQ_Move_MockShaper

    plugin = make_actuator(DAQ_Move_MockShaper)
    shaper = Shaper.from_settings(plugin.settings.child(GEOMETRY_NAME), plugin.settings.child(PROPERTIES_NAME))
    assert shaper == get_default_shaper()
    plugin.close()


def _choose_default_modulator(monkeypatch, chosen):
    from pymodaq_plugins_beam_shaping.utilities import shaper as shaper_module
    types_ = ['phase', 'amplitude', 'both']
    types_.insert(0, types_.pop(types_.index(chosen)))
    real_config = shaper_module.config
    monkeypatch.setattr(shaper_module, 'config',
                        lambda *args: types_ if args == ('default_shaper', 'modulator_type') else real_config(*args))


@pytest.mark.parametrize('chosen', ['phase', 'amplitude', 'both'])
def test_extension_modulator_type(monkeypatch, chosen):
    # the default shaper gives it, unless the Shaper actuator tells another one
    _choose_default_modulator(monkeypatch, chosen)
    extension = _extension(None)
    assert BeamShaping.modulator_type.fget(types.SimpleNamespace(shaper=BeamShaping.shaper.fget(extension))) == \
        ModulatorType(chosen)

    module = FakeModule(shaper_params())
    fill_shaper_settings(module.settings.child('actuator_settings'), 'My SLM', 640, 480, 12.,
                         modulator_type=ModulatorType.PHASE)
    extension = _extension(module)
    assert BeamShaping.shaper.fget(extension).modulator_type == ModulatorType.PHASE  # the actuator prevails


@pytest.mark.parametrize('chosen', ['phase', 'amplitude', 'both'])
def test_mock_shaper_accepts_its_modulator_type(qapp, monkeypatch, chosen):
    import numpy as np
    from pymodaq.utils.data import DataActuator
    from pymodaq.utils.plugin_testing import make_actuator
    from pymodaq_plugins_beam_shaping.daq_move_plugins.daq_move_MockShaper import DAQ_Move_MockShaper

    _choose_default_modulator(monkeypatch, chosen)
    plugin = make_actuator(DAQ_Move_MockShaper)
    try:
        assert plugin.settings['shaper_properties', 'modulator_type'] == chosen
        shape = plugin.controller.get_slm_phases().shape
        phase, amplitude = np.full(shape, 1.5), np.full(shape, 0.5)
        # a single array: real for the phase or the amplitude, complex (amplitude * exp(i phase)) for both
        data = {'amplitude': amplitude, 'phase': phase, 'both': amplitude * np.exp(1j * phase)}[chosen]
        plugin.move_abs(DataActuator('shaper', data=[data]))
        assert np.all(plugin.controller.get_slm_phases() == (0 if chosen == 'amplitude' else 1.5))
        assert np.all(plugin.controller.get_slm_amplitudes() == (1 if chosen == 'phase' else 0.5))
    finally:
        plugin.close()


def test_default_shaper_from_the_configuration():
    from pymodaq_plugins_beam_shaping import config
    default = get_default_shaper()
    assert (default.width, default.height) == (config('default_shaper', 'width'), config('default_shaper', 'height'))
    assert default.modulator_type == ModulatorType.PHASE
    assert not default.has_internal_calibration


@pytest.mark.parametrize('chosen', ['phase', 'amplitude', 'both'])
def test_default_shaper_modulator_type_is_chosen_in_the_preferences(monkeypatch, chosen):
    # the preferences show the list as a combobox and move the selected item first
    from pymodaq_plugins_beam_shaping.utilities import shaper as shaper_module
    types_ = ['phase', 'amplitude', 'both']
    types_.insert(0, types_.pop(types_.index(chosen)))
    real_config = shaper_module.config
    monkeypatch.setattr(shaper_module, 'config',
                        lambda *args: types_ if args == ('default_shaper', 'modulator_type') else real_config(*args))
    assert get_default_shaper().modulator_type == ModulatorType(chosen)


def test_sizes_follow_the_shaper():
    from pymodaq_plugins_beam_shaping.utilities import sizing
    default = get_default_shaper()
    assert sizing.get_slm_size(default) == default.shape
    other = Shaper('Other', 640, 480, 12., False, False, ModulatorType.PHASE)
    assert sizing.get_slm_size(other) == (480, 640)
    assert sizing.get_effective_slm_pixel_size(other) == 12. * sizing.get_binning()


def test_preference_overwrites_the_calibration_choice_of_the_actuator(monkeypatch, caplog):
    from pymodaq_plugins_beam_shaping.extensions import spatial_beam_shaping as module_under_test
    module = FakeModule(shaper_params())
    fill_shaper_settings(module.settings.child('actuator_settings'), 'My SLM', 1920, 1080, 8.,
                         has_internal_calibration=True)
    extension = _extension(module)
    use = module.settings.child('actuator_settings', PROPERTIES_NAME, 'use_internal_calibration')

    monkeypatch.setattr(module_under_test, 'plugin_config', lambda *args: False)
    BeamShaping.apply_calibration_preference(extension)
    assert not use.value()
    assert 'Use internal calibration' in caplog.text

    monkeypatch.setattr(module_under_test, 'plugin_config', lambda *args: True)
    BeamShaping.apply_calibration_preference(extension)
    assert use.value()


def test_preference_does_not_touch_a_shaper_without_internal_calibration():
    from pymodaq_plugins_beam_shaping.extensions import spatial_beam_shaping as module_under_test
    module = FakeModule(shaper_params())
    fill_shaper_settings(module.settings.child('actuator_settings'), 'My SLM', 1920, 1080, 8.,
                         has_internal_calibration=False)
    BeamShaping.apply_calibration_preference(_extension(module))
    assert not module.settings.child('actuator_settings', PROPERTIES_NAME, 'use_internal_calibration').value()
    BeamShaping.apply_calibration_preference(_extension(None))  # no actuator: nothing to do


def test_wavelength_of_the_setup_is_imposed_to_the_actuator(monkeypatch, caplog):
    from pymodaq_plugins_beam_shaping.extensions import spatial_beam_shaping as module_under_test
    module = FakeModule(shaper_params() + [{'name': 'wavelength_nm', 'type': 'float', 'value': 515.}])
    module.initialized_state = True
    extension = _extension(module)
    monkeypatch.setattr(module_under_test, 'plugin_config', lambda *args: 800.)

    BeamShaping.apply_wavelength(extension)
    assert module.settings['actuator_settings', 'wavelength_nm'] == 800.
    assert 'Initialize the actuator again' in caplog.text

    caplog.clear()
    BeamShaping.apply_wavelength(extension)  # nothing to change anymore
    assert not caplog.text


def test_wavelength_ignored_by_a_plugin_that_does_not_need_it():
    BeamShaping.apply_wavelength(_extension(FakeModule(shaper_params())))
    BeamShaping.apply_wavelength(_extension(None))
