import numpy as np
from pathlib import Path


from pymodaq_utils.logger import set_logger, get_module_name
from pymodaq_gui.parameter import Parameter

from pymodaq_plugins_beam_shaping.field.utils import (FieldLoader, LoadTypeEnum,
                                                      Field)
from pymodaq_plugins_beam_shaping.field.factory import LoaderFactory
from pymodaq_plugins_beam_shaping.field.h5 import load_field_from_h5

resources_path = Path(__file__).parent.parent.parent.joinpath('resources')
#ferris_wheel = resources_path.joinpath('ferris_wheel_3_11_pluto_setup_4f.h5')
ferris_wheel = resources_path.joinpath('ferris_wheel_3_11_pluto_setup_2f.h5')
cat = resources_path.joinpath('cat_field.h5')

logger = set_logger(get_module_name(__file__))


@LoaderFactory.register_loader()
class SavedFieldLoader(FieldLoader):

    LOADER_NAME = 'SavedField'
    with_physical_pixels_size = True

    params = FieldLoader.params + \
            [{'title': 'File path:', 'name': 'file', 'type': 'browsepath',
             'value': str(cat), 'filetype': True, 'filter': "Fields (*.h5field)"}
         ]


    def load(self, *args, **kwargs) -> Field:
        """ Mandatory reimplemented method. Used to load a target to populate the field attribute"""

        self.field = load_field_from_h5(self.settings['file'])
        return self.field


