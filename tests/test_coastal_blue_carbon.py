# -*- coding: utf-8 -*-
"""Tests for Coastal Blue Carbon Functions."""
import logging
import os
import pprint
import shutil
import tempfile
import unittest

import numpy
from osgeo import gdal, osr
import pygeoprocessing
from natcap.invest import utils

from natcap.invest.coastal_blue_carbon import coastal_blue_carbon


REGRESSION_DATA = os.path.join(
    os.path.dirname(__file__), '..', 'data', 'invest-test-data',
    'coastal_blue_carbon')
LOGGER = logging.getLogger(__name__)


class TestPreprocessor(unittest.TestCase):
    """Test Coastal Blue Carbon preprocessor functions."""

    def setUp(self):
        """Create a temp directory for the workspace."""
        self.workspace_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Remove workspace."""
        shutil.rmtree(self.workspace_dir)

    def test_sample_data(self):
        """CBC Preprocessor: Test on sample data."""
        from natcap.invest.coastal_blue_carbon import preprocessor

        snapshot_csv_path = os.path.join(
            REGRESSION_DATA, 'inputs', 'snapshots.csv')

        args = {
            'workspace_dir': os.path.join(self.workspace_dir, 'workspace'),
            'results_suffix': '150225',
            'lulc_lookup_table_path': os.path.join(
                REGRESSION_DATA, 'inputs', 'lulc_lookup.csv'),
            'landcover_snapshot_csv': snapshot_csv_path,
        }
        preprocessor.execute(args)

        # walk through all files in the workspace and assert that outputs have
        # the file suffix.
        non_suffixed_files = []
        outputs_dir = os.path.join(
            args['workspace_dir'], 'outputs_preprocessor')
        for root_dir, dirnames, filenames in os.walk(outputs_dir):
            for filename in filenames:
                if not filename.lower().endswith('.txt'):  # ignore logfile
                    basename, extension = os.path.splitext(filename)
                    if not basename.endswith('_150225'):
                        path_rel_to_workspace = os.path.relpath(
                            os.path.join(root_dir, filename),
                            args['workspace_dir'])
                        non_suffixed_files.append(path_rel_to_workspace)

        if non_suffixed_files:
            self.fail('%s files are missing suffixes: %s' %
                      (len(non_suffixed_files),
                       pprint.pformat(non_suffixed_files)))

        expected_landcover_codes = set(range(0, 24))
        found_landcover_codes = set(utils.build_lookup_from_csv(
            os.path.join(outputs_dir,
                         'carbon_biophysical_table_template_150225.csv'),
            'code').keys())
        self.assertEqual(expected_landcover_codes, found_landcover_codes)

    def test_transition_table(self):
        """CBC Preprocessor: Test creation of transition table."""
        from natcap.invest.coastal_blue_carbon import preprocessor

        srs = osr.SpatialReference()
        srs.ImportFromEPSG(3157)
        projection_wkt = srs.ExportToWkt()
        origin = (443723.127327877911739, 4956546.905980412848294)
        matrix_a = numpy.array([
            [0, 1],
            [0, 1],
            [0, 1]], dtype=numpy.int16)
        filename_a = os.path.join(self.workspace_dir, 'raster_a.tif')
        pygeoprocessing.numpy_array_to_raster(
            matrix_a, -1, (100, -100), origin, projection_wkt, filename_a)

        matrix_b = numpy.array([
            [0, 1],
            [1, 0],
            [-1, -1]], dtype=numpy.int16)
        filename_b = os.path.join(self.workspace_dir, 'raster_b.tif')
        pygeoprocessing.numpy_array_to_raster(
            matrix_b, -1, (100, -100), origin, projection_wkt, filename_b)

        landcover_table_path = os.path.join(self.workspace_dir,
                                            'lulc_table.csv')
        with open(landcover_table_path, 'w') as lulc_csv:
            lulc_csv.write('code,lulc-class,is_coastal_blue_carbon_habitat\n')
            lulc_csv.write('0,mangrove,True\n')
            lulc_csv.write('1,parking lot,False\n')

        landcover_table = utils.build_lookup_from_csv(
            landcover_table_path, 'code')
        target_table_path = os.path.join(self.workspace_dir,
                                         'transition_table.csv')

        # Remove landcover code 1 from the table; expect error.
        del landcover_table[1]
        with self.assertRaises(ValueError) as context:
            preprocessor._create_transition_table(
                landcover_table, [filename_a, filename_b], target_table_path)

        self.assertIn('missing a row with the landuse code 1',
                      str(context.exception))

        # Re-load the landcover table
        landcover_table = utils.build_lookup_from_csv(
            landcover_table_path, 'code')
        preprocessor._create_transition_table(
            landcover_table, [filename_a, filename_b], target_table_path)

        with open(target_table_path) as transition_table:
            self.assertEqual(
                transition_table.readline(),
                'lulc-class,mangrove,parking lot\n')
            self.assertEqual(
                transition_table.readline(),
                'mangrove,accum,disturb\n')
            self.assertEqual(
                transition_table.readline(),
                'parking lot,accum,NCC\n')

            # After the above lines is a blank line, then the legend.
            # Deliberately not testing the legend.
            self.assertEqual(transition_table.readline(), '\n')


class TestCBC2(unittest.TestCase):
    """Test Coastal Blue Carbon main model functions."""

    def setUp(self):
        """Create a temp directory for the workspace."""
        self.workspace_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Remove workspace after each test function."""
        shutil.rmtree(self.workspace_dir)

    def test_extract_snapshots(self):
        """CBC: Extract snapshots from a snapshot CSV."""
        csv_path = os.path.join(self.workspace_dir, 'snapshots.csv')

        transition_years = (2000, 2010, 2020)
        transition_rasters = []
        with open(csv_path, 'w') as transitions_csv:
            # Check that we can interpret varying case.
            transitions_csv.write('snapshot_YEAR,raster_PATH\n')
            for transition_year in transition_years:
                # Write absolute paths.
                transition_file_path = os.path.join(
                    self.workspace_dir, f'{transition_year}.tif)')
                transition_rasters.append(transition_file_path)
                transitions_csv.write(
                    f'{transition_year},{transition_file_path}\n')

            # Make one path relative to the workspace, where the transitions
            # CSV also lives.
            # The expected raster path is absolute.
            transitions_csv.write('2030,some_path.tif\n')
            transition_years += (2030,)
            transition_rasters.append(os.path.join(self.workspace_dir,
                                                   'some_path.tif'))

        extracted_transitions = (
            coastal_blue_carbon._extract_snapshots_from_table(csv_path))

        self.assertEqual(
            extracted_transitions,
            dict(zip(transition_years, transition_rasters)))

    def test_track_latest_transition_year(self):
        """CBC: Track the latest disturbance year."""
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(32731)  # WGS84 / UTM zone 31 S
        wkt = srs.ExportToWkt()

        current_disturbance_vol_raster = os.path.join(
            self.workspace_dir, 'cur_disturbance.tif')
        current_disturbance_vol_matrix = numpy.array([
            [5.0, 1.0],
            [-1, 3.0]], dtype=numpy.float32)
        pygeoprocessing.numpy_array_to_raster(
            current_disturbance_vol_matrix, -1, (2, -2), (2, -2), wkt,
            current_disturbance_vol_raster)

        known_transition_years_raster = os.path.join(
            self.workspace_dir, 'known_transition_years.tif')
        known_transition_years_matrix = numpy.array([
            [100, 100],
            [5, 6]], dtype=numpy.uint16)
        pygeoprocessing.numpy_array_to_raster(
            known_transition_years_matrix, 100, (2, -2), (2, -2), wkt,
            known_transition_years_raster)

        target_raster_path = os.path.join(
            self.workspace_dir, 'new_tracked_years.tif')
        coastal_blue_carbon._track_latest_transition_year(
            current_disturbance_vol_raster,
            known_transition_years_raster,
            11,  # current "year" being disturbed.
            target_raster_path)

        expected_array = numpy.array([
            [11, 11],
            [5, 11]], dtype=numpy.uint16)
        try:
            raster = gdal.OpenEx(target_raster_path)
            numpy.testing.assert_allclose(
                raster.ReadAsArray(),
                expected_array)
        finally:
            raster = None

    def test_read_transition_matrix(self):
        """CBC: Test transition matrix reading."""
        # The full biophysical table will have much, much more information.  To
        # keep the test simple, I'm only tracking the columns I know I'll need
        # in this function.
        biophysical_table = {
            1: {'lulc-class': 'a',
                'soil-yearly-accumulation': 2,
                'biomass-yearly-accumulation': 3,
                'soil-high-impact-disturb': 4,
                'biomass-high-impact-disturb': 5},
            2: {'lulc-class': 'b',
                'soil-yearly-accumulation': 6,
                'biomass-yearly-accumulation': 7,
                'soil-high-impact-disturb': 8,
                'biomass-high-impact-disturb': 9},
            3: {'lulc-class': 'c',
                'soil-yearly-accumulation': 10,
                'biomass-yearly-accumulation': 11,
                'soil-high-impact-disturb': 12,
                'biomass-high-impact-disturb': 13}
        }

        transition_csv_path = os.path.join(self.workspace_dir,
                                           'transitions.csv')
        with open(transition_csv_path, 'w') as transition_csv:
            transition_csv.write('lulc-class,a,b,c\n')
            transition_csv.write('a,NCC,accum,high-impact-disturb\n')
            transition_csv.write('b,,NCC,accum\n')
            transition_csv.write('c,accum,,NCC\n')
            transition_csv.write(',,,\n')
            transition_csv.write(',legend,,')  # simulate legend

        disturbance_matrices, accumulation_matrices = (
             coastal_blue_carbon._read_transition_matrix(
                 transition_csv_path, biophysical_table))

        expected_biomass_disturbance = numpy.zeros((4, 4), dtype=numpy.float32)
        expected_biomass_disturbance[1, 3] = (
            biophysical_table[1]['biomass-high-impact-disturb'])
        numpy.testing.assert_allclose(
            expected_biomass_disturbance,
            disturbance_matrices['biomass'].toarray())

        expected_soil_disturbance = numpy.zeros((4, 4), dtype=numpy.float32)
        expected_soil_disturbance[1, 3] = (
            biophysical_table[1]['soil-high-impact-disturb'])
        numpy.testing.assert_allclose(
            expected_soil_disturbance,
            disturbance_matrices['soil'].toarray())

        expected_biomass_accumulation = numpy.zeros(
            (4, 4), dtype=numpy.float32)
        expected_biomass_accumulation[3, 1] = (
            biophysical_table[1]['biomass-yearly-accumulation'])
        expected_biomass_accumulation[1, 2] = (
            biophysical_table[2]['biomass-yearly-accumulation'])
        expected_biomass_accumulation[2, 3] = (
            biophysical_table[3]['biomass-yearly-accumulation'])
        numpy.testing.assert_allclose(
            expected_biomass_accumulation,
            accumulation_matrices['biomass'].toarray())

        expected_soil_accumulation = numpy.zeros((4, 4), dtype=numpy.float32)
        expected_soil_accumulation[3, 1] = (
            biophysical_table[1]['soil-yearly-accumulation'])
        expected_soil_accumulation[1, 2] = (
            biophysical_table[2]['soil-yearly-accumulation'])
        expected_soil_accumulation[2, 3] = (
            biophysical_table[3]['soil-yearly-accumulation'])
        numpy.testing.assert_allclose(
            expected_soil_accumulation,
            accumulation_matrices['soil'].toarray())

    def test_emissions(self):
        """CBC: Check emissions calculations."""
        volume_disturbed_carbon = numpy.array(
            [[5.5, coastal_blue_carbon.NODATA_FLOAT32_MIN]], dtype=numpy.float32)
        year_last_disturbed = numpy.array(
            [[10, coastal_blue_carbon.NODATA_UINT16_MAX]], dtype=numpy.uint16)
        half_life = numpy.array([[7.5, 7.5]], dtype=numpy.float32)
        current_year = 15

        result_matrix = coastal_blue_carbon._calculate_emissions(
            volume_disturbed_carbon, year_last_disturbed, half_life,
            current_year)

        # Calculated by hand.
        expected_array = numpy.array([
            [0.3058625, coastal_blue_carbon.NODATA_FLOAT32_MIN]],
            dtype=numpy.float32)
        numpy.testing.assert_allclose(
            result_matrix, expected_array, rtol=1E-6)

    def test_add_rasters(self):
        """CBC: Check that we can add two rasters."""
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(32731)  # WGS84 / UTM zone 31 S
        wkt = srs.ExportToWkt()

        raster_a_path = os.path.join(self.workspace_dir, 'a.tif')
        pygeoprocessing.numpy_array_to_raster(
            numpy.array([[5, 15, 12]], dtype=numpy.uint8),
            15, (2, -2), (2, -2), wkt, raster_a_path)

        raster_b_path = os.path.join(self.workspace_dir, 'b.tif')
        pygeoprocessing.numpy_array_to_raster(
            numpy.array([[3, 4, 5]], dtype=numpy.uint8),
            5, (2, -2), (2, -2), wkt, raster_b_path)

        target_path = os.path.join(self.workspace_dir, 'output.tif')
        coastal_blue_carbon._sum_n_rasters(
            [raster_a_path, raster_b_path], target_path)

        nodata = coastal_blue_carbon.NODATA_FLOAT32_MIN
        try:
            raster = gdal.OpenEx(target_path)
            numpy.testing.assert_allclose(
                raster.ReadAsArray(),
                numpy.array([[8, nodata, nodata]], dtype=numpy.float32))
        finally:
            raster = None

    @staticmethod
    def _create_model_args(target_dir):
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(32731)  # WGS84 / UTM zone 31 S
        wkt = srs.ExportToWkt()

        biophysical_table = [
            ['code', 'lulc-class', 'biomass-initial', 'soil-initial',
                'litter-initial', 'biomass-half-life',
                'biomass-low-impact-disturb', 'biomass-med-impact-disturb',
                'biomass-high-impact-disturb', 'biomass-yearly-accumulation',
                'soil-half-life', 'soil-low-impact-disturb',
                'soil-med-impact-disturb', 'soil-high-impact-disturb',
                'soil-yearly-accumulation', 'litter-yearly-accumulation'],
            [1, 'mangrove',
                64, 313, 3,  # initial
                15, 0.5, 0.5, 1, 2,  # biomass
                7.5, 0.3, 0.5, 0.66, 5.35,  # soil
                1],  # litter accum.
            [2, 'parking lot',
                0, 0, 0,  # initial
                0, 0, 0, 0, 0,  # biomass
                0, 0, 0, 0, 0,  # soil
                0],  # litter accum.
        ]
        biophysical_table_path = os.path.join(
            target_dir, 'biophysical.csv')
        with open(biophysical_table_path, 'w') as bio_table:
            for line_list in biophysical_table:
                line = ','.join(str(field) for field in line_list)
                bio_table.write(f'{line}\n')

        transition_matrix = [
            ['lulc-class', 'mangrove', 'parking lot'],
            ['mangrove', 'NCC', 'high-impact-disturb'],
            ['parking lot', 'accum', 'NCC']
        ]
        transition_matrix_path = os.path.join(
            target_dir, 'transitions.csv')
        with open(transition_matrix_path, 'w') as transition_table:
            for line_list in transition_matrix:
                line = ','.join(line_list)
                transition_table.write(f'{line}\n')

        baseline_landcover_raster_path = os.path.join(
            target_dir, 'baseline_lulc.tif')
        baseline_matrix = numpy.array([[1, 2]], dtype=numpy.uint8)
        pygeoprocessing.numpy_array_to_raster(
            baseline_matrix, 255, (2, -2), (2, -2), wkt,
            baseline_landcover_raster_path)

        snapshot_2010_raster_path = os.path.join(
            target_dir, 'snapshot_2010.tif')
        snapshot_2010_matrix = numpy.array([[2, 1]], dtype=numpy.uint8)
        pygeoprocessing.numpy_array_to_raster(
            snapshot_2010_matrix, 255, (2, -2), (2, -2), wkt,
            snapshot_2010_raster_path)

        snapshot_2020_raster_path = os.path.join(
            target_dir, 'snapshot_2020.tif')
        snapshot_2020_matrix = numpy.array([[1, 2]], dtype=numpy.uint8)
        pygeoprocessing.numpy_array_to_raster(
            snapshot_2020_matrix, 255, (2, -2), (2, -2), wkt,
            snapshot_2020_raster_path)

        snapshot_rasters_csv_path = os.path.join(
            target_dir, 'snapshot_rasters.csv')
        baseline_year = 2000
        with open(snapshot_rasters_csv_path, 'w') as snapshot_rasters_csv:
            snapshot_rasters_csv.write('snapshot_year,raster_path\n')
            snapshot_rasters_csv.write(
                f'{baseline_year},{baseline_landcover_raster_path}\n')
            snapshot_rasters_csv.write(
                f'2010,{snapshot_2010_raster_path}\n')
            snapshot_rasters_csv.write(
                f'2020,{snapshot_2020_raster_path}\n')

        args = {
            'landcover_transitions_table': transition_matrix_path,
            'landcover_snapshot_csv': snapshot_rasters_csv_path,
            'biophysical_table_path': biophysical_table_path,
            'analysis_year': 2030,
            'do_economic_analysis': True,
            'use_price_table': True,
            'price_table_path': os.path.join(target_dir,
                                             'price_table.csv'),
            'discount_rate': 4,
        }

        with open(args['price_table_path'], 'w') as price_table:
            price_table.write('year,price\n')
            prior_year_price = 1.0
            for year in range(baseline_year,
                              args['analysis_year']+1):
                price = prior_year_price * 1.04
                price_table.write(f'{year},{price}\n')
        return args

    def test_duplicate_lulc_classes(self):
        """CBC: Raise an execption if duplicate lulc-classes."""
        args = TestCBC2._create_model_args(self.workspace_dir)
        args['workspace_dir'] = os.path.join(self.workspace_dir, 'workspace')
        with open(args['biophysical_table_path'], 'r') as table:
            lines = table.readlines()

        with open(args['biophysical_table_path'], 'a') as table:
            last_line_contents = lines[-1].strip().split(',')
            last_line_contents[0] = '3'  # assign a new code
            table.write(','.join(last_line_contents))

        with self.assertRaises(ValueError) as context:
            coastal_blue_carbon.execute(args)

        self.assertIn("`lulc-class` column must be unique",
                      str(context.exception))

    def test_model_no_analysis_year_no_price_table(self):
        """CBC: Test the model's execution."""
        args = TestCBC2._create_model_args(self.workspace_dir)
        args['workspace_dir'] = os.path.join(self.workspace_dir, 'workspace')
        del args['analysis_year']  # final year is 2020.
        args['use_price_table'] = False
        args['inflation_rate'] = 5
        args['price'] = 10.0

        coastal_blue_carbon.execute(args)

        # Sample values calculated by hand.  Pixel 0 only accumulates.  Pixel 1
        # has no accumulation (per the biophysical table) and also has no
        # emissions.
        expected_sequestration_2000_to_2010 = numpy.array(
            [[83.5, 0]], dtype=numpy.float32)
        raster_path = os.path.join(
            args['workspace_dir'], 'output',
            ('total-net-carbon-sequestration-between-'
                '2000-and-2010.tif'))
        try:
            raster = gdal.OpenEx(raster_path)
            numpy.testing.assert_allclose(
                raster.ReadAsArray(),
                expected_sequestration_2000_to_2010)
        finally:
            raster = None

        expected_sequestration_2010_to_2020 = numpy.array(
            [[-179.84901, 73.5]], dtype=numpy.float32)
        raster_path = os.path.join(
            args['workspace_dir'], 'output',
            ('total-net-carbon-sequestration-between-'
                '2010-and-2020.tif'))
        try:
            raster = gdal.OpenEx(raster_path)
            numpy.testing.assert_allclose(
                raster.ReadAsArray(),
                expected_sequestration_2010_to_2020, rtol=1e-6)
        finally:
            raster = None

        # Total sequestration is the sum of all the previous sequestration.
        expected_total_sequestration = (
            expected_sequestration_2000_to_2010 +
            expected_sequestration_2010_to_2020)
        raster_path = os.path.join(
            args['workspace_dir'], 'output',
            'total-net-carbon-sequestration.tif')
        try:
            raster = gdal.OpenEx(raster_path)
            numpy.testing.assert_allclose(
                raster.ReadAsArray(),
                expected_total_sequestration, rtol=1e-6)
        finally:
            raster = None

        expected_net_present_value_at_2020 = numpy.array(
            [[-21135.857,  16123.521]], dtype=numpy.float32)
        raster_path = os.path.join(
            args['workspace_dir'], 'output', 'net-present-value-at-2020.tif')
        try:
            raster = gdal.OpenEx(raster_path)
            numpy.testing.assert_allclose(
                raster.ReadAsArray(),
                expected_net_present_value_at_2020, rtol=1e-6)
        finally:
            raster = None

    def test_model(self):
        """CBC: Test the model's execution."""
        args = TestCBC2._create_model_args(self.workspace_dir)
        args['workspace_dir'] = os.path.join(self.workspace_dir, 'workspace')

        coastal_blue_carbon.execute(args)

        # Sample values calculated by hand.  Pixel 0 only accumulates.  Pixel 1
        # has no accumulation (per the biophysical table) and also has no
        # emissions.
        expected_sequestration_2000_to_2010 = numpy.array(
            [[83.5, 0]], dtype=numpy.float32)
        raster_path = os.path.join(
            args['workspace_dir'], 'output',
            ('total-net-carbon-sequestration-between-'
                '2000-and-2010.tif'))
        try:
            raster = gdal.OpenEx(raster_path)
            numpy.testing.assert_allclose(
                raster.ReadAsArray(),
                expected_sequestration_2000_to_2010)
        finally:
            raster = None

        expected_sequestration_2010_to_2020 = numpy.array(
            [[-179.84901, 73.5]], dtype=numpy.float32)
        raster_path = os.path.join(
            args['workspace_dir'], 'output',
            ('total-net-carbon-sequestration-between-'
                '2010-and-2020.tif'))
        try:
            raster = gdal.OpenEx(raster_path)
            numpy.testing.assert_allclose(
                raster.ReadAsArray(),
                expected_sequestration_2010_to_2020, rtol=1e-6)
        finally:
            raster = None

        expected_sequestration_2020_to_2030 = numpy.array(
            [[73.5, -28.698004]], dtype=numpy.float32)
        raster_path = os.path.join(
            args['workspace_dir'], 'output',
            ('total-net-carbon-sequestration-between-'
                '2020-and-2030.tif'))
        try:
            raster = gdal.OpenEx(raster_path)
            numpy.testing.assert_allclose(
                raster.ReadAsArray(),
                expected_sequestration_2020_to_2030, rtol=1e-6)
        finally:
            raster = None

        # Total sequestration is the sum of all the previous sequestration.
        expected_total_sequestration = (
            expected_sequestration_2000_to_2010 +
            expected_sequestration_2010_to_2020 +
            expected_sequestration_2020_to_2030)
        raster_path = os.path.join(
            args['workspace_dir'], 'output',
            'total-net-carbon-sequestration.tif')
        try:
            raster = gdal.OpenEx(raster_path)
            numpy.testing.assert_allclose(
                raster.ReadAsArray(),
                expected_total_sequestration, rtol=1e-6)
        finally:
            raster = None

        expected_net_present_value_at_2030 = numpy.array(
            [[-427.3467, 837.93445]], dtype=numpy.float32)
        raster_path = os.path.join(
            args['workspace_dir'], 'output', 'net-present-value-at-2030.tif')
        try:
            raster = gdal.OpenEx(raster_path)
            numpy.testing.assert_allclose(
                raster.ReadAsArray(),
                expected_net_present_value_at_2030, rtol=1e-6)
        finally:
            raster = None

    def test_model_no_transitions(self):
        """CBC: Test model without transitions.

        When the model executes without transitions, we still evaluate carbon
        sequestration (accumulation only) for the whole baseline period.
        """
        args = TestCBC2._create_model_args(self.workspace_dir)
        args['workspace_dir'] = os.path.join(self.workspace_dir, 'workspace')

        prior_snapshots = coastal_blue_carbon._extract_snapshots_from_table(
            args['landcover_snapshot_csv'])
        baseline_year = min(prior_snapshots.keys())
        baseline_raster = prior_snapshots[baseline_year]
        with open(args['landcover_snapshot_csv'], 'w') as snapshot_csv:
            snapshot_csv.write('snapshot_year,raster_path\n')
            snapshot_csv.write(f'{baseline_year},{baseline_raster}\n')
        args['analysis_year'] = baseline_year + 10

        # Use valuation parameters rather than price table.
        args['use_price_table'] = False
        args['inflation_rate'] = 4
        args['price'] = 1.0

        coastal_blue_carbon.execute(args)

        # Check sequestration raster
        expected_sequestration_2000_to_2010 = numpy.array(
            [[83.5, 0.]], dtype=numpy.float32)
        raster_path = os.path.join(
            args['workspace_dir'], 'output',
            ('total-net-carbon-sequestration-between-'
                '2000-and-2010.tif'))
        try:
            raster= gdal.OpenEx(raster_path)
            numpy.testing.assert_allclose(
                raster.ReadAsArray(),
                expected_sequestration_2000_to_2010)
        finally:
            raster = None

        # Check valuation raster
        # Discount rate here matches the inflation rate, so the value of the 10
        # years' accumulation is just 1*(10 years of accumulation).
        expected_net_present_value_at_2010 = numpy.array(
            [[835.0, 0.]], dtype=numpy.float32)
        raster_path = os.path.join(
            args['workspace_dir'], 'output', 'net-present-value-at-2010.tif')
        try:
            raster = gdal.OpenEx(raster_path)
            numpy.testing.assert_allclose(
                raster.ReadAsArray(),
                expected_net_present_value_at_2010, rtol=1e-6)
        finally:
            raster = None

    def test_validation(self):
        """CBC: Test custom validation."""
        args = TestCBC2._create_model_args(self.workspace_dir)
        args['workspace_dir'] = self.workspace_dir

        # verify validation passes on basic set of arguments.
        validation_warnings = coastal_blue_carbon.validate(args)
        self.assertEqual([], validation_warnings)

        # Now work through the extra validation warnings.
        # Create an invalid transitions table.
        invalid_raster_path = os.path.join(self.workspace_dir,
                                           'invalid_raster.tif')
        with open(invalid_raster_path, 'w') as raster:
            raster.write('not a raster')

        # Write over the landcover snapshot CSV
        prior_snapshots = coastal_blue_carbon._extract_snapshots_from_table(
            args['landcover_snapshot_csv'])
        baseline_year = min(prior_snapshots)
        with open(args['landcover_snapshot_csv'], 'w') as snapshot_table:
            snapshot_table.write('snapshot_year,raster_path\n')
            snapshot_table.write(
                f'{baseline_year},{prior_snapshots[baseline_year]}\n')
            snapshot_table.write(
                f"{baseline_year + 10},{invalid_raster_path}")

        # analysis year must be >= the last transition year.
        args['analysis_year'] = baseline_year

        validation_warnings = coastal_blue_carbon.validate(args)
        self.assertEqual(len(validation_warnings), 2)
        self.assertIn(
            f"Raster for snapshot {baseline_year + 10} could not "
            "be validated", validation_warnings[0][1])
        self.assertIn(
            "Analysis year 2000 must be >= the latest snapshot year "
            "(2010)",
            validation_warnings[1][1])
