import numpy
import os
import shutil
import tempfile
import types
import unittest

import geometamaker
from natcap.invest import spec_utils
from natcap.invest.unit_registry import u
import pygeoprocessing
from osgeo import gdal
from osgeo import ogr
from osgeo import osr
from shapely.geometry import Point

gdal.UseExceptions()


class SpecUtilsUnitTests(unittest.TestCase):
    """Unit tests for natcap.invest.spec_utils."""

    def test_format_unit(self):
        """spec_utils: test converting units to strings with format_unit."""
        from natcap.invest import spec_utils
        for unit_name, expected in [
                ('meter', 'm'),
                ('meter / second', 'm/s'),
                ('foot * mm', 'ft · mm'),
                ('t * hr * ha / ha / MJ / mm', 't · h · ha / (ha · MJ · mm)'),
                ('mm^3 / year', 'mm³/year')
        ]:
            unit = spec_utils.u.Unit(unit_name)
            actual = spec_utils.format_unit(unit)
            self.assertEqual(expected, actual)

    def test_format_unit_raises_error(self):
        """spec_utils: format_unit raises TypeError if not a pint.Unit."""
        from natcap.invest import spec_utils
        with self.assertRaises(TypeError):
            spec_utils.format_unit({})


class TestDescribeArgFromSpec(unittest.TestCase):
    """Test building RST for various invest args specifications."""

    def test_number_spec(self):
        spec = {
            "name": "Bar",
            "about": "Description",
            "type": "number",
            "units": u.meter**3/u.month,
            "expression": "value >= 0"
        }
        out = spec_utils.describe_arg_from_spec(spec['name'], spec)
        expected_rst = ([
            '**Bar** (`number <input_types.html#number>`__, '
            'units: **m³/month**, *required*): Description'])
        self.assertEqual(repr(out), repr(expected_rst))

    def test_ratio_spec(self):
        spec = {
            "name": "Bar",
            "about": "Description",
            "type": "ratio"
        }
        out = spec_utils.describe_arg_from_spec(spec['name'], spec)
        expected_rst = (['**Bar** (`ratio <input_types.html#ratio>`__, '
                         '*required*): Description'])
        self.assertEqual(repr(out), repr(expected_rst))

    def test_percent_spec(self):
        spec = {
            "name": "Bar",
            "about": "Description",
            "type": "percent",
            "required": False
        }
        out = spec_utils.describe_arg_from_spec(spec['name'], spec)
        expected_rst = (['**Bar** (`percent <input_types.html#percent>`__, '
                         '*optional*): Description'])
        self.assertEqual(repr(out), repr(expected_rst))

    def test_code_spec(self):
        spec = {
            "name": "Bar",
            "about": "Description",
            "type": "integer",
            "required": True
        }
        out = spec_utils.describe_arg_from_spec(spec['name'], spec)
        expected_rst = (['**Bar** (`integer <input_types.html#integer>`__, '
                         '*required*): Description'])
        self.assertEqual(repr(out), repr(expected_rst))

    def test_boolean_spec(self):
        spec = {
            "name": "Bar",
            "about": "Description",
            "type": "boolean"
        }
        out = spec_utils.describe_arg_from_spec(spec['name'], spec)
        expected_rst = (['**Bar** (`true/false <input_types.html#truefalse>'
                         '`__): Description'])
        self.assertEqual(repr(out), repr(expected_rst))

    def test_freestyle_string_spec(self):
        spec = {
            "name": "Bar",
            "about": "Description",
            "type": "freestyle_string"
        }
        out = spec_utils.describe_arg_from_spec(spec['name'], spec)
        expected_rst = (['**Bar** (`text <input_types.html#text>`__, '
                         '*required*): Description'])
        self.assertEqual(repr(out), repr(expected_rst))

    def test_option_string_spec_dictionary(self):
        spec = {
            "name": "Bar",
            "about": "Description",
            "type": "option_string",
            "options": {
                "option_a": {
                    "display_name": "A"
                },
                "Option_b": {
                    "description": "do something"
                },
                "option_c": {
                    "display_name": "c",
                    "description": "do something else"
                }
            }
        }
        # expect that option case is ignored
        # otherwise, c would sort before A
        out = spec_utils.describe_arg_from_spec(spec['name'], spec)
        expected_rst = ([
            '**Bar** (`option <input_types.html#option>`__, *required*): Description',
            '\tOptions:',
            '\t- A',
            '\t- c: do something else',
            '\t- Option_b: do something'
        ])
        self.assertEqual(repr(out), repr(expected_rst))

    def test_option_string_spec_list(self):
        spec = {
            "name": "Bar",
            "about": "Description",
            "type": "option_string",
            "options": ["option_a", "Option_b"]
        }
        out = spec_utils.describe_arg_from_spec(spec['name'], spec)
        expected_rst = ([
            '**Bar** (`option <input_types.html#option>`__, *required*): Description',
            '\tOptions: option_a, Option_b'
        ])
        self.assertEqual(repr(out), repr(expected_rst))

    def test_raster_spec(self):
        spec = {
            "type": "raster",
            "bands": {1: {"type": "integer"}},
            "about": "Description",
            "name": "Bar"
        }
        out = spec_utils.describe_arg_from_spec(spec['name'], spec)
        expected_rst = ([
            '**Bar** (`raster <input_types.html#raster>`__, *required*): Description'
        ])
        self.assertEqual(repr(out), repr(expected_rst))

        spec = {
            "type": "raster",
            "bands": {1: {
                "type": "number",
                "units": u.millimeter/u.year
            }},
            "about": "Description",
            "name": "Bar"
        }
        out = spec_utils.describe_arg_from_spec(spec['name'], spec)
        expected_rst = ([
            '**Bar** (`raster <input_types.html#raster>`__, units: **mm/year**, *required*): Description'
        ])
        self.assertEqual(repr(out), repr(expected_rst))

    def test_vector_spec(self):
        spec = {
            "type": "vector",
            "fields": {},
            "geometries": {"LINESTRING"},
            "about": "Description",
            "name": "Bar"
        }
        out = spec_utils.describe_arg_from_spec(spec['name'], spec)
        expected_rst = ([
            '**Bar** (`vector <input_types.html#vector>`__, linestring, *required*): Description'
        ])
        self.assertEqual(repr(out), repr(expected_rst))

        spec = {
            "type": "vector",
            "fields": {
                "id": {
                    "type": "integer",
                    "about": "Unique identifier for each feature"
                },
                "precipitation": {
                    "type": "number",
                    "units": u.millimeter/u.year,
                    "about": "Average annual precipitation over the area"
                }
            },
            "geometries": {"POLYGON", "MULTIPOLYGON"},
            "about": "Description",
            "name": "Bar"
        }
        out = spec_utils.describe_arg_from_spec(spec['name'], spec)
        expected_rst = ([
            '**Bar** (`vector <input_types.html#vector>`__, polygon/multipolygon, *required*): Description',
        ])
        self.assertEqual(repr(out), repr(expected_rst))

    def test_csv_spec(self):
        spec = {
            "type": "csv",
            "about": "Description.",
            "name": "Bar"
        }
        out = spec_utils.describe_arg_from_spec(spec['name'], spec)
        expected_rst = ([
            '**Bar** (`CSV <input_types.html#csv>`__, *required*): Description. '
            'Please see the sample data table for details on the format.'
        ])
        self.assertEqual(repr(out), repr(expected_rst))

        # Test every type that can be nested in a CSV column:
        # number, ratio, percent, code,
        spec = {
            "type": "csv",
            "about": "Description",
            "name": "Bar",
            "columns": {
                "b": {"type": "ratio", "about": "description"}
            }
        }
        out = spec_utils.describe_arg_from_spec(spec['name'], spec)
        expected_rst = ([
            '**Bar** (`CSV <input_types.html#csv>`__, *required*): Description'
        ])
        self.assertEqual(repr(out), repr(expected_rst))

    def test_directory_spec(self):
        self.maxDiff = None
        spec = {
            "type": "directory",
            "about": "Description",
            "name": "Bar",
            "contents": {}
        }
        out = spec_utils.describe_arg_from_spec(spec['name'], spec)
        expected_rst = ([
            '**Bar** (`directory <input_types.html#directory>`__, *required*): Description'
        ])
        self.assertEqual(repr(out), repr(expected_rst))

    def test_multi_type_spec(self):
        spec = {
            "type": {"raster", "vector"},
            "about": "Description",
            "name": "Bar",
            "bands": {1: {"type": "integer"}},
            "geometries": {"POLYGON"},
            "fields": {}
        }
        out = spec_utils.describe_arg_from_spec(spec['name'], spec)
        expected_rst = ([
            '**Bar** (`raster <input_types.html#raster>`__ or `vector <input_types.html#vector>`__, *required*): Description'
        ])
        self.assertEqual(repr(out), repr(expected_rst))

    def test_real_model_spec(self):
        from natcap.invest import carbon
        out = spec_utils.describe_arg_from_name(
            'natcap.invest.carbon', 'carbon_pools_path', 'columns', 'lucode')
        expected_rst = (
            '.. _carbon-pools-path-columns-lucode:\n\n' +
            '**lucode** (`integer <input_types.html#integer>`__, *required*): ' +
            carbon.MODEL_SPEC['args']['carbon_pools_path']['columns']['lucode']['about']
        )
        self.assertEqual(repr(out), repr(expected_rst))


