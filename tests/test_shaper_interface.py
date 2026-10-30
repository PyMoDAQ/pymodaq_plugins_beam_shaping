import types

import pytest

from pymodaq_gui.parameter import Parameter

from pymodaq_plugins_utils.hardware.shaper import (Shaper, ModulatorType, shaper_params, fill_shaper_settings,
                                                   GEOMETRY_NAME, PROPERTIES_NAME)
from pymodaq_plugins_beam_shaping.extensions.spatial_beam_shaping import BeamShaping
from pymodaq_plugins_beam_shaping.utilities.shaper import get_default_shaper, get_shaper, set_shaper


class FakeModule:
    """What the extension has: the DAQ_Move control module, with the settings tree of its plugin"""
    _hw_settings_name = 'actuator_settings'

    def __init__(self, children):
        self.settings = Parameter.create(name='settings', type='group', children=[
            {'name': self._hw_settings_name, 'type': 'group', 'children': children}])


def _extension(actuator):
    return types.SimpleNamespace(_shaper_actuator=actuator, _shaper=None, has_action=lambda name: False)


@pytest.fixture(autouse=True)
def reset_shaper():
    set_shaper(None)
    yield
    set_shaper(None)


def test_extension_uses_the_actuator_once_initialized():
    module = FakeModule(shaper_params())
    extension = _extension(module)
    assert BeamShaping.shaper.fget(extension) == get_default_shaper()  # not initialized yet: default shaper
    assert get_shaper() == get_default_shaper()

    fill_shaper_settings(module.settings.child('actuator_settings'), 'My SLM', 1920, 1080, 8., 9.,
                         modulator_type=ModulatorType.PHASE, has_internal_calibration=True)
    shaper = BeamShaping.shaper.fget(extension)
    assert (shaper.name, shaper.shape, shaper.pixel_size) == ('My SLM', (1080, 1920), 8.)
    assert shaper.has_internal_calibration and shaper.use_internal_calibration
    assert get_shaper() is shaper  # what the sizing functions use

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


def test_default_shaper_from_the_configuration():
    from pymodaq_plugins_beam_shaping import config
    default = get_default_shaper()
    assert (default.width, default.height) == (config('default_shaper', 'width'), config('default_shaper', 'height'))
    assert default.modulator_type == ModulatorType.PHASE
    assert not default.has_internal_calibration


def test_sizes_follow_the_shaper():
    from pymodaq_plugins_beam_shaping.utilities import sizing
    assert sizing.get_slm_size() == get_default_shaper().shape
    set_shaper(Shaper('Other', 640, 480, 12., False, False, ModulatorType.PHASE))
    assert sizing.get_slm_size() == (480, 640)
    assert sizing.get_effective_slm_pixel_size() == 12. * sizing.get_binning()
