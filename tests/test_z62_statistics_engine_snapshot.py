"""Do not confuse a missing slave read with a cold device or use CPU0 twice."""
from contextlib import nullcontext
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))


class FakeQmp:
    def __init__(self):
        self.cpu_reads=[];self.bad_slave=False;self.bad_bool=False;self.duplicate=False

    def command(self,name,arguments=None):
        if name=='query-cpus-fast': return [{'cpu-index':i} for i in range(4)]
        if name=='qom-list': return [{'name':n,'type':'child<nikon-z72-boot-config>'} for n in ('m','s')]
        if name=='qom-get':
            prop=arguments['property'];path=arguments['path'];master=path.endswith('/m')
            if prop=='master-role': return master or self.duplicate
            if prop in ('statistics-model-started','statistics-model-enable','statistics-model-support',
                        'continuous-enabled','continuous-active','continuous-rearm','continuous-clock-level',
                        'functional-continuous-stats','functional-finite-stats','functional-raw'):
                return 0 if self.bad_bool and prop=='continuous-enabled' else master
            if prop=='statistics-control-trace': return '[]'
            if prop.endswith('reason'): return 'success'
            return 7 if master or 'master-input' in path else 3
        if name=='human-monitor-command':
            cpu=arguments['cpu-index'];self.cpu_reads.append(cpu)
            if cpu==2 and self.bad_slave: return 'Cannot access memory'
            count=int(arguments['command-line'].split('/')[1].split('w')[0])
            return '0x20068000: '+' '.join(hex(100+cpu) for _ in range(count))
        raise AssertionError('Unexpected command '+name)


class StatisticsEngineSnapshotTests(unittest.TestCase):
    def api(self):
        try:
            import z62_statistics_engine_snapshot as module
        except ImportError as exc:
            self.fail('Two-engine statistics observation is missing: '+str(exc))
        return module

    def machine(self):
        return type('Machine',(),{'io':nullcontext(),'qmp':FakeQmp()})()

    def test_reads_master_cpu0_and_slave_cpu2_as_separate_views(self):
        machine=self.machine();row=self.api().collect(machine,{})
        self.assertTrue(row['known'])
        self.assertEqual(row['engines']['master']['controls']['0x20068010'],100)
        self.assertEqual(row['engines']['slave']['controls']['0x20068010'],102)
        self.assertEqual(set(machine.qmp.cpu_reads),{0,2})

    def test_failed_slave_read_preserves_known_master_and_explicit_unknown(self):
        machine=self.machine();machine.qmp.bad_slave=True
        row=self.api().collect(machine,{})
        self.assertFalse(row['known']);self.assertTrue(row['engines']['master']['known'])
        self.assertFalse(row['engines']['slave']['known'])
        self.assertIsNone(row['engines']['slave']['controls'].get('0x20068010'))
        self.assertTrue(row['engines']['slave']['errors'])

    def test_wrong_bool_type_is_not_silently_coerced(self):
        machine=self.machine();machine.qmp.bad_bool=True
        row=self.api().collect(machine,{})
        self.assertFalse(row['known'])
        self.assertIsNone(row['engines']['master']['input']['continuous-enabled'])

    def test_duplicate_roles_are_rejected_before_any_mmio_read(self):
        machine=self.machine();machine.qmp.duplicate=True
        with self.assertRaises(ValueError): self.api().collect(machine,{})
        self.assertEqual(machine.qmp.cpu_reads,[])

    def test_control_ring_parser_retains_gaps_and_rejects_bad_records(self):
        module=self.api()
        base={'sequence':1,'address':'0x20068014','value':'0x10','mask_after':'0x200',
              'started_before':True,'started_after':False,'model_supported':True,'model_enable':False,
              'pc_valid':True,'pc':'0x1020ab00','cpu':0,'qemu_virtual_ns':1000,'frame_count':10}
        rows=module.parse_control_trace([base,{**base,'sequence':3}])
        self.assertEqual([r['sequence'] for r in rows],[1,3])
        with self.assertRaises(ValueError): module.parse_control_trace([{**base,'started_after':0}])
        with self.assertRaises(ValueError): module.parse_control_trace([{**base,'address':'0xf8f01000'}])