def _generate_files_from_spec(spec, workspace):
    """A utility function to support the metadata tests."""
    for filename, spec_data in spec.items():
        if 'type' in spec_data and spec_data['type'] == 'directory':
            os.mkdir(os.path.join(workspace, filename))
            _generate_files_from_spec(
                spec_data['contents'], os.path.join(workspace, filename))
        else:
            filepath = os.path.join(workspace, filename)
            ext = ".tif" if os.path.splitext(filepath)[-1] == '' else ''
            if 'bands' in spec_data:
                driver = gdal.GetDriverByName('GTIFF')
                n_bands = len(spec_data['bands'])
                raster = driver.Create(
                    filepath+ext, 2, 2, n_bands, gdal.GDT_Byte)
                for i in range(n_bands):
                    band = raster.GetRasterBand(i + 1)
                    band.SetNoDataValue(2)
            elif 'fields' in spec_data or 'columns' in spec_data:
                if 'geometries' in spec_data:
                    ext = ".gpkg" if os.path.splitext(filepath)[-1] == '' else ''
                    driver = gdal.GetDriverByName('GPKG')
                    target_vector = driver.CreateDataSource(filepath+ext)
                    layer_name = os.path.basename(os.path.splitext(filepath)[0])
                    target_layer = target_vector.CreateLayer(
                        layer_name, geom_type=ogr.wkbPolygon)
                    for field_name, field_data in spec_data['fields'].items():
                        target_layer.CreateField(ogr.FieldDefn(field_name, ogr.OFTInteger))
                else:
                    ext = ".csv" if os.path.splitext(filepath)[-1] == '' else ''
                    # Write a CSV if it has fields (or columns) but no geometry
                    if 'fields' in spec_data:
                        fields = spec_data['fields']
                    else:
                        fields = spec_data['columns']
                    with open(filepath+ext, 'w') as file:
                        file.write(f"{','.join([field for field in fields])}")
            else:
                # Such as taskgraph.db, just create the file.
                with open(filepath, 'w') as file:
                    pass


