import numpy as np
import pytest
from pymodaq_plugins_beam_shaping.field import Field


class TestField:

    def test_field_init_empty(self):
        NAME = 'myname'
        f = Field(NAME)
        assert f.name == NAME

    def test_field_init_amplitude(self):
        amp_array = np.random.random((10, 15))

        field = Field('amplitude', amplitude=amp_array)
        assert np.allclose(field.amplitude, amp_array)
        assert np.allclose(field.phase, np.zeros_like(amp_array))

    def test_field_init_phase(self):
        phase_array = np.random.random((10, 15))

        field = Field('amplitude', phase=phase_array)
        assert np.allclose(field.phase, phase_array)
        assert np.allclose(field.amplitude, np.ones_like(phase_array))





def test_normalise_to_intensity_matches_the_total_intensity_and_keeps_the_phase():
    reference = Field('reference', amplitude=np.full((4, 4), 2.), phase=np.full((4, 4), 0.5))  # total intensity 64
    field = Field('field', amplitude=np.linspace(1., 2., 16).reshape(4, 4), phase=np.full((4, 4), 0.3))

    normalised = reference.normalise_to_intensity(field)

    assert np.sum(normalised.intensity) == pytest.approx(np.sum(reference.intensity))
    assert np.allclose(normalised.amplitude / field.amplitude, normalised.amplitude[0, 0] / field.amplitude[0, 0])
    assert np.allclose(normalised.phase, 0.3)
    assert np.sum(field.intensity) != pytest.approx(np.sum(reference.intensity))  # the field itself is untouched
