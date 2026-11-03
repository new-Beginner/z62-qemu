from pathlib import Path
from types import SimpleNamespace
import sys
import threading
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import trace_z62_grid_geometry_lifecycle as subject


class Queries:
    def __init__(self, bad=None):
        self.properties = []
        self.bad = bad

    def command(self, name, arguments):
        if name == 'qom-list':
            return [{'name':'device[0]','type':'child<nikon-z72-boot-config>'}]
        prop = arguments['property']
        self.properties.append(prop)
        if prop == 'raw-reason':
            raise RuntimeError('Property does not exist in r48/r52')
        if prop == self.bad:
            return 'malformed counter'
        if prop in ('master-role','z62-raw-stream','raw-stream-active'):
            return True
        if prop == 'raw-last-reason':
            return 'stride'
        if prop.endswith('-reason'):
            return 'success'
        return 0


class ProducerPropertyNames(unittest.TestCase):
    def test_missing_old_name_is_mapped_to_the_actual_status_value(self):
        original_queries = Queries()
        machine = SimpleNamespace(io=threading.RLock(),qmp=original_queries)
        old = subject.ORIGINAL_COUNTERS(machine,{})
        self.assertFalse(old['known'])
        self.assertIsNone(old['input']['raw-reason'])
        queries = Queries()
        row = subject.collect_counters(SimpleNamespace(io=threading.RLock(),qmp=queries),{})
        self.assertTrue(row['known'])
        self.assertEqual(row['input']['raw-reason'],'stride')
        self.assertIn('raw-last-reason',queries.properties)
        self.assertNotIn('raw-reason',queries.properties)
        self.assertEqual(row['property_source_aliases']['input.raw-reason'],
                         '/machine/master-input.raw-last-reason')

    def test_bad_numeric_status_remains_unknown(self):
        queries = Queries('raw-stream-frames')
        row = subject.collect_counters(SimpleNamespace(io=threading.RLock(),qmp=queries),{})
        self.assertFalse(row['known'])
        self.assertIsNone(row['stream']['raw-stream-frames'])
        self.assertTrue(row['errors'])


if __name__ == '__main__':
    unittest.main()
