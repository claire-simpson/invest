"""Module for Regression Testing the InVEST Forest Carbon Edge model."""
import unittest
import tempfile
import shutil
import os

import numpy
import pandas
from osgeo import gdal, osr, ogr
from shapely.geometry import Polygon
import pygeoprocessing
import pickle

import pygeoprocessing

gdal.UseExceptions()
REGRESSION_DATA = os.path.join(
    os.path.dirname(__file__), '..', 'data', 'invest-test-data',
    'forest_carbon_edge_effect')


def make_simple_vector(path_to_shp):
    """
    Generate shapefile with one rectangular polygon

    Args:
        path_to_shp (str): path to target shapefile

    Returns:
        None
    """
    # (xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax), (xmin, ymin)
    shapely_geometry_list = [
        Polygon([(461251, 4923195), (461501, 4923195),
                 (461501, 4923445), (461251, 4923445),
                 (461251, 4923195)])
    ]

    srs = osr.SpatialReference()
    srs.ImportFromEPSG(26910)
    projection_wkt = srs.ExportToWkt()
    vector_format = "ESRI Shapefile"
    fields = {"id": ogr.OFTReal}
    attribute_list = [{"id": 0}]
    pygeoprocessing.shapely_geometry_to_vector(shapely_geometry_list,
                                               path_to_shp, projection_wkt,
                                               vector_format, fields,
                                               attribute_list)


def make_simple_raster(base_raster_path, array, nodata_val=-1):
    """Create a raster on designated path.

    Args:
        base_raster_path (str): the raster path for the new raster.
        array (array): numpy array to convert to tif.
        nodata_val (int or None): for defining a raster's nodata value.

    Returns:
        None

    """

    srs = osr.SpatialReference()
    srs.ImportFromEPSG(26910)  # UTM Zone 10N
    projection_wkt = srs.ExportToWkt()
    # origin hand-picked for this epsg:
    origin = (461261, 4923265)

    pixel_size = (1, -1)

    pygeoprocessing.numpy_array_to_raster(
        array, nodata_val, pixel_size, origin, projection_wkt,
        base_raster_path)


