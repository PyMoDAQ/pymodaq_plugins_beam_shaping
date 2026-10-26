"""Masking regions are expressed in real units (as the ROIs of the viewers) and converted to indexes"""
import numpy as np
import pytest
from qtpy import QtWidgets

from pymodaq_data import Q_
from pymodaq_gui.utils.dock import DockArea

from pymodaq_plugins_beam_shaping.utilities import regions, sizing


PIXELS = (Q_(8., 'um'), Q_(8., 'um'))


def test_slices_to_indexes_matches_vsig():
    from pymodaq_data.data import DataRaw, Axis
    shape = (100, 200)
    axes = [Axis('y', units='m', scaling=8e-6, offset=0, index=0, size=shape[0]),
            Axis('x', units='m', scaling=8e-6, offset=0, index=1, size=shape[1])]
    dwa = DataRaw('d', data=[np.zeros(shape)], axes=axes, nav_indexes=())
    slices = (slice(80., 160.), slice(16., 96.))
    idx = regions.slices_to_indexes(slices, PIXELS, shape)
    assert idx == (slice(10, 20), slice(2, 12))
    assert dwa.isig[idx].shape == dwa.vsig[regions.to_axis_units(slices)].shape


def test_slices_to_indexes_clipped():
    idx = regions.slices_to_indexes((slice(-1e3, 1e9), slice(0, 1e9)), PIXELS, (100, 200))
    assert idx == (slice(0, 100), slice(0, 200))


def test_default_slices_are_two_thirds_centered():
    pos, size = regions.get_effective_area(PIXELS)
    slices = regions.default_slices(PIXELS)
    for _slice, p, s in zip(slices, pos, size):
        assert _slice.stop - _slice.start == pytest.approx(2 / 3 * s)
        assert (_slice.start + _slice.stop) / 2 == pytest.approx(p + s / 2)
    assert regions.are_slices_in_area(slices, PIXELS)


def test_legacy_pixel_slices_are_not_valid():
    legacy = regions.parse_slices('(slice(277, 1770, None), slice(252, 1795, None))')
    assert not regions.are_slices_in_area(legacy, PIXELS)
    assert regions.parse_slices('') is None


def test_slices_str_roundtrip():
    slices = (slice(10., 20.), slice(np.float64(30.), 40.))
    assert regions.parse_slices(regions.slices_to_str(slices)) == (slice(10., 20.), slice(30., 40.))


@pytest.fixture
def dockarea(qtbot):
    window = QtWidgets.QMainWindow()
    area = DockArea()
    window.setCentralWidget(area)
    qtbot.addWidget(window)
    window.show()
    yield area


def test_loader_mask_in_real_units(qtbot, dockarea):
    from pymodaq_plugins_beam_shaping.field.field_loader_app import FieldLoaderApp

    app = FieldLoaderApp(dockarea, title='loader')
    app.settings.child('loader').setValue('GaussianIntensity')
    app.load_field()
    app.settings.child('utils', 'masking', 'show_mask').setValue(True)

    region = app.get_mask_region()
    assert regions.are_slices_in_area(region, app.get_pixel_sizes())
    pos, size = sizing.get_effective_area_pos_size_in_pxls()
    idx = app.get_mask_as_slices()
    for _slice, p, s in zip(idx, pos, size):
        assert _slice.stop - _slice.start == pytest.approx(2 / 3 * s, abs=2)
        assert (_slice.start + _slice.stop) / 2 == pytest.approx(p + s / 2, abs=2)

    # moving the ROI updates the setting in meters and the indexes follow
    pxl = app.get_pixel_sizes()[0].m_as('m')  # the ROI is in the units of the axes
    app.mask.setPos((int(pos[1]) * pxl, int(pos[0]) * pxl))
    app.mask.setSize((100 * pxl, 50 * pxl))
    app.update_mask_slices()
    idx = app.get_mask_as_slices()
    assert (idx[0].stop - idx[0].start, idx[1].stop - idx[1].start) == (50, 100)
    assert app.get_mask_array().sum() > 0


def test_algo_app_slices(qtbot, dockarea):
    from pymodaq_plugins_beam_shaping.algorithms.algorithm_app import AlgoApp
    from pymodaq_plugins_beam_shaping.algorithms.utils import ApplyMaskTo
    from pymodaq_plugins_beam_shaping.field import Field

    app = AlgoApp(dockarea)
    shape = sizing.get_effective_needed_field_size()
    app.set_target_field(Field(amplitude=np.ones(shape), pixel_sizes=PIXELS))
    region = app.get_mask_region(ApplyMaskTo.TARGET)
    assert region is not None and regions.are_slices_in_area(region, PIXELS)

    app.settings.child(str(ApplyMaskTo.TARGET), 'apply_mask').setValue(True)
    app.update_target_slices((slice(0., 1e9), slice(0., 1e9)))  # constrained to the effective area
    idx = app.get_mask_as_slices(ApplyMaskTo.TARGET)
    pos, size = sizing.get_effective_area_pos_size_in_pxls()
    for _slice, p, s in zip(idx, pos, size):
        assert _slice.start == pytest.approx(p, abs=1)
        assert _slice.stop == pytest.approx(p + s, abs=1)
