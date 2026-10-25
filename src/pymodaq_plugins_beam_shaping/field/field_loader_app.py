from typing import Tuple, Union
from pathlib import Path
import numpy as np
from qtpy import QtWidgets, QtCore
from skimage.transform import rescale, resize
from scipy.ndimage import gaussian_filter
from pyqtgraph import ROI as pgROI

from pymodaq_utils.config import GlobalConfig
from pymodaq_utils.math_utils import normalize, greater2n, gauss2D
from pymodaq_utils.enums import StrEnum

from pymodaq_data import DataToExport, DataCalculated, DataDim
from pymodaq_data.h5modules.saving import H5SaverLowLevel
from pymodaq_data.h5modules.data_saving import DataSaverLoader, GroupType

from pymodaq_gui.plotting.items.roi import RectROI
from pymodaq_gui.managers.parameter_manager import Parameter
from pymodaq_gui.plotting.data_viewers.viewer2D import Viewer2D
from pymodaq_gui.utils.custom_app import CustomApp
from pymodaq_gui.utils.dock import DockArea, Dock
from pymodaq_gui.utils.file_io import select_file
from pymodaq_gui.parameter.ioxml import parameter_to_xml_string
from pymodaq_plugins_beam_shaping import config as plugin_config
from pymodaq_plugins_beam_shaping.field import Field, Q_, LoaderFactory, FieldLoader
from pymodaq_plugins_beam_shaping.utilities.masking import MaskType

from pymodaq_plugins_beam_shaping.utilities.sizing import (get_effective_needed_field_size,
                                                           get_effective_slm_pixel_size,
                                                           get_effective_slm_size,
                                                           get_effective_area_pos_size_in_pxls)

config = GlobalConfig()
field_loader_factory = LoaderFactory()


class NormaliseTo(StrEnum):
    NONE = 'none'
    MAX = 'max'
    INTENSITY = 'intensity'


