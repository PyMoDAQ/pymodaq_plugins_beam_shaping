# -*- coding: utf-8 -*-
"""Outline of a region (a boolean mask) drawn on the 2D viewers of a ViewerDispatcher"""
from typing import Optional
from weakref import WeakKeyDictionary

import numpy as np
import pyqtgraph as pg

LEVEL = 0.5  # between the 0 and 1 of the mask


class RegionOutline:
    """ Draw the contour of a mask (an isocurve at the level 0.5 of the mask) on every 2D viewer of a dispatcher

    The contour is a child of the image item of each viewer, so it follows its pixels whatever the scaling of the axes
    of the viewer: a mask of the same shape as the image is drawn at the right place, in the plane of the viewer
    (the target and the output of a 4f setup have the shape of the modulator, the axes only differ by the scale).
    One item per viewer, reused for the next masks.

    Parameters
    ----------
    color: the color of the outline
    """

    def __init__(self, color='r'):
        self._pen = pg.mkPen(color, width=2)
        self._items: 'WeakKeyDictionary' = WeakKeyDictionary()

    def show(self, dispatcher, mask: Optional[np.ndarray]):
        """ Draw the outline of the mask on all the 2D viewers of the dispatcher (or of the list of viewers), hide it
        if there is no mask or if the mask is empty"""
        has_region = mask is not None and bool(np.any(mask))
        for viewer in getattr(dispatcher, 'viewers', dispatcher):
            image = self._image_item(viewer)
            if image is None:
                continue
            item = self._items.get(viewer)
            item_parent = None
            try:
                item_parent = item.parentItem() if item is not None else None
            except RuntimeError:  # deleted with the image item that the viewer replaced: make another one
                item = None
            if item is None:
                item = pg.IsocurveItem(level=LEVEL, pen=self._pen, axisOrder='row-major')
                item.setZValue(5)  # above the images (see the ROI select of the viewers)
                self._items[viewer] = item
            if item_parent is not image:  # the viewer built other image items
                item.setParentItem(image)
            if has_region:
                item.setData(np.asarray(mask, dtype=float))
                item.setLevel(LEVEL)
            item.setVisible(has_region)

    @staticmethod
    def _image_item(viewer):
        try:
            return viewer.view.data_displayer.get_image('red')
        except AttributeError:  # not a 2D viewer
            return None