class ForestCarbonEdgeTests(unittest.TestCase):
    """Tests for the Forest Carbon Edge Model."""

    def setUp(self):
        """Overriding setUp function to create temp workspace directory."""
        # this lets us delete the workspace after its done no matter the
        # test result
        self.workspace_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Overriding tearDown function to remove temporary directory."""
        shutil.rmtree(self.workspace_dir)

    def test_carbon_full(self):
        """Forest Carbon Edge: regression testing all functionality."""
        from natcap.invest import forest_carbon_edge_effect

        args = {
            'aoi_vector_path': os.path.join(
                REGRESSION_DATA, 'input', 'small_aoi.shp'),
            'biomass_to_carbon_conversion_factor': '0.47',
            'biophysical_table_path': os.path.join(
                REGRESSION_DATA, 'input', 'forest_edge_carbon_lu_table.csv'),
            'compute_forest_edge_effects': True,
            'lulc_raster_path': os.path.join(
                REGRESSION_DATA, 'input', 'small_lulc.tif'),
            'n_nearest_model_points': 10,
            'pools_to_calculate': 'all',
            'tropical_forest_edge_carbon_model_vector_path': os.path.join(
                REGRESSION_DATA, 'input', 'core_data',
                'forest_carbon_edge_regression_model_parameters.shp'),
            'workspace_dir': self.workspace_dir,
            'n_workers': -1
        }
        forest_carbon_edge_effect.execute(args)
        ForestCarbonEdgeTests._test_same_files(
            os.path.join(REGRESSION_DATA, 'file_list.txt'),
            args['workspace_dir'])

        self._assert_vector_results_close(
            'id',
            ['c_sum', 'c_ha_mean'],
            os.path.join(
                args['workspace_dir'], 'aggregated_carbon_stocks.shp'),
            os.path.join(REGRESSION_DATA, 'agg_results_base.shp'))

        # Check raster output to make sure values are in Mg/ha.
        raster_path = os.path.join(args['workspace_dir'], 'carbon_map.tif')
        raster_info = pygeoprocessing.get_raster_info(raster_path)
        nodata = raster_info['nodata'][0]
        raster_sum = 0.0
        for _, block in pygeoprocessing.iterblocks((raster_path, 1)):
            raster_sum += numpy.sum(
                block[~pygeoprocessing.array_equals_nodata(
                        block, nodata)], dtype=numpy.float64)

        # expected_sum_per_pixel_values is in Mg, calculated from raster
        # generated by the model when each pixel value was in Mg/px.
        # Since pixel values are now Mg/ha, raster sum is (Mg•px)/ha.
        # To convert expected_sum_per_pixel_values from Mg, multiply by px/ha.
        expected_sum_per_pixel_values = 21414391.997192383
        pixel_area = abs(numpy.prod(raster_info['pixel_size']))
        pixels_per_hectare = 10000 / pixel_area
        expected_sum = expected_sum_per_pixel_values * pixels_per_hectare
        numpy.testing.assert_allclose(raster_sum, expected_sum)

    def test_carbon_dup_output(self):
        """Forest Carbon Edge: test for existing output overlap."""
        from natcap.invest import forest_carbon_edge_effect

        args = {
            'aoi_vector_path': os.path.join(
                REGRESSION_DATA, 'input', 'small_aoi.shp'),
            'biomass_to_carbon_conversion_factor': '0.47',
            'biophysical_table_path': os.path.join(
                REGRESSION_DATA, 'input', 'forest_edge_carbon_lu_table.csv'),
            'compute_forest_edge_effects': True,
            'lulc_raster_path': os.path.join(
                REGRESSION_DATA, 'input', 'small_lulc.tif'),
            'n_nearest_model_points': 1,
            'pools_to_calculate': 'above_ground',
            'results_suffix': 'small',
            'tropical_forest_edge_carbon_model_vector_path': os.path.join(
                REGRESSION_DATA, 'input', 'core_data',
                'forest_carbon_edge_regression_model_parameters.shp'),
            'workspace_dir': self.workspace_dir,
            'n_workers': -1
        }

        # explicitly testing that invoking twice doesn't cause the model to
        # crash because of existing outputs
        forest_carbon_edge_effect.execute(args)
        forest_carbon_edge_effect.execute(args)
        self.assertTrue(True)  # explicit pass of the model

    def test_carbon_no_forest_edge(self):
        """Forest Carbon Edge: test for no forest edge effects."""
        from natcap.invest import forest_carbon_edge_effect

        args = {
            'aoi_vector_path': os.path.join(
                REGRESSION_DATA, 'input', 'small_aoi.shp'),
            'biomass_to_carbon_conversion_factor': '0.47',
            'biophysical_table_path': os.path.join(
                REGRESSION_DATA, 'input',
                'no_forest_edge_carbon_lu_table.csv'),
            'compute_forest_edge_effects': False,
            'lulc_raster_path': os.path.join(
                REGRESSION_DATA, 'input', 'small_lulc.tif'),
            'n_nearest_model_points': 1,
            'pools_to_calculate': 'above_ground',
            'results_suffix': 'small_no_edge_effect',
            'tropical_forest_edge_carbon_model_vector_path': os.path.join(
                REGRESSION_DATA, 'input', 'core_data',
                'forest_carbon_edge_regression_model_parameters.shp'),
            'workspace_dir': self.workspace_dir,
            'n_workers': -1
        }
        forest_carbon_edge_effect.execute(args)

        ForestCarbonEdgeTests._test_same_files(
            os.path.join(
                REGRESSION_DATA, 'file_list_no_edge_effect.txt'),
            args['workspace_dir'])
        self._assert_vector_results_close(
            'id',
            ['c_sum', 'c_ha_mean'],
            os.path.join(
                args['workspace_dir'],
                'aggregated_carbon_stocks_small_no_edge_effect.shp'),
            os.path.join(
                REGRESSION_DATA, 'agg_results_no_edge_effect.shp'))

    def test_carbon_bad_pool_value(self):
        """Forest Carbon Edge: test with bad carbon pool value."""
        from natcap.invest import forest_carbon_edge_effect

        args = {
            'biomass_to_carbon_conversion_factor': '0.47',
            'biophysical_table_path': os.path.join(
                REGRESSION_DATA, 'input',
                'no_forest_edge_carbon_lu_table_bad_pool_value.csv'),
            'compute_forest_edge_effects': False,
            'lulc_raster_path': os.path.join(
                REGRESSION_DATA, 'input', 'small_lulc.tif'),
            'n_nearest_model_points': 1,
            'pools_to_calculate': 'all',
            'results_suffix': 'small_no_edge_effect',
            'tropical_forest_edge_carbon_model_vector_path': os.path.join(
                REGRESSION_DATA, 'input', 'core_data',
                'forest_carbon_edge_regression_model_parameters.shp'),
            'workspace_dir': self.workspace_dir,
            'n_workers': -1
        }

        with self.assertRaises(ValueError) as cm:
            forest_carbon_edge_effect.execute(args)
        expected_message = 'Could not interpret carbon pool value'
        actual_message = str(cm.exception)
        self.assertTrue(expected_message in actual_message, actual_message)

    def test_missing_lulc_value(self):
        """Forest Carbon Edge: test with missing LULC value."""
        from natcap.invest import forest_carbon_edge_effect
        import pandas

        args = {
            'aoi_vector_path': os.path.join(
                REGRESSION_DATA, 'input', 'small_aoi.shp'),
            'biomass_to_carbon_conversion_factor': '0.47',
            'biophysical_table_path': os.path.join(
                REGRESSION_DATA, 'input', 'forest_edge_carbon_lu_table.csv'),
            'compute_forest_edge_effects': True,
            'lulc_raster_path': os.path.join(
                REGRESSION_DATA, 'input', 'small_lulc.tif'),
            'n_nearest_model_points': 10,
            'pools_to_calculate': 'all',
            'tropical_forest_edge_carbon_model_vector_path': os.path.join(
                REGRESSION_DATA, 'input', 'core_data',
                'forest_carbon_edge_regression_model_parameters.shp'),
            'workspace_dir': self.workspace_dir,
            'n_workers': -1
        }

        bad_biophysical_table_path = os.path.join(
            self.workspace_dir, 'bad_biophysical_table.csv')

        bio_df = pandas.read_csv(args['biophysical_table_path'])
        bio_df = bio_df[bio_df['lucode'] != 4]
        bio_df.to_csv(bad_biophysical_table_path)
        bio_df = None

        args['biophysical_table_path'] = bad_biophysical_table_path
        with self.assertRaises(ValueError) as cm:
            forest_carbon_edge_effect.execute(args)
        expected_message = (
            "The missing values found in the LULC raster but not the table"
            " are: [4.]")
        actual_message = str(cm.exception)
        self.assertTrue(expected_message in actual_message, actual_message)

    def test_carbon_nodata_lulc(self):
        """Forest Carbon Edge: ensure nodata lulc raster cause exception."""
        from natcap.invest import forest_carbon_edge_effect

        args = {
            'aoi_vector_path': os.path.join(
                REGRESSION_DATA, 'input', 'small_aoi.shp'),
            'biomass_to_carbon_conversion_factor': '0.47',
            'biophysical_table_path': os.path.join(
                REGRESSION_DATA, 'input', 'forest_edge_carbon_lu_table.csv'),
            'compute_forest_edge_effects': True,
            'lulc_raster_path': os.path.join(
                REGRESSION_DATA, 'input', 'nodata_lulc.tif'),
            'n_nearest_model_points': 10,
            'pools_to_calculate': 'all',
            'tropical_forest_edge_carbon_model_vector_path': os.path.join(
                REGRESSION_DATA, 'input', 'core_data',
                'forest_carbon_edge_regression_model_parameters.shp'),
            'workspace_dir': self.workspace_dir,
            'n_workers': -1
        }
        with self.assertRaises(ValueError) as cm:
            forest_carbon_edge_effect.execute(args)
        expected_message = 'The landcover raster '
        actual_message = str(cm.exception)
        self.assertTrue(expected_message in actual_message, actual_message)

    def test_combine_carbon_maps(self):
        """Test `combine_carbon_maps`"""
        from natcap.invest.forest_carbon_edge_effect import combine_carbon_maps

        # note that NODATA_VALUE = -1
        carbon_arr1 = numpy.array([[7, 2, -1], [0, -2, -1]])
        carbon_arr2 = numpy.array([[-1, 900, -1], [1, 20, 0]])

        expected_output = numpy.array([[7, 902, -1], [1, 18, 0]])

        actual_output = combine_carbon_maps(carbon_arr1, carbon_arr2)

        numpy.testing.assert_allclose(actual_output, expected_output)

    def test_aggregate_carbon_map(self):
        """Test `_aggregate_carbon_map`"""
        from natcap.invest.forest_carbon_edge_effect import \
            _aggregate_carbon_map

        aoi_vector_path = os.path.join(self.workspace_dir, "aoi.shp")
        carbon_map_path = os.path.join(self.workspace_dir, "carbon.tif")
        target_vector_path = os.path.join(self.workspace_dir,
                                          "agg_carbon.shp")

        # make data
        make_simple_vector(aoi_vector_path)
        carbon_array = numpy.array(([1, 2, 3], [4, 5, 6]))
        make_simple_raster(carbon_map_path, carbon_array)

        _aggregate_carbon_map(aoi_vector_path, carbon_map_path,
                              target_vector_path)

        # Validate fields in the agg carbon results vector
        with gdal.OpenEx(target_vector_path,
                         gdal.OF_VECTOR | gdal.GA_Update) as ws_ds:
            ws_layer = ws_ds.GetLayer()
            for field_name, expected_value in zip(['c_sum', 'c_ha_mean'],
                                                  [0.0021, 0.000336]):
                actual_values = [ws_feat.GetField(field_name)
                                 for ws_feat in ws_layer][0]
                error_msg = f"Error with {field_name} in agg_carbon.shp"
                self.assertEqual(actual_values, expected_value, msg=error_msg)

    def test_calculate_lulc_carbon_map(self):
        """Test `_calculate_lulc_carbon_map`"""
        from natcap.invest.forest_carbon_edge_effect import \
            _calculate_lulc_carbon_map

        # Make synthetic data
        lulc_raster_path = os.path.join(self.workspace_dir, "lulc.tif")
        lulc_array = numpy.array([[1, 2, 3], [3, 2, 1]], dtype=numpy.int16)
        make_simple_raster(lulc_raster_path, lulc_array)

        biophysical_table_path = os.path.join(self.workspace_dir,
                                              "biophysical_table.csv")

        data = {"lucode": [1, 2, 3]}
        df = pandas.DataFrame(data).set_index("lucode")
        df["is_tropical_forest"] = [0, 1, 0]
        df["c_above"] = [100, 500, 200]
        df.to_csv(biophysical_table_path)

        carbon_pool_type = 'c_above'
        ignore_tropical_type = False
        compute_forest_edge_effects = True
        carbon_map_path = os.path.join(self.workspace_dir, "output_carbon.tif")

        _calculate_lulc_carbon_map(
            lulc_raster_path, biophysical_table_path, carbon_pool_type,
            ignore_tropical_type, compute_forest_edge_effects,
            carbon_map_path)

        actual_output = pygeoprocessing.raster_to_numpy_array(carbon_map_path)
        expected_output = numpy.array([[100, 500, 200], [200, 500, 100]])

        numpy.testing.assert_allclose(actual_output, expected_output)

    def test_map_distance_from_tropical_forest_edge(self):
        """Test `_map_distance_from_tropical_forest_edge`"""
        from natcap.invest.forest_carbon_edge_effect import \
            _map_distance_from_tropical_forest_edge

        # Make synthetic data
        base_lulc_raster_path = os.path.join(self.workspace_dir, "lulc.tif")
        lulc_array = numpy.array([
            [2, 2, 3, 3, 3, 2, 2],
            [2, 1, 1, 1, 1, 1, 2],
            [3, 1, 1, 1, 1, 1, 3],
            [2, 1, 1, 1, 1, 1, 2],
            [2, 2, 3, 3, 3, 2, 2]
        ], dtype=numpy.int16)
        make_simple_raster(base_lulc_raster_path, lulc_array)

        biophysical_table_path = os.path.join(self.workspace_dir,
                                              "biophysical_table.csv")

        data = {"lucode": [1, 2, 3]}
        df = pandas.DataFrame(data).set_index("lucode")
        df["is_tropical_forest"] = [1, 0, 0]
        df["c_above"] = [100, 500, 200]
        df.to_csv(biophysical_table_path)

        target_edge_distance_path = os.path.join(self.workspace_dir,
                                                 "edge_distance.tif")
        target_mask_path = os.path.join(self.workspace_dir,
                                        "non_forest_mask.tif")

        _map_distance_from_tropical_forest_edge(
            base_lulc_raster_path, biophysical_table_path,
            target_edge_distance_path, target_mask_path)

        # check forest mask
        actual_output = pygeoprocessing.raster_to_numpy_array(target_mask_path)
        expected_output = numpy.array([
            [1, 1, 1, 1, 1, 1, 1],
            [1, 0, 0, 0, 0, 0, 1],
            [1, 0, 0, 0, 0, 0, 1],
            [1, 0, 0, 0, 0, 0, 1],
            [1, 1, 1, 1, 1, 1, 1]
        ], dtype=numpy.int16)
        numpy.testing.assert_allclose(actual_output, expected_output)

        # check edge distance map
        actual_output = pygeoprocessing.raster_to_numpy_array(
            target_edge_distance_path)
        expected_output = numpy.array([
            [0, 0, 0, 0, 0, 0, 0],
            [0, 1, 1, 1, 1, 1, 0],
            [0, 1, 2, 2, 2, 1, 0],
            [0, 1, 1, 1, 1, 1, 0],
            [0, 0, 0, 0, 0, 0, 0]
        ], dtype=numpy.int16)
        numpy.testing.assert_allclose(actual_output, expected_output)

    def test_calculate_tropical_forest_edge_carbon_map(self):
        """Test `_calculate_tropical_forest_edge_carbon_map`"""
        from natcap.invest.forest_carbon_edge_effect import \
            _calculate_tropical_forest_edge_carbon_map
        from scipy.spatial import cKDTree

        edge_dist_array = numpy.array([
            [0, 0, 0, 0, 0, 0, 0],
            [0, 1, 1, 1, 1, 1, 0],
            [0, 1, 2, 2, 2, 1, 0],
            [0, 1, 1, 1, 1, 1, 0],
            [0, 0, 0, 0, 0, 0, 0]
        ], dtype=numpy.int16)
        edge_distance_path = os.path.join(self.workspace_dir, "edge_dist.tif")
        make_simple_raster(edge_distance_path, edge_dist_array)
        spatial_index_pickle_path = os.path.join(self.workspace_dir,
                                                 "spatial_index.pkl")

        def _create_spatial_index_pickle(spatial_index_pickle_path,
                                         raster_path):
            """
            Create and save a KD-tree.

            This function reads the spatial extent and resolution from a raster
            file, then generates a grid of sample points in geographic space
            (one point every other row, all columns). It builds a KD-tree from
            these points for fast spatial lookup, along with synthetic theta
            and method model parameters, and saves the result as a pickle file.

            Args:
                spatial_index_pickle_path (str): Path to save the pickle file.
                raster_path (string): Path to the raster used to extract
                    spatial metadata.

            Return:
                None

            """
            # Get origin and pixel_size
            raster_info = pygeoprocessing.get_raster_info(raster_path)
            gt = raster_info['geotransform']#461261, 4923265
            origin_x, origin_y = gt[0], gt[3]
            pixel_size_x, pixel_size_y = raster_info['pixel_size']
            cols, rows = raster_info['raster_size']

            # only create a point every other row and every col (in raster)
            row_col_pairs = [(r, c) for r in range(0, rows, 2) for c in range(cols)]
            # Get spatial coordinates
            points = []
            for row, col in row_col_pairs:
                x = origin_x + col * pixel_size_x
                y = origin_y + row * pixel_size_y
                points.append((y, x))
                # note: row → y, col → x (so KD-tree works with (lat, lon))

            theta_model_parameters = numpy.linspace(
                100, 200, len(points)*3).reshape(len(points), 3)  # Nx3

            method_model_parameter = numpy.ones((len(points),))

            kd_tree = cKDTree(points)

            # Save the data as a tuple in a pickle file
            with open(spatial_index_pickle_path, 'wb') as f:
                pickle.dump((kd_tree, theta_model_parameters,
                             method_model_parameter), f)

        _create_spatial_index_pickle(spatial_index_pickle_path,
                                     edge_distance_path)

        n_nearest_model_points = 8
        biomass_to_carbon_conversion_factor = 1000
        tropical_forest_edge_carbon_map_path = os.path.join(self.workspace_dir,
                                                            "output.tif")

        _calculate_tropical_forest_edge_carbon_map(
            edge_distance_path, spatial_index_pickle_path,
            n_nearest_model_points, biomass_to_carbon_conversion_factor,
            tropical_forest_edge_carbon_map_path)

        actual_output = pygeoprocessing.raster_to_numpy_array(
            tropical_forest_edge_carbon_map_path)
        expected_output = numpy.array(
            [[-1, -1, -1, -1, -1, -1, -1],
             [-1, 13486.482, 13903.661, 15450.714, 16976.272, 17436.426, -1],
             [-1, 17600.988, 37163.07, 40048.15, 38613.932, 22213.786, -1],
             [-1, 22157.857, 22673.838, 24483.13, 26430.724, 26987.493, -1],
             [-1, -1, -1, -1, -1, -1, -1]])

        numpy.testing.assert_allclose(actual_output, expected_output)


    @staticmethod
    def _test_same_files(base_list_path, directory_path):
        """Assert files in `base_list_path` are in `directory_path`.

        Args:
            base_list_path (string): a path to a file that has one relative
                file path per line.
            directory_path (string): a path to a directory whose contents will
                be checked against the files listed in `base_list_file`

        Returns:
            None

        Raises:
            AssertionError when there are files listed in `base_list_file`
                that don't exist in the directory indicated by `path`
        """
        missing_files = []
        with open(base_list_path, 'r') as file_list:
            for file_path in file_list:
                full_path = os.path.join(directory_path, file_path.rstrip())
                if full_path == '':
                    continue
                if not os.path.isfile(full_path):
                    missing_files.append(full_path)
        if len(missing_files) > 0:
            raise AssertionError(
                "The following files were expected but not found: " +
                '\n'.join(missing_files))

    def _assert_vector_results_close(
            self, id_fieldname, field_list, result_vector_path,
            expected_vector_path):
        """Test workspace state against expected aggregate results.

        Args:
            id_fieldname (string): fieldname of the unique ID.
            field_list (list of string): list of fields to check
                near-equality.
            result_vector_path (string): path to the summary shapefile
                produced by the Forest Carbon Edge model.
            expected_vector_path (string): path to a vector that has the
                same fields and values as `result_vector_path`.

        Returns:
            None

        Raises:
            AssertionError if results are not nearly equal or missing.

        """
        result_vector = gdal.OpenEx(result_vector_path, gdal.OF_VECTOR)
        try:
            result_layer = result_vector.GetLayer()
            result_lookup = {}
            for feature in result_layer:
                result_lookup[feature.GetField(id_fieldname)] = dict(
                    [(fieldname, feature.GetField(fieldname))
                     for fieldname in field_list])
            expected_vector = gdal.OpenEx(
                expected_vector_path, gdal.OF_VECTOR)
            expected_layer = expected_vector.GetLayer()
            expected_lookup = {}
            for feature in expected_layer:
                expected_lookup[feature.GetField(id_fieldname)] = dict(
                    [(fieldname, feature.GetField(fieldname))
                     for fieldname in field_list])

            self.assertEqual(len(result_lookup), len(expected_lookup))
            not_close_values_list = []
            for feature_id in result_lookup:
                for fieldname in field_list:
                    result = result_lookup[feature_id][fieldname]
                    expected_result = expected_lookup[feature_id][fieldname]
                    if not numpy.isclose(result, expected_result):
                        not_close_values_list.append(
                            'id: %d, %s: %f (actual) vs %f (expected)' % (
                                feature_id, fieldname, result,
                                expected_result))
            if not_close_values_list:
                raise AssertionError(
                    'Values do not match: %s' % not_close_values_list)
        finally:
            result_layer = None
            if result_vector:
                gdal.Dataset.__swig_destroy__(result_vector)
            result_vector = None


class ForestCarbonEdgeValidationTests(unittest.TestCase):
    """Tests for the Forest Carbon Model MODEL_SPEC and validation."""

    def setUp(self):
        """Create a temporary workspace."""
        self.workspace_dir = tempfile.mkdtemp()
        self.base_required_keys = [
            'workspace_dir',
            'biophysical_table_path',
            'lulc_raster_path',
            'pools_to_calculate',
            'compute_forest_edge_effects',
        ]

    def tearDown(self):
        """Remove the temporary workspace after a test."""
        shutil.rmtree(self.workspace_dir)

    def test_missing_keys(self):
        """Forest Carbon Validate: assert missing required keys."""
        from natcap.invest import forest_carbon_edge_effect
        from natcap.invest import validation

        # empty args dict.
        validation_errors = forest_carbon_edge_effect.validate({})
        invalid_keys = validation.get_invalid_keys(validation_errors)
        expected_missing_keys = set(self.base_required_keys)
        self.assertEqual(invalid_keys, expected_missing_keys)

    def test_missing_keys_for_edge_effects(self):
        """Forest Carbon Validate: assert missing required for edge effects."""
        from natcap.invest import forest_carbon_edge_effect
        from natcap.invest import validation

        args = {'compute_forest_edge_effects': True}
        validation_errors = forest_carbon_edge_effect.validate(args)
        invalid_keys = validation.get_invalid_keys(validation_errors)
        expected_missing_keys = set(
            self.base_required_keys +
            ['n_nearest_model_points',
             'tropical_forest_edge_carbon_model_vector_path',
             'biomass_to_carbon_conversion_factor'])
        expected_missing_keys.difference_update(
            {'compute_forest_edge_effects'})
        self.assertEqual(invalid_keys, expected_missing_keys)
