import types

from pymodaq_gui.parameter import Parameter

from pymodaq_plugins_utils.hardware.shaper import (Shaper, ModulatorType, shaper_params, fill_shaper_settings,
                                                   GEOMETRY_NAME, PROPERTIES_NAME)
from pymodaq_plugins_beam_shaping.extensions.spatial_beam_shaping import BeamShaping
from pymodaq_plugins_beam_shaping.utilities.shaper import get_shaper


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
    assert BeamShaping.shaper.fget(extension) == get_shaper()  # not initialized yet: configuration

    fill_shaper_settings(module.settings.child('actuator_settings'), 'My SLM', 1920, 1080, 8., 9.,
                         modulator_type=ModulatorType.PHASE, has_internal_calibration=True)
    shaper = BeamShaping.shaper.fget(extension)
    assert (shaper.name, shaper.shape, shaper.pixel_size) == ('My SLM', (1080, 1920), 8.)
    assert shaper.has_internal_calibration and shaper.use_internal_calibration

    module.settings.child('actuator_settings', PROPERTIES_NAME, 'use_internal_calibration').setValue(False)
    assert not BeamShaping.shaper.fget(extension).use_internal_calibration


def test_extension_without_actuator_or_groups():
    assert BeamShaping.shaper.fget(_extension(None)) == get_shaper()
    assert BeamShaping.shaper.fget(_extension(FakeModule([]))) == get_shaper()


def test_mock_shaper_gives_the_configured_geometry(qapp):
    from pymodaq.utils.plugin_testing import make_actuator
    from pymodaq_plugins_beam_shaping.daq_move_plugins.daq_move_MockShaper import DAQ_Move_MockShaper
    from pymodaq_plugins_beam_shaping.utilities import sizing

    plugin = make_actuator(DAQ_Move_MockShaper)
    shaper = Shaper.from_settings(plugin.settings.child(GEOMETRY_NAME), plugin.settings.child(PROPERTIES_NAME))
    assert shaper.shape == sizing.get_slm_size()
    assert shaper.pixel_size > 0
    plugin.close()
