"""The compensation of the input beam: a piece of code of its own, chosen in the settings of the algorithm app like the
initial phase. Tested on arrays first, then through the algorithms that use it"""
import numpy as np
import pytest
from pyqtgraph.parametertree import Parameter

from pymodaq_plugins_beam_shaping.algorithms.compensation import CompensationFactory, register_compensations


@pytest.fixture(scope='module')
def factory():
    register_compensations()
    return CompensationFactory()


def make(factory, name, **values):
    """A compensation with its parameters set to the values"""
    compensation_class = factory.get_compensation(name)
    settings = Parameter.create(name=name, type='group', children=compensation_class.params)
    for key, value in values.items():
        settings.child(key).setValue(value)
    return compensation_class(settings)


def gaussian(shape=(32, 48), width=3.):
    y, x = np.indices(shape)
    return np.exp(-(((y - shape[0] / 2) / (shape[0] / width)) ** 2 + ((x - shape[1] / 2) / (shape[1] / width)) ** 2))


def test_the_factory_lists_the_compensations_with_none_first(factory):
    assert factory.compensations[:2] == ['NoCompensation', 'DivideByInput']


def test_an_unknown_compensation_is_refused(factory):
    with pytest.raises(ValueError):
        factory.get_compensation('Unknown')


def test_no_compensation_leaves_the_target_and_has_no_unreachable_region(factory):
    target = np.random.default_rng(0).random((32, 48))
    compensated, unreachable = make(factory, 'NoCompensation').compensate(target, gaussian())
    assert np.array_equal(compensated, target) and unreachable is None


def test_dividing_by_the_input_gives_the_transmission_that_makes_the_target(factory):
    """ output = input x transmission must be the target, up to a factor: the transmission is the target over the
    input, scaled to a maximum of 1, and 0 where the input is below the minimum level (relative to its maximum)"""
    target, beam = np.ones((32, 48)), gaussian()
    compensation = make(factory, 'DivideByInput', min_input_level=0.2)
    transmission, unreachable = compensation.compensate(target, beam)
    reachable = ~unreachable
    assert np.array_equal(unreachable, beam < 0.2 * beam.max())
    assert unreachable.any() and reachable.any()
    assert transmission.max() == pytest.approx(1.)
    assert np.all(transmission[unreachable] == 0)
    output = (beam * transmission)[reachable]
    assert np.allclose(output, output[0])  # flat target: flat output where it can be obtained


def test_a_higher_minimum_level_makes_a_larger_unreachable_region(factory):
    beam = gaussian()
    small = make(factory, 'DivideByInput', min_input_level=0.1).unreachable(beam)
    large = make(factory, 'DivideByInput', min_input_level=0.5).unreachable(beam)
    assert small.sum() < large.sum() and np.all(large[small])


def test_the_unreachable_region_does_not_need_the_target(factory):
    """ What the preview shows before any run: the same region as the one of the compensation of a target"""
    beam = gaussian()
    compensation = make(factory, 'DivideByInput')
    assert np.array_equal(compensation.unreachable(beam), compensation.compensate(np.ones(beam.shape), beam)[1])


def test_the_input_is_averaged_over_the_blocks_of_a_superpixel(factory):
    beam = gaussian()
    compensation = make(factory, 'DivideByInput', min_input_level=0.3)
    _, unreachable = compensation.compensate(np.ones(beam.shape), beam, block=4)
    top, left = unreachable[:4, :4], unreachable[:4, :4]
    assert np.all(top == top[0, 0]) and np.all(left == left[0, 0])  # one value per block


def test_a_null_input_is_not_compensated(factory):
    target = np.ones((8, 8))
    transmission, unreachable = make(factory, 'DivideByInput').compensate(target, np.zeros((8, 8)))
    assert np.array_equal(transmission, target) and unreachable is None


def test_an_input_of_another_shape_is_not_compensated_and_says_so(factory, caplog):
    target = np.ones((8, 8))
    with caplog.at_level('WARNING'):
        transmission, unreachable = make(factory, 'DivideByInput').compensate(target, gaussian())
    assert np.array_equal(transmission, target) and unreachable is None
    assert 'compensat' in caplog.text
