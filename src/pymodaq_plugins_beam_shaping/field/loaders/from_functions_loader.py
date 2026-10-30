from numbers import Number
from typing import Tuple, Union, TYPE_CHECKING, Callable, Iterable

import numpy as np


from pymodaq_plugins_beam_shaping.field import Field, LoaderFactory, FieldLoader
from pymodaq_gui.parameter import Parameter
from pymodaq_utils import math_utils as mutils
from pymodaq_data import Q_, Unit

from scipy.special import genlaguerre, hermite

from pymodaq_plugins_beam_shaping import config as plugin_config



class BaseFieldLoader(FieldLoader):
    with_physical_pixels_size = True

    def compute_grid(self) -> tuple[np.ndarray, np.ndarray]:
        """ Compute the centered positions on the grid in microns given the value of the pixel width"""
        x = np.arange(0, self.n_pixel_width, 1) * self.pixel_width   #um
        x = x-np.mean(x)
        y = np.arange(0, self.n_pixel_height, 1) * self.pixel_height  #um
        y = y - np.mean(y)
        xx, yy = np.meshgrid(x, y)
        return xx, yy

    @staticmethod
    def compute_polygon(xx, yy, n_coordinates):
        """ Compute the location of the pixels within a closed polygon of n points

        The method use the fact that all points situated at the left of any polygone edge are within the polygon. The
        coordinates should be taken counter-clockwise. See https://stackoverflow.com/questions/2752725/
        """
        d = np.full(xx.shape, True)
        for ind in range(-1, len(n_coordinates) - 1):
            d = d & (((n_coordinates[ind+1][0] - n_coordinates[ind][0]) * (yy - n_coordinates[ind][1]) -
                     (xx - n_coordinates[ind][0]) * (n_coordinates[ind+1][1] - n_coordinates[ind][1])) >= 0)
        return np.where(d, 1, 0)

    def compute_circle(self, xx: np.ndarray, yy: np.ndarray,
                       x_center: float, y_center: float,
                       radius: float = 100.):
        """ Compute the location of the pixels within a circle given its center and its radius """
        xx_shifted = xx - x_center
        yy_shifted = yy - y_center

        # Calculate the radial distance from the beam center
        radial_distance = np.sqrt(xx_shifted ** 2 + yy_shifted ** 2)
        amplitude = np.where(radial_distance < radius, 1, 0)
        return amplitude

    @staticmethod
    def gaussian_fwhm(x: np.ndarray, x0: float, fwhm: float) -> np.ndarray:
        """ Get a Gaussian amplitude distribution centered in x0 with a full width at half maximum in intensity of fwhm

        Parameters
        ----------
        x: np.ndarray
            distribution on which the gaussian is evaluated (in microns)
        x0: float
            center of the gaussian distribution (in micron)
        fwhm: float
            full width at half maximum in intensity expressed (in micron)

        Returns
        -------
        np.ndarray
        """
        return np.exp(- 2 * np.log(2) * ((x - x0) / fwhm) ** 2)

    def settings_changed(self, param: Parameter):
        field = self.compute_field()
        self.notify_listeners(field)

    def compute_field(self) -> Field:
        raise NotImplementedError

    def load(self, *args, **kwargs) -> Field:
        """ Mandatory reimplemented method. Used to load a target to populate the field attribute"""
        self.field = self.compute_field()
        return self.field


@LoaderFactory.register_loader()
class GaussianIntensity(BaseFieldLoader):

    LOADER_NAME = 'GaussianIntensity'

    params = BaseFieldLoader.params + \
        [
            {'title': 'Beam size x (um):', 'name': 'beam_size_x', 'type': 'float',
             'value': plugin_config('input', 'gaussian', 'fwhm_x'), 'tip' : 'FWHM in intensity'},
            {'title': 'Beam size y (um):', 'name': 'beam_size_y', 'type': 'float',
             'value': plugin_config('input', 'gaussian', 'fwhm_y'), 'tip' : 'FWHM in intensity'},
         ]

    def compute_field(self) -> Field:
        xx, yy = self.compute_grid()
        self.progressbar = 30
        amplitude = (self.gaussian_fwhm(xx, 0, self.settings['beam_size_x']) *
                     self.gaussian_fwhm(yy, 0, self.settings['beam_size_y']))
        self.progressbar = 60
        field = Field('GaussianIntensity',
                      amplitude=amplitude,
                      pixel_sizes=Q_(np.array((self.pixel_height, self.pixel_width)),'um'))
        return field


