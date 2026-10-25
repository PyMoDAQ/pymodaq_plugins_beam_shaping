from types import SimpleNamespace

import pytest

from pymodaq_plugins_beam_shaping.algorithms import factory
from pymodaq_plugins_beam_shaping.algorithms.factory import AlgorithmFactory, register_external_algorithms
from pymodaq_plugins_beam_shaping.algorithms.utils import LensSetup


def fake_entry_point(name, load):
    return SimpleNamespace(name=name, value=f'fake_package.{name}', load=load)


@pytest.fixture
def clean_registry():
    before = dict(AlgorithmFactory.algorithms_registry)
    yield
    AlgorithmFactory.algorithms_registry.clear()
    AlgorithmFactory.algorithms_registry.update(before)


def test_external_algorithm_is_registered(monkeypatch, clean_registry):
    def load():
        @AlgorithmFactory.register_algorithm()
        class External(factory.AlgoBase):
            ALGO_NAME = 'External test algorithm'
            SETUP_TYPE = LensSetup.TwoF
        return External

    monkeypatch.setattr(factory, 'entry_points', lambda group: [fake_entry_point('external', load)])
    assert 'External test algorithm' not in AlgorithmFactory.algorithms_registry

    register_external_algorithms()

    assert 'External test algorithm' in AlgorithmFactory.algorithms_registry


def test_entry_point_group_is_the_documented_one(monkeypatch):
    groups = []
    monkeypatch.setattr(factory, 'entry_points', lambda group: groups.append(group) or [])
    register_external_algorithms()
    assert groups == ['pymodaq_plugins_beam_shaping.algorithms']


def test_broken_package_does_not_prevent_the_others(monkeypatch, clean_registry):
    def broken():
        raise ModuleNotFoundError('missing dependency')

    def good():
        return 'module'

    monkeypatch.setattr(factory, 'entry_points',
                        lambda group: [fake_entry_point('broken', broken), fake_entry_point('good', good)])
    assert register_external_algorithms() == ['module']
