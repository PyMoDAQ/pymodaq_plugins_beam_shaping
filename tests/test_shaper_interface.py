import pytest

from pymodaq_plugins_beam_shaping.utilities.shaper import ShaperGeometry, ShaperInterface, has_shaper_interface


def test_geometry():
    geometry = ShaperGeometry(width=1920, height=1080, pixel_size_x=8., pixel_size_y=9.)
    assert geometry.shape == (1080, 1920)
    assert geometry.pixel_size == (8., 9.)


def test_interface_has_to_be_implemented():
    class Plugin(ShaperInterface):
        pass

    with pytest.raises(NotImplementedError):
        Plugin().get_shaper_geometry()


def test_duck_typing():
    class Other:
        def get_shaper_geometry(self):
            return ShaperGeometry(2, 3, 4., 4.)

    assert has_shaper_interface(Other())
    assert has_shaper_interface(ShaperInterface())
    assert not has_shaper_interface(object())


def test_mock_shaper_gives_the_configured_geometry(qapp):
    from pymodaq.utils.plugin_testing import make_actuator
    from pymodaq_plugins_beam_shaping.daq_move_plugins.daq_move_MockShaper import DAQ_Move_MockShaper
    from pymodaq_plugins_beam_shaping.utilities import sizing

    plugin = make_actuator(DAQ_Move_MockShaper)
    geometry = plugin.get_shaper_geometry()
    assert isinstance(plugin, ShaperInterface)
    assert geometry.shape == sizing.get_slm_size()
    assert geometry.pixel_size_x > 0
    plugin.close()