@LoaderFactory.register_loader()
class DoubleGaussian(BaseFieldLoader):
    LOADER_NAME = 'DoubleGaussian'

    params = BaseFieldLoader.params + \
             [
                 {'title': 'sigma_x (um):', 'name': 'sigma_x', 'type': 'float',
                  'value': 300., },
                 {'title': 'sigma_y (um):', 'name': 'sigma_y', 'type': 'float',
                  'value': 300., },
                 {'title': 'Position x from center (um):', 'name': 'x_from_center', 'type': 'float',
                  'value': 500., },
                 {'title': 'Add asymetry (um) :', 'name': 'asymetry', 'type': 'float',
                  'value': 0., },
                 {'title': 'Rotation around center (degree):', 'name': 'rotation_around_center', 'type': 'float',
                  'value': 0., },
             ]

    def compute_field(self) -> Field:

        xx, yy = self.compute_grid()

        self.progressbar = 15

        theta = np.radians(Q_(self.settings['rotation_around_center'], 'degree'))
        rotation_matrix = np.array([[np.cos(theta), -np.sin(theta)], [np.sin(theta), np.cos(theta)]])

        self.progressbar = 30

        # Gaussian 1
        beam_center_unrotated = [self.settings['x_from_center'], 0.]

        self.progressbar = 45

        x1_rot, y1_rot = rotation_matrix @ beam_center_unrotated
        amplitude = (self.gaussian_fwhm(xx, x1_rot, self.settings['sigma_x']) *
                     self.gaussian_fwhm(yy, y1_rot, self.settings['sigma_y']))
        self.progressbar = 60

        # Gaussian 2
        beam_center_unrotated_magn = [
            beam_center_unrotated[0] + self.settings['asymetry'],
            beam_center_unrotated[1]]

        self.progressbar = 80
        x2_rot, y2_rot = -rotation_matrix @ beam_center_unrotated_magn
        amplitude += (self.gaussian_fwhm(xx, x2_rot, self.settings['sigma_x']) *
                     self.gaussian_fwhm(yy, y2_rot, self.settings['sigma_y']))

        field = Field('Double_gaussian', amplitude=amplitude,
                      pixel_sizes=Q_(np.array((self.pixel_height,
                                               self.pixel_width)),
                                     'um'))
        return field


@LoaderFactory.register_loader()
class LaguerreGaussian(BaseFieldLoader):
    """ Calculation based on mathematical expression from 10.61835/gd8 using scipy special Laguerre function"""

    LOADER_NAME = 'LaguerreGaussian'

    params = BaseFieldLoader.params + \
        [
            {'title': 'Beam waist (um):', 'name': 'waist', 'type': 'float',
             'value': plugin_config('input', 'laguerre', 'waist'), },
            {'title': 'Radial order :', 'name': 'radial_index', 'type': 'int',
             'value': plugin_config('input', 'laguerre', 'radial_index'), },
            {'title': 'Azimutal order:', 'name': 'azimutal_index', 'type': 'int',
             'value': plugin_config('input', 'laguerre', 'azimutal_index'), },
         ]

    def compute_polynomial(self, m: int , l: int) -> Callable[[np.ndarray], np.ndarray]:
        return genlaguerre(m, abs(l))

    def compute_laguerre(self, m: int, l: int, xx: np.ndarray, yy: np.ndarray, waist_fwhm: float):
        poly = self.compute_polynomial(m, l)
        radius = np.sqrt(xx ** 2 + yy ** 2)
        phi = np.arctan2(yy, xx)
        waist = waist_fwhm / np.sqrt(2 * np.log(2))
        return (poly(2 * radius ** 2 / waist ** 2) *
                self.gaussian_fwhm(radius, 0, waist_fwhm) *
                np.exp(1j * l * phi) *
                (np.sqrt(2) * radius / waist) ** abs(l)
                )

    def compute_field(self) -> Field:
        xx, yy = self.compute_grid()

        self.progressbar = 20

        lg_complex = self.compute_laguerre(self.settings['radial_index'],
                                           self.settings['azimutal_index'],
                                           xx, yy,
                                           self.settings['waist'])
        self.progressbar = 80

        field = Field('LaguerreGaussian',
                      amplitude=np.abs(lg_complex),
                      phase=np.angle(lg_complex),
                      pixel_sizes=Q_(np.array((self.pixel_height,
                                               self.pixel_width)),
                                     'um'))
        return field