class TestMetadataFromSpec(unittest.TestCase):
    """Tests for metadata-generation functions."""

    def setUp(self):
        """Override setUp function to create temp workspace directory."""
        self.workspace_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Override tearDown function to remove temporary directory."""
        shutil.rmtree(self.workspace_dir)

    def test_write_metadata_for_outputs(self):
        """Test writing metadata for an invest output workspace."""

        # An example invest output spec
        output_spec = {
            'output': {
                "type": "directory",
                "contents": {
                    "urban_nature_supply_percapita.tif": {
                        "about": (
                            "The calculated supply per capita of urban nature."),
                        "bands": {1: {
                            "type": "number",
                            "units": u.m**2,
                        }}},
                    "admin_boundaries.gpkg": {
                        "about": (
                            "A copy of the user's administrative boundaries "
                            "vector with a single layer."),
                        "geometries": spec_utils.POLYGONS,
                        "fields": {
                            "SUP_DEMadm_cap": {
                                "type": "number",
                                "units": u.m**2/u.person,
                                "about": (
                                    "The average urban nature supply/demand ")
                            }
                        }
                    }
                },
            },
            'intermediate': {
                'type': 'directory',
                'contents': {
                    'taskgraph_cache': spec_utils.TASKGRAPH_DIR,
                }
            }
        }
        # Generate an output workspace with real files, without
        # running an invest model.
        _generate_files_from_spec(output_spec, self.workspace_dir)

        model_module = types.SimpleNamespace(
            __name__='urban_nature_access',
            execute=lambda: None,
            MODEL_SPEC={
                'model_id': 'urban_nature_access',
                'outputs': output_spec})

        args_dict = {'workspace_dir': self.workspace_dir}

        spec_utils.generate_metadata_for_outputs(model_module, args_dict)
        files, messages = geometamaker.validate_dir(
            self.workspace_dir, recursive=True)
        self.assertEqual(len(files), 2)
        self.assertFalse(any(messages))

        resource = geometamaker.describe(
            os.path.join(args_dict['workspace_dir'], 'output',
                         'urban_nature_supply_percapita.tif'))
        self.assertCountEqual(resource.get_keywords(),
                              [model_module.MODEL_SPEC['model_id'], 'InVEST'])

    def test_generate_metadata_for_datastack(self):
        """Test `generate_metadata_for_datastack`"""
        from natcap.invest import urban_cooling_model

        data_dir = os.path.join(self.workspace_dir, 'data')
        os.mkdir(data_dir)
        model_module = urban_cooling_model
        args_dict = {
             'workspace_dir': self.workspace_dir,
             'results_suffix': '_1',
             'lulc_raster_path': os.path.join(
                 data_dir, "lulc_raster_path.tif"),
             'ref_eto_raster_path': os.path.join(
                 data_dir, "ref_eto_raster_path.tif"),
             'aoi_vector_path': os.path.join(data_dir, "aoi_vector_path.gpkg"),
             'biophysical_table_path': os.path.join(
                 data_dir, "biophysical_table_path.csv"),
             't_ref': '27',
             'uhi_max': '5',
             't_air_average_radius': '500',
             'green_area_cooling_distance': '450',
             'cc_method': 'factors',
             'do_energy_valuation': False,
             'building_vector_path': "",
             'energy_consumption_table_path': '',
             'do_productivity_valuation': True,
             'avg_rel_humidity': '61.4',
             'cc_weight_shade': '',
             'cc_weight_albedo': '',
             'cc_weight_eti': ''}

        _generate_files_from_spec(model_module.MODEL_SPEC["args"], data_dir)

        param_set = {"args": args_dict}

        spec_utils.generate_metadata_for_datastack(model_module, args_dict,
                                                   param_set, data_dir)

        files, messages = geometamaker.validate_dir(data_dir, recursive=True)
        self.assertEqual(len(files), 4)
        self.assertFalse(any(messages))

        resource = geometamaker.describe(
            os.path.join(data_dir, args_dict['lulc_raster_path']))
        self.assertCountEqual(resource.get_keywords(),
                              [model_module.MODEL_SPEC['model_id'], 'InVEST'])
