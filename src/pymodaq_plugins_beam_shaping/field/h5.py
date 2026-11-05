""" Saving and loading a Field in a h5field file (format of the field loaders and the Field Tool)"""
from pathlib import Path
from typing import Iterable, Union

from pymodaq_data import DataCalculated, DataDim, Q_
from pymodaq_data.h5modules.data_saving import DataSaverLoader, DataLoader
from pymodaq_gui.parameter import Parameter
from pymodaq_gui.parameter.ioxml import parameter_to_xml_string

from pymodaq_plugins_beam_shaping.utilities.h5saving import add_plugin_version
from pymodaq_plugins_beam_shaping.field.field import Field

MAX_SETTINGS_SIZE = 60000  # size limit for any object header (including all the other attributes) is 64kb


def settings_to_xml(settings: Iterable[Parameter]) -> bytes:
    """ The settings as one xml group, the last ones are dropped if they do not fit in a h5 attribute"""
    settings_str = b'<All_settings title="All Settings" type="group">'
    for setting in settings:
        xml = parameter_to_xml_string(setting)
        if len(settings_str + xml) < MAX_SETTINGS_SIZE:
            settings_str += xml
        else:
            break
    settings_str += b'</All_settings>'
    return settings_str


def save_field_to_h5(field: Field, fname: Union[str, Path], settings: Iterable[Parameter] = (),
                     where: str = '/RawData', group_name: str = 'Field', title: str = ''):
    """ Save the field (amplitude and phase) and the settings used to produce it into a hdf5 file

    The field is added to the file if it exists."""
    fname = Path(fname)
    new_file = not fname.exists()
    dwa = DataCalculated('Field', data=[field.amplitude, field.phase], labels=['Amplitude', 'Phase'],
                         axes=field.get_axes())
    with DataSaverLoader(fname, new_file=new_file) as saver:
        group = saver.add_data_group(where, DataDim.Data2D, title=title, settings_as_xml=settings_to_xml(settings),
                                     group_name=group_name)
        saver.add_data(group, dwa)
        add_plugin_version(saver)


def load_field_from_h5(fname: Union[str, Path], path: str = '/RawData/Field/Data00', name: str = 'Image') -> Field:
    """ Load a Field saved by save_field_to_h5"""
    with DataLoader(fname) as loader:
        dwa = loader.load_data(path, load_all=True)
        xaxis = dwa.get_axis_from_index(1)[0]
        yaxis = dwa.get_axis_from_index(0)[0]
        return Field(name, amplitude=dwa[0], phase=dwa[1],
                     pixel_sizes=(Q_(yaxis.scaling, yaxis.units), Q_(xaxis.scaling, xaxis.units)))