@LoaderFactory.register_loader()
class FerrisWheel(LaguerreGaussian):

    LOADER_NAME = 'FerrisWheel'

    params = BaseFieldLoader.params + \
        [
            {'title': 'Beam waist (um):', 'name': 'waist', 'type': 'float',
             'value': plugin_config('input', 'ferris', 'waist'), },
            {'title': 'Azimutal order 1:', 'name': 'azimutal_index_1', 'type': 'int',
             'value': plugin_config('input', 'ferris', 'azimutal_index_1'), },
            {'title': 'Azimutal order 2:', 'name': 'azimutal_index_2', 'type': 'int',
             'value': plugin_config('input', 'ferris', 'azimutal_index_2'), },
            {'title': 'Alpha:', 'name': 'alpha', 'type': 'float',
             'value': plugin_config('input', 'ferris', 'alpha'), },
         ]

    def compute_field(self) -> Field:
        xx, yy = self.compute_grid()
        self.progressbar = 10

        field1 = super().compute_laguerre(0, self.settings['azimutal_index_1'], xx, yy,
                                          self.settings['waist'])
        self.progressbar = 50

        field2 = super().compute_laguerre(0, self.settings['azimutal_index_2'], xx, yy,
                                          self.settings['waist'])
        self.progressbar = 80

        wheel = field1 + self.settings['alpha'] * field2

        amplitude = np.abs(wheel)
        phase = np.angle(wheel)

        self.progressbar = 100

        field = Field('FerrisWheel',
                      amplitude=amplitude,
                      phase = phase,
                      pixel_sizes=Q_(np.array((self.pixel_height,
                                               self.pixel_width)),
                                     'um'))
        return field


@LoaderFactory.register_loader()
class TwoCirclesOnLine(BaseFieldLoader):

    LOADER_NAME = 'TwoCirclesOnALine'

    params = BaseFieldLoader.params + \
             [
                 {'title': 'Radius (um):', 'name': 'radius_circle', 'type': 'float',
                  'value': 300., },
                 {'title': 'Position x from center (um):', 'name': 'x_from_center', 'type': 'float',
                  'value': 500., },
                 {'title': 'Add asymetry (um) :', 'name': 'asymetry', 'type': 'float',
                  'value': 0.,},
                 {'title': 'Rotation around center (degree):', 'name': 'rotation_around_center', 'type': 'float',
                  'value': 0., },
                 {'title': 'linewidth (um):', 'name': 'linewidth', 'type': 'float',
                  'value': 100., },
             ]

    def compute_field(self) -> Field:
        xx, yy = self.compute_grid()

        theta = np.radians(Q_(self.settings['rotation_around_center'], 'degree'))
        rotation_matrix = np.array([[np.cos(theta), -np.sin(theta)], [np.sin(theta), np.cos(theta)]])

        #Circle 1
        beam_center_unrotated = np.array([self.settings['x_from_center'], 0.])

        x1_rot, y1_rot = rotation_matrix@beam_center_unrotated
        amplitude = self.compute_circle(xx, yy, x1_rot, y1_rot, self.settings['radius_circle'])

        #Circle 2
        beam_center_unrotated2 = np.array([beam_center_unrotated[0] + self.settings['asymetry'],
                                          beam_center_unrotated[1]])
        x2_rot, y2_rot = -rotation_matrix@beam_center_unrotated2
        amplitude += self.compute_circle(xx, yy, x2_rot, y2_rot, self.settings['radius_circle'])

        rectangle_coordinates = [beam_center_unrotated + np.array([0, -self.settings['linewidth'] / 2]),
                                 beam_center_unrotated + np.array([0, +self.settings['linewidth'] / 2]),
                                 beam_center_unrotated + np.array([self.settings['asymetry'], 0]) + np.array([0, -self.settings['linewidth'] / 2]),
                                 beam_center_unrotated + np.array([self.settings['asymetry'], 0]) + np.array([0, self.settings['linewidth'] / 2]),
                                 ]
        rotated_coordinates = []
        for ind, coord in enumerate(rectangle_coordinates):
            if ind < 2:
                rot = rotation_matrix
            else:
                rot = -rotation_matrix
            rotated_coordinates.append(rot@coord)

        amplitude += self.compute_polygon(xx, yy, rotated_coordinates)

        amplitude[amplitude > 0] = 1

        field = Field('2circles_on_line', amplitude=amplitude,
                      pixel_sizes=Q_(np.array((self.pixel_height,
                                               self.pixel_width)),
                                     'um'))
        return field