class FieldLoaderApp(CustomApp):
    settings_name = "LoaderAppSettings"
    params = [
        {'title': 'Loader', 'name': 'loader', 'type': 'list',
         'limits': field_loader_factory.field_loaders,
         'value': field_loader_factory.field_loaders[0]},
        {'title': 'Reload:', 'name': 'reload', 'type': 'bool_push', 'label': 'Reload!',
         'value': False},
        {'title': 'Save:', 'name': 'save', 'type': 'bool_push', 'label': 'Save Field!',
         'value': False},
        {'title': 'Initial size', 'name': 'ini_size', 'type': 'group', 'children': [
            {'title': 'Height', 'name': 'height', 'type': 'int', 'value': 0, 'readonly': True},
            {'title': 'Width', 'name': 'width', 'type': 'int', 'value': 0, 'readonly': True},
        ]},
        {'title': 'Needed size', 'name': 'needed_size', 'type': 'group', 'children': [
            {'title': 'Pixel Height (µm)', 'name': 'pixel_height', 'type': 'float',
             'value': get_effective_slm_pixel_size(),
             'readonly': False},
            {'title': 'Pixel Width (µm)', 'name': 'pixel_width', 'type': 'float',
             'value': get_effective_slm_pixel_size(),
             'readonly': False},
            {'title': 'Height', 'name': 'height', 'type': 'int',
             'value': get_effective_needed_field_size()[0],
             'readonly': True},
            {'title': 'Width', 'name': 'width', 'type': 'int',
             'value': get_effective_needed_field_size()[1],
             'readonly': True},
            {'title': 'Show on Viewer', 'name': 'show_needed_area', 'type': 'bool_push',
             'value': True,},
        ]},
        {'title': 'utils', 'name': 'utils', 'type': 'group', 'children': [
            {'title': 'Show field', 'name': 'show_field', 'type': 'bool_push', 'value': True},

            {'title': 'Flip ud', 'name': 'flipud', 'type': 'bool', 'value': False},
            {'title': 'Flip lr', 'name': 'fliplr', 'type': 'bool', 'value': False},
            {'title': 'Sizing', 'name': 'sizing', 'type': 'group', 'children': [
                {'title': 'Scaling', 'name': 'scaling', 'type': 'float', 'value': 1., },
                {'title': 'Do Scaling', 'name': 'do_scaling', 'type': 'bool', 'value': True},
                {'title': 'Keep aspect ratio', 'name': 'aspect_ratio', 'type': 'bool',
                 'value': True},
                {'title': 'Height', 'name': 'height', 'type': 'int', 'value': 0, 'readonly': True},
                {'title': 'Width', 'name': 'width', 'type': 'int', 'value': 0, 'readonly': True},
            ]},
            {'title': 'Smoothing', 'name': 'smoothing', 'type': 'group', 'children': [
                {'title': 'Apply:', 'name': 'apply_smoothing', 'type': 'bool', 'value': False},
                {'title': 'Sigma X (pxl)', 'name': 'sigma_x', 'type': 'int', 'value': 10,},
                {'title': 'Sigma Y (pxl)', 'name': 'sigma_y', 'type': 'int', 'value': 10, },
            ]},
            {'title': 'Normalisation', 'name': 'normalisation', 'type': 'list', 'value': NormaliseTo.MAX,
             'limits': NormaliseTo.names()},
            {'title': 'Masking', 'name': 'masking', 'type': 'group', 'children': [
                {'title': 'Mask Type', 'name': 'mask_type', 'type': 'list', 'value': str(MaskType.SQUARE),
                 'limits': MaskType.names()},
                {'title': 'Slices', 'name': 'slices', 'type': 'str',
                 'value': '(slice(338, 757, None), slice(665, 1770, None))'},
                {'title': 'Boundary', 'name': 'boundary', 'type': 'group', 'children': [
                    {'title': 'Apply', 'name': 'apply_boundary', 'type': 'bool', 'value': False},
                    {'title': 'Sharpness', 'name': 'sharpness', 'type': 'int', 'value': 3, }
                ]},
                {'title': 'Show On', 'name': 'show_on', 'type': 'list',
                 'value': 'Amplitude', 'limits': ['Amplitude', 'Phase']},
                {'title': 'Show Mask', 'name': 'show_mask', 'type': 'bool', 'value': False},
                {'title': 'Apply Mask', 'name': 'apply_mask', 'type': 'bool', 'value': False},
            ]}
        ]},
    ]

    field_signal = QtCore.Signal(Field)

    def __init__(self, dockarea: DockArea, title: str = None, **kwargs):
        super().__init__(parent=dockarea, title=title)
        self._main_widget: QtWidgets.QWidget = None
        self.field_widget: QtWidgets.QWidget = None
        self.settings_widget: QtWidgets.QWidget = None
        self._loader_settings_widget: QtWidgets.QWidget = None

        self.amp_viewer: Viewer2D = None
        self.phase_viewer: Viewer2D = None

        self.mask: RectROI = None

        self._field_loader: FieldLoader = None

        self._ini_field = Field()
        self.field = Field()

        self.setup_ui()

        self.loader_kwargs = kwargs

        self.loader = field_loader_factory.field_loaders[0]

    @staticmethod
    def normalise(field: Field, normalise_to = NormaliseTo.MAX):
        """ Normalise inplace """
        if normalise_to == NormaliseTo.NONE:
            pass
        elif normalise_to == NormaliseTo.MAX:
            field.amplitude = field.amplitude /  np.max(field.amplitude)
        elif normalise_to == NormaliseTo.INTENSITY:
            field.amplitude =  field.amplitude /  np.sqrt(np.sum(field.intensity))

    def update_pixels(self, pixel_sizes: Tuple[Q_, Q_]):
        self.settings.child('needed_size', 'pixel_height').setValue(pixel_sizes[0].m_as('um'))
        self.settings.child('needed_size', 'pixel_width').setValue(pixel_sizes[1].m_as('um'))
        self.load_field()

    def get_mask_as_slices(self) -> Union[None, tuple[slice, slice]]:

        slices = eval(self.settings['utils', 'masking', 'slices'])
        if hasattr(slices, '__iter__'):
            for _slice in slices:
                if not isinstance(_slice, slice):
                    return None
        return slices

    def get_mask_type(self) -> MaskType:
        return MaskType[self.settings['utils', 'masking', 'mask_type']]

    def update_mask_slices(self):
        if self.mask is not None:
            self.settings.child('utils', 'masking', 'slices').setValue(str(self.mask.to_info().to_slices()))

    def value_changed(self, param: Parameter):
        if param.name() == 'loader':
            self.loader = param.value()

        elif param.name() in ('flipud', 'fliplr', 'do_scaling', 'scaling', 'aspect_ratio', 'apply_mask',
                              'apply_smoothing', 'sigma_y', 'sigma_x', 'slices', 'boundary', 'apply_boundary',
                              'sharpness', 'normalisation'):
            self.field = self._ini_field.deepcopy()
            self.update_final_size()
            self.update_viewers()

        elif param.name() == 'show_field':
            self.field_widget.setVisible(param.value())

        elif param.name() == 'reload':
            if param.value():
                self.load_field()
                param.setValue(False)

        elif param.name() == 'show_needed_area':
            self.show_roi_target(param.value())

        elif param.name() == 'show_mask':
            if self.settings['utils', 'masking', 'show_on'] == 'Amplitude':
                viewer = self.amp_viewer
            else:
                viewer = self.phase_viewer
            if param.value():
                viewer.roi_manager.add_roi_programmatically('RectROI')
                self.mask = viewer.roi_manager.get_roi_from_index(0)
                self.mask.sigRegionChangeFinished.connect(self.update_mask_slices)
                self.update_mask_slices()
            else:
                viewer.roi_manager.remove_roi_programmatically(0)
                self.mask.sigRegionChangeFinished.disconnect()
                self.mask = None

        elif param.name() == 'save':
            if param.value():
                self.save_field()
                param.setValue(False)

    def save_field(self, fname: Path = None, where: str = '/RawData', group_name: str = 'Field', title: str = ''):
        """ Save the field and the metadata used to produce it into a hdf5 file

        Parameters
        ----------
        fname : Path
            If specified, add the field in the existing (or new) file. Otherwise open a File dialog to enter a file name
        where: str
            the node where the data will be saved
        """
        if fname is None:
            fname = select_file(start_path=config('data', 'data_saving','h5file', 'save_path'),
                                save=True, ext='h5field',
                                force_save_extension=True)  # see daq_utils
        if fname != '':
            new_file = not fname.exists()

            dwa = DataCalculated('Field',
                                 data=[
                                     self.field.amplitude,
                                     self.field.phase
                                 ],
                                 labels=['Amplitude', 'Phase'],
                                 axes = self.field.get_axes())

            settings_all = [parameter_to_xml_string(self.settings),
                            parameter_to_xml_string(self._field_loader.settings)]
            settings_str = b'<All_settings title="All Settings" type="group">'
            for set in settings_all:
                if len(settings_str + set) < 60000:
                    # size limit for any object header (including all the other attributes) is 64kb
                    settings_str += set
                else:
                    break
            settings_str += b'</All_settings>'

            with DataSaverLoader(fname, new_file=new_file) as saver:
                group = saver.add_data_group(where, DataDim.Data2D, title=title, settings_as_xml=settings_str,
                                             group_name=group_name)
                saver.add_data(group, dwa)

    def update_apply_mask(self, size: tuple[int, int],
                          center: tuple[int, int] = None,
                          apply = False):
        """ Update the slices setting according to the size and center parameter
        and apply the mask eventually"""
        shape = (self.settings['needed_size', 'height'],
                 self.settings['needed_size', 'width'])
        if center is None:
            center = tuple(np.array(shape) // 2)

        slices = (slice(max(0, center[0] - size[0] // 2), min(shape[0], center[0] + size[0] // 2)),
                  slice(max(0, center[1] - size[1] // 2), min(shape[1], center[1] + size[1] // 2)))
        self.settings.child('utils', 'masking', 'slices').setValue(str(slices))
        self.settings.child('utils', 'masking', 'apply_mask').setValue(apply)

    def updated_slm(self, slm_default_name: str):
        """ When a SLM has been changed in the config, one should update the needed size of the field"""
        needed_size = get_effective_needed_field_size()
        pixel_size = get_effective_slm_pixel_size()
        self.settings.child('needed_size', 'height').setValue(needed_size[0])
        self.settings.child('needed_size', 'width').setValue(needed_size[1])
        self.settings.child('needed_size', 'pixel_height').setValue(pixel_size)
        self.settings.child('needed_size', 'pixel_width').setValue(pixel_size)


    def show_roi_target(self, show=True):
        self.amp_viewer.roi_target.setVisible(show)
        self.slm_size_roi_amp.setVisible(show)

        self.phase_viewer.roi_target.setVisible(show)
        self.slm_size_roi_phase.setVisible(show)

    def update_viewers(self):
        needed_shape = (self.settings['needed_size', 'height'],
                        self.settings['needed_size', 'width'],
                        )
        if self.field is not None:
            self.amp_viewer.show_data(self.field.amplitude_as_dwa())
            self.phase_viewer.show_data(self.field.phase_as_dwa())

            pixels_magnitude = np.array([pixel.to_base_units().magnitude for pixel in self.field.pixels_sizes])
            self.amp_viewer.move_roi_target(
                (0, 0),
                (np.array(needed_shape) * pixels_magnitude)[::-1])
            self.phase_viewer.move_roi_target(
                (0, 0),
                (np.array(needed_shape) * pixels_magnitude)[::-1])

            pos, size = get_effective_area_pos_size_in_pxls()
            self.amp_viewer.view.move_scale_roi(self.slm_size_roi_amp,
                                                pos=(pos * pixels_magnitude)[::-1],
                                                size=(size * pixels_magnitude)[::-1])
            self.phase_viewer.view.move_scale_roi(self.slm_size_roi_phase,
                                                  pos=(pos * pixels_magnitude)[::-1],
                                                  size=(size * pixels_magnitude)[::-1])

    def set_loader_in_settings(self, loader_name: str):
        if loader_name in self.settings.child('loader').opts['limits']:
            self.settings.child('loader').setValue(loader_name)

    def threshold_phase(self, field: Field, threshold=1e-9):
        """ Apply a threshold around 0 and pi to avoid numerical errors"""

        field.phase[2*np.pi - np.abs(field.phase) < threshold] = 2*np.pi
        field.phase[np.abs(field.phase) < threshold] = 0

    def load_field(self, *args, **kwargs):
        notify = kwargs.pop('notify', False)
        self._ini_field = self._field_loader.load_field(*args, notify=notify, **kwargs)
        self.apply_modifications(self._ini_field)

    def apply_modifications(self, field: Field):
        if field is not None:
            self.threshold_phase(field)
            self.field = field.deepcopy()
            self.update_ini_size()
            self.update_final_size()
            self.update_viewers()

            self.field_signal.emit(self.field)

    def update_field(self, field: Field):
        self._ini_field = field
        self.apply_modifications(field)

    def update_ini_size(self):
        self.settings.child('ini_size', 'height').setValue(self._ini_field.shape[0])
        self.settings.child('ini_size', 'width').setValue(self._ini_field.shape[1])

    def update_final_size(self):
        pixel_ratio = self.settings['needed_size', 'pixel_width'] / self.settings['needed_size', 'pixel_height']
        needed_shape = (self.settings['needed_size', 'height'],
                         self.settings['needed_size', 'width'])
        if self.settings['utils', 'flipud']:
            self.field.field = np.flipud(self.field.field)
        if self.settings['utils', 'fliplr']:
            self.field.field = np.fliplr(self.field.field)

        _field_temp = self.field.deepcopy()
        if self._field_loader.with_physical_pixels_size:
            self.field.amplitude = _field_temp.amplitude
            self.field.phase = _field_temp.phase
        else:
            self.field.amplitude = rescale(_field_temp.amplitude, (pixel_ratio, 1))
            self.field.phase = rescale(_field_temp.phase, (pixel_ratio, 1))

        self.field.calibrate_axes((Q_(self.settings['needed_size', 'pixel_height'], 'um'),
                                   Q_(self.settings['needed_size', 'pixel_width'], 'um')))

        if self.settings['utils', 'sizing', 'do_scaling']:
            if self.settings['utils', 'sizing', 'aspect_ratio']:
                ratio = np.min(np.array(needed_shape) / np.array(self.field.shape))
            else:
                ratio = np.array(needed_shape) / np.array(self.field.shape)
            _field_temp = self.field.deepcopy()

            self.field.amplitude = self.rescale_normalize(_field_temp.amplitude,
                                                          ratio * self.settings['utils', 'sizing', 'scaling'])
            self.field.phase = self.rescale_normalize(_field_temp.phase,
                                                      ratio * self.settings['utils', 'sizing', 'scaling'])

        self.settings.child('utils', 'sizing', 'height').setValue(self.field.shape[0])
        self.settings.child('utils', 'sizing', 'width').setValue(self.field.shape[1])

        self.field = self.crop(self.field, needed_shape)

        npad = self.get_npad_between(needed_shape, self.field.shape)
        if np.any(np.array(npad)):
            self.field = self.field.pad(npad)

        self.normalise(self.field, NormaliseTo[self.settings['utils', 'normalisation']])

        if self.settings['utils', 'masking', 'apply_mask']:

            mask = self.get_mask_array()
            self.field.amplitude = self.field.amplitude * mask
            self.field.phase = self.field.phase * mask

        if self.settings['utils', 'smoothing', 'apply_smoothing']:
            self.field.amplitude = gaussian_filter(self.field.amplitude, sigma=(
                self.settings['utils', 'smoothing', 'sigma_y'],
                self.settings['utils', 'smoothing', 'sigma_x']
            ))
            self.field.phase = gaussian_filter(self.field.phase, sigma=(
                self.settings['utils', 'smoothing', 'sigma_y'],
                self.settings['utils', 'smoothing', 'sigma_x']
            ))

    def get_mask_array(self, inner_value=1, outer_value=0) -> np.ndarray:
        """ Return a numpy array to be used to mask fields
        """
        shape = (self.settings['needed_size', 'height'],
                 self.settings['needed_size', 'width'])

        mask = outer_value * np.ones(shape)
        slices = self.get_mask_as_slices()
        y0, x0 = tuple([(_slice.stop + _slice.start) / 2 for _slice in slices])
        ry, rx = tuple([(_slice.stop - _slice.start) / 2 for _slice in slices])

        x = np.arange(0, shape[1], 1)
        y = np.arange(0, shape[0], 1)

        if self.settings['utils', 'masking', 'boundary', 'apply_boundary']:
            mask = gauss2D(x, x0, rx,
                           y, y0, ry,
                           self.settings['utils', 'masking', 'boundary', 'sharpness'])

        else:
            if self.get_mask_type() == MaskType.SQUARE:
                mask[tuple(slices)] = inner_value
            else:
                xx, yy = np.meshgrid(x, y)
                mask[
                    (xx - x0) ** 2 / rx **2 + (yy - y0) ** 2 / ry **2 <= 1] = inner_value
        return mask

    @staticmethod
    def rescale_normalize(array_in: np.ndarray, ratio) -> np.ndarray:
        """ Rescale and renormalize the output array to have the same intensity dynamic as the input array"""
        array_out = rescale(array_in, ratio)
        array_normalized = normalize(array_out) * (np.max(array_in) - np.min(array_in)) + np.min(array_in)
        if np.any(np.isnan(normalize(array_normalized))):  # generate nan is the array is constant
            return array_out
        else:
            return array_normalized

    @staticmethod
    def crop(field: Field, size: tuple[int, int], center: tuple[int, int] = None):
        shape = np.array(field.shape)
        if center is None:
            center = tuple(shape // 2)

        slices = (slice(max(0, center[0] - size[0] // 2), min(shape[0], center[0] + size[0] // 2)),
                  slice(max(0, center[1] - size[1] // 2), min(shape[1], center[1] + size[1] // 2)))
        return field.isig[tuple(slices)]

    @staticmethod
    def get_npad_between(first_shape, second_shape):
        """ Get the padding necessary to match object shape and image shape

        If positive, the image shape is bigger than the object
        If negative, the object shape is bigger than the image
        """
        npad_before = ((np.array(first_shape) -
                        np.array(second_shape)) // 2).astype(int)
        npad_after = (np.array(first_shape) -
                        np.array(second_shape)) - npad_before
        return (npad_before[0], npad_after[0]), (npad_before[1], npad_after[1])

    @property
    def loader(self):
        return self._field_loader

    @loader.setter
    def loader(self, loader_name: str):
        try:
            self._field_loader: FieldLoader =\
                field_loader_factory.get_loader(loader_name)(
                    parent=self,
                    **self.loader_kwargs
                )

            while True:
                child = self._loader_settings_widget.layout().takeAt(0)
                if not child:
                    break
                child.widget().deleteLater()
                QtWidgets.QApplication.processEvents()

            self._loader_settings_widget.layout().addWidget(self._field_loader.settings_tree)
            self._field_loader.register_listener(self)

        except ValueError as e:
            pass

    def setup_docks(self):
        self.docks['target'] = Dock('Target')
        self._main_widget = QtWidgets.QWidget()
        self._main_widget.setLayout(QtWidgets.QHBoxLayout())

        self.field_widget = QtWidgets.QWidget()
        self.field_widget.setLayout(QtWidgets.QHBoxLayout())
        field_widget_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        self.field_widget.layout().addWidget(field_widget_splitter)

        amp_widget = QtWidgets.QWidget()
        self.amp_viewer = Viewer2D(amp_widget)
        self.amp_viewer.view.get_action('legend').trigger()
        self.slm_size_roi_amp = pgROI(pos=(0, 0), size=(20, 20), movable=False, rotatable=False, resizable=False,
                                      pen=(0, 255, 0))
        self.amp_viewer.view.plotitem.addItem(self.slm_size_roi_amp)
        self.slm_size_roi_amp.setVisible(False)

        phase_widget = QtWidgets.QWidget()
        self.phase_viewer = Viewer2D(phase_widget)
        self.phase_viewer.view.get_action('legend').trigger()
        self.slm_size_roi_phase = pgROI(pos=(0, 0), size=(20, 20), movable=False, rotatable=False, resizable=False,
                                        pen=(0, 255, 0))
        self.phase_viewer.view.plotitem.addItem(self.slm_size_roi_phase)
        self.slm_size_roi_phase.setVisible(False)

        self.show_roi_target(self.settings['needed_size', 'show_needed_area'])

        field_widget_splitter.addWidget(amp_widget)
        field_widget_splitter.addWidget(phase_widget)

        self.dockarea.addDock(self.docks['target'])

        self.settings_widget = QtWidgets.QWidget()
        self.settings_widget.setLayout(QtWidgets.QVBoxLayout())
        self.settings_widget.layout().setContentsMargins(0, 0, 0, 0)
        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        self.settings_widget.layout().addWidget(splitter)
        splitter.addWidget(self.settings_tree)

        self._loader_settings_widget = QtWidgets.QWidget()
        self._loader_settings_widget.setLayout(QtWidgets.QVBoxLayout())
        self._loader_settings_widget.layout().setContentsMargins(0, 0, 0, 0)
        splitter.addWidget(self._loader_settings_widget)

        self._main_widget.layout().addWidget(self.settings_widget)
        self.settings_tree.setMinimumWidth(300)
        self.settings_tree.setMinimumHeight(150)
        self._main_widget.layout().addWidget(self.field_widget)
        self.docks['target'].addWidget(self._main_widget)

    def setup_actions(self):
        ...

    def connect_things(self):
        ...


def main():
    from pathlib import Path
    from pymodaq_gui.qt_utils import mkQApp

    app = mkQApp('Optical Shaping')

    win = QtWidgets.QMainWindow()
    area = DockArea()
    win.setCentralWidget(area)
    win.resize(1000, 500)
    win.setWindowTitle('PyMoDAQ Dashboard')
    win.show()

    optical_app = FieldLoaderApp(area)

    app.exec()


if __name__ == '__main__':
    main()
