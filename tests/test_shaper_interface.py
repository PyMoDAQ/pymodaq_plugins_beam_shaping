import pytest
from pymodaq_gui.parameter import Parameter

from pymodaq_plugins_beam_shaping.utilities.shaper import (ShaperGeometry, shaper_geometry_params,
                                                           get_module_shaper_geometry)


def test_geometry():
    geometry = ShaperGeometry(width=1920, height=1080, pixel_size_x=8., pixel_size_y=9.)
    assert geometry.shape == (1080, 1920)
    assert geometry.pixel_size == (8., 9.)


class FakeModule:
    """What the extension has: the DAQ_Move control module, with the settings tree of its plugin"""
    _hw_settings_name = 'actuator_settings'

    def __init__(self, children):
        self.settings = Parameter.create(name='settings', type='group', children=[
            {'name': self._hw_settings_name, 'type': 'group', 'children': children}])


def test_read_from_module():
    module = FakeModule([shaper_geometry_params()])
    assert get_module_shaper_geometry(module) is None  # not filled yet: plugin not initialized
    group = module.settings.child('actuator_settings', 'shaper_geometry')
    for name, value in (('width', 1920), ('height', 1080), ('pixel_size_x', 8.), ('pixel_size_y', 9.)):
        group.child(name).setValue(value)
    assert get_module_shaper_geometry(module) == ShaperGeometry(1920, 1080, 8., 9.)


def test_plugin_without_the_group():
    assert get_module_shaper_geometry(FakeModule([])) is None
    assert get_module_shaper_geometry(object()) is None


def test_mock_shaper_gives_the_configured_geometry(qapp):
    from pymodaq.utils.plugin_testing import make_actuator
    from pymodaq_plugins_beam_shaping.daq_move_plugins.daq_move_MockShaper import DAQ_Move_MockShaper
    from pymodaq_plugins_beam_shaping.utilities import sizing

    plugin = make_actuator(DAQ_Move_MockShaper)
    geometry = ShaperGeometry.from_parameter(plugin.settings.child('shaper_geometry'))
    assert geometry.shape == sizing.get_slm_size()
    assert geometry.pixel_size_x > 0
    plugin.close()