@LoaderFactory.register_loader()
class RectangleIntensity(BaseFieldLoader):
    LOADER_NAME = 'RectangleIntensity'

    params = BaseFieldLoader.params + [
        {'title': 'Width (um):', 'name': 'length', 'type': 'float', 'value': 1000., 'suffix': 'um'},
        {'title': 'Height (um):', 'name': 'height', 'type': 'float', 'value': 1000., 'suffix': 'um'},
        {'title': 'Edge Thickness (um):', 'name': 'thickness', 'type': 'float', 'value': 200., 'suffix': 'um'},
    ]

    def compute_field(self) -> Field:

        xx, yy = self.compute_grid()
        self.progressbar = 30

        # Rectangle parameters

        inner_coordinates = [[self.settings['length'] /2 - self.settings['thickness'] /2 , - self.settings['height'] /2  + self.settings['thickness'] /2],
                             [self.settings['length'] /2 - self.settings['thickness'] /2 , + self.settings['height'] /2  - self.settings['thickness'] /2],
                             [-self.settings['length'] /2 + self.settings['thickness'] /2 , + self.settings['height'] /2 - self.settings['thickness'] /2],
                             [-self.settings['length'] /2 + self.settings['thickness'] /2 , - self.settings['height'] /2  + self.settings['thickness'] /2],]
        outer_coordinates = [[self.settings['length'] /2 , - self.settings['height'] /2 ],
                             [self.settings['length'] /2 , + self.settings['height'] /2 ],
                             [-self.settings['length'] /2 , + self.settings['height'] /2 ],
                             [-self.settings['length'] /2 , - self.settings['height'] /2 ],]

        amplitude = self.compute_polygon(xx, yy, outer_coordinates)
        amplitude -= self.compute_polygon(xx, yy, inner_coordinates)
        self.progressbar = 90

        field = Field(
            'RectangleIntensity',
            amplitude=amplitude,
            pixel_sizes=Q_(np.array((self.pixel_height, self.pixel_width)), 'um')
        )
        return field



