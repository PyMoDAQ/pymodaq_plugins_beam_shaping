"""this package imports opencv, whose pip wheel points Qt to its own bundled platform plugins (QT_QPA_PLATFORM_PLUGIN_PATH).
With PyQt5 this makes the creation of the QApplication abort when slmsuite was imported before it, as the tests of
the controller do. Import cv2 here and drop these variables, so that Qt keeps using the plugins of the installed binding.
"""
import os

try:
    import cv2  # noqa: F401
except ImportError:
    pass

for variable in ('QT_QPA_PLATFORM_PLUGIN_PATH', 'QT_QPA_FONTDIR'):
    os.environ.pop(variable, None)

try:  # the apps read the theme set on the QApplication by mkQApp, pytest-qt reuses this instance
    from pymodaq_gui.qt_utils import mkQApp
    mkQApp('tests')
except ImportError:
    pass