@LoaderFactory.register_loader()
class RectangleIntensity_test(BaseFieldLoader):
    LOADER_NAME = 'RectangleIntensity_test'

    params = BaseFieldLoader.params + [
        {'title': 'Width (um):', 'name': 'length', 'type': 'float', 'value': 1000., 'suffix': 'um'},
        {'title': 'Height (um):', 'name': 'height', 'type': 'float', 'value': 1000., 'suffix': 'um'},
        {'title': 'Edge Thickness (um):', 'name': 'thickness', 'type': 'float', 'value': 200., 'suffix': 'um'},
        {'title': 'Rotation (deg):', 'name': 'theta', 'type': 'float', 'value': 0.},
        {'title': 'With linear phase', 'name': 'with_linear_phase', 'type': 'bool', 'value': False},
        {'title': 'Phase slope X', 'name': 'phase_slope_x', 'type': 'float', 'value': 0.01},
        {'title': 'Phase slope Y', 'name': 'phase_slope_y', 'type': 'float', 'value': 0.0},
    ]

    def rotate_coords(self, coords, theta):
        theta = np.deg2rad(theta)

        R = np.array([
            [np.cos(theta), -np.sin(theta)],
            [np.sin(theta),  np.cos(theta)]
        ])

        coords = np.array(coords)
        return (R @ coords.T).T.tolist()

    def compute_field(self) -> Field:

        xx, yy = self.compute_grid()
        self.progressbar = 30

        L = self.settings['length']
        H = self.settings['height']
        t = self.settings['thickness']

        inner_coordinates = [
            [ L/2 - t/2, -H/2 + t/2],
            [ L/2 - t/2,  H/2 - t/2],
            [-L/2 + t/2,  H/2 - t/2],
            [-L/2 + t/2, -H/2 + t/2],
        ]

        outer_coordinates = [
            [ L/2, -H/2],
            [ L/2,  H/2],
            [-L/2,  H/2],
            [-L/2, -H/2],
        ]

        theta = self.settings['theta']
        inner_coordinates = self.rotate_coords(inner_coordinates, theta)
        outer_coordinates = self.rotate_coords(outer_coordinates, theta)

        amplitude = self.compute_polygon(xx, yy, outer_coordinates)
        amplitude -= self.compute_polygon(xx, yy, inner_coordinates)

        self.progressbar = 80

        phase = np.zeros_like(amplitude)

        if self.settings['with_linear_phase']:
            ax = self.settings['phase_slope_x']
            ay = self.settings['phase_slope_y']

            linear_phase = ax * xx + ay * yy

            # phase uniquement dans le rectangle
            phase = linear_phase * amplitude

        self.progressbar = 90

        field = Field(
            'RectangleIntensity',
            amplitude=amplitude,
            phase=phase,
            pixel_sizes=Q_(np.array((self.pixel_height, self.pixel_width)), 'um')
        )

        return field

@LoaderFactory.register_loader()
class HermiteGauss(BaseFieldLoader):
    LOADER_NAME = 'HermiteGaussLoader'

    params = BaseFieldLoader.params + [
        {'title': 'Waist (um):', 'name': 'waist', 'type': 'float', 'value': 50., 'suffix': 'um'},
        {'title': 'Order nx:', 'name': 'nx', 'type': 'int', 'value': 0},
        {'title': 'Order ny:', 'name': 'ny', 'type': 'int', 'value': 0},
    ]

    def hermite_gauss(self, X, Y, w0, nx, ny):
        """
        Hermite-Gauss mode HG(nx, ny) at z = 0
        """
        x = np.sqrt(2) * X / w0
        y = np.sqrt(2) * Y / w0

        Hx = hermite(nx)(x)
        Hy = hermite(ny)(y)

        field = (
                Hx * Hy
                * np.exp(-(X ** 2 + Y ** 2) / w0 ** 2)
        )

        amplitude = np.abs(field)
        phase = np.angle(field)

        return amplitude, phase

    def compute_field(self):
        # Axes of the target plane
        x = Q_(np.arange(-self.n_pixel_width / 2, self.n_pixel_width / 2) * self.pixel_width, 'um')
        y = Q_(np.arange(-self.n_pixel_height / 2, self.n_pixel_height / 2) * self.pixel_height, 'um')

        X, Y = np.meshgrid(x.magnitude, y.magnitude)

        self.progressbar = 30

        # Parameters
        w0 = Q_(self.settings['waist'], 'um').magnitude
        nx = self.settings['nx']
        ny = self.settings['ny']

        self.progressbar = 60

        amplitude, phase = self.hermite_gauss(X, Y, w0, nx, ny)

        self.progressbar = 90

        field = Field(
            'HermiteGauss',
            amplitude=amplitude,
            phase=phase,
            pixel_sizes=Q_(np.array((self.pixel_height, self.pixel_width)), 'um')
        )

        return field



@LoaderFactory.register_loader()
class DoubleLG(BaseFieldLoader):
    LOADER_NAME = 'DoubleLGLoader'

    params = BaseFieldLoader.params + [
        {'title': 'Waist 1 (um):', 'name': 'waist1', 'type': 'float', 'value': 50., 'suffix': 'um'},
        {'title': 'p1:', 'name': 'p1', 'type': 'int', 'value': 0},
        {'title': 'l1:', 'name': 'l1', 'type': 'int', 'value': 1},

        {'title': 'Waist 2 (um):', 'name': 'waist2', 'type': 'float', 'value': 50., 'suffix': 'um'},
        {'title': 'p2:', 'name': 'p2', 'type': 'int', 'value': 0},
        {'title': 'l2:', 'name': 'l2', 'type': 'int', 'value': -1},

        {'title': 'Beam separation d (um):', 'name': 'd', 'type': 'float', 'value': 100., 'suffix': 'um'},
    ]

    def laguerre_gauss(self, X, Y, w0, p, l):
        """
        LG mode at z = 0
        """
        r = np.sqrt(X**2 + Y**2)
        phi = np.arctan2(Y, X)

        rho = 2 * r**2 / w0**2
        Lpl = genlaguerre(p, np.abs(l))(rho)

        amplitude = (
            (np.sqrt(2) * r / w0)**np.abs(l)
            * Lpl
            * np.exp(-r**2 / w0**2)
        )

        phase = l * phi

        return amplitude, phase

    def compute_field(self):
        # Axes of the target plane
        x = Q_(np.arange(-self.n_pixel_width / 2, self.n_pixel_width / 2) * self.pixel_width, 'um')
        y = Q_(np.arange(-self.n_pixel_height / 2, self.n_pixel_height / 2) * self.pixel_height, 'um')

        X, Y = np.meshgrid(x.magnitude, y.magnitude)

        self.progressbar = 20

        # Parameters
        w1 = Q_(self.settings['waist1'], 'um').magnitude
        w2 = Q_(self.settings['waist2'], 'um').magnitude
        d  = Q_(self.settings['d'], 'um').magnitude

        p1 = self.settings['p1']
        l1 = self.settings['l1']
        p2 = self.settings['p2']
        l2 = self.settings['l2']

        # Shifted coordinates
        X1 = X - d / 2
        X2 = X + d / 2

        self.progressbar = 50

        # LG beams
        A1, P1 = self.laguerre_gauss(X1, Y, w1, p1, l1)
        A2, P2 = self.laguerre_gauss(X2, Y, w2, p2, l2)

        # Complex fields
        E1 = A1 * np.exp(1j * P1)
        E2 = A2 * np.exp(1j * P2)

        # Superposition
        E = E1 + E2

        self.progressbar = 80

        amplitude = np.abs(E)
        phase = np.angle(E)

        field = Field(
            'DoubleLG',
            amplitude=amplitude,
            phase=phase,
            pixel_sizes=Q_(np.array((self.pixel_height, self.pixel_width)), 'um')
        )

        self.progressbar = 100
        return field





@LoaderFactory.register_loader()
class VortexPhaseIntensity(BaseFieldLoader):

    LOADER_NAME = 'VortexPhaseIntensity'

    params = BaseFieldLoader.params + [
        {'title': 'Topological charge l:', 'name': 'l', 'type': 'int',
         'value': 1},
        {'title': 'Beam waist (um):', 'name': 'waist', 'type': 'float',
         'value': plugin_config('input', 'gaussian', 'fwhm_x'),
         'tip': 'FWHM in intensity'}
    ]

    def compute_field(self) -> Field:

        xx, yy = self.compute_grid()
        self.progressbar = 20

        l = self.settings['l']
        waist = self.settings['waist']

        r = np.sqrt(xx**2 + yy**2)
        theta = np.arctan2(yy, xx)

        self.progressbar = 40

        gaussian = np.exp(-2 * np.log(2) * (r / waist) ** 2)

        phase = l * theta
        phase_wrapped = np.mod(phase, 2*np.pi)

        phase_intensity = phase_wrapped / (2*np.pi)

        intensity = gaussian * phase_intensity

        self.progressbar = 80

        field = Field(
            'VortexPhaseIntensity',
            amplitude=intensity,
            pixel_sizes=Q_(np.array((self.pixel_height, self.pixel_width)), 'um')
        )

        return field