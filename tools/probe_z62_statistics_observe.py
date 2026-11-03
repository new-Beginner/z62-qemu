"""Native checks that diagnostics observe controls without changing the model."""
import argparse
from contextlib import contextmanager, nullcontext
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import probe_z62_continuous_stats as stats
from z62_statistics_engine_snapshot import parse_control_trace, collect


@contextmanager
def session(binary, observe=False):
    original = stats.raw.host.configure_command
    def configure(command, *args, **kwargs):
        result = original(command, *args, **kwargs)
        if observe:
            result += ['-global', 'nikon-z72-boot-config.z62-statistics-observe=on']
        return result
    with patch.object(stats.raw.host, 'configure_command', configure), stats.session(binary) as s:
        yield s


def trace(s, path=None):
    return parse_control_trace(json.loads(s.get('statistics-control-trace', path or s.master)))


def exercise(s):
    # Characterize the OLD model, including its suspected +14 stop behavior.
    # This probe must stay the same if observation is enabled or disabled.
    s.write(0x20068010, 0x10)
    s.write(0x20068008, 0x10)
    assert s.get('statistics-model-started', s.master) is True
    assert s.get('continuous-enabled', stats.INPUT) is True
    s.write(0x20068014, 0x10)
    assert s.get('statistics-model-started', s.master) is False
    s.write(0x20068010, 0x10)
    assert s.get('statistics-model-enable', s.master) is False
    assert s.get('continuous-enabled', stats.INPUT) is False
    s.write(0x20068008, 0x10)
    s.write(0x20068100, 8)
    stats.configure(s); stats.source(s); stats.frame(s)
    return {'frames': stats.get(s, 'frames'), 'bytes': stats.get(s, 'bytes'),
            'reason': stats.get(s, 'reason'), 'enabled': s.get('continuous-enabled', stats.INPUT)}


def check(binary):
    result = {}
    with session(binary) as s:
        assert s.get('z62-statistics-observe', s.master) is False
        baseline = exercise(s)
        assert baseline['frames'] == 1 and baseline['bytes'] == 26240
        assert trace(s) == [] and s.get('statistics-control-count', s.master) == 0
        result['default_off_no_records'] = True
    with session(binary, True) as s:
        assert exercise(s) == baseline
        rows = trace(s)
        assert [int(r['address'], 16) for r in rows[:6]] == [
            0x20068010, 0x20068008, 0x20068014, 0x20068010, 0x20068008, 0x20068100]
        assert rows[2]['started_before'] and not rows[2]['started_after']
        assert rows[3]['mask_after'] == '0x00000010' and not rows[3]['model_enable']
        assert all(not r['pc_valid'] and r['cpu'] == -1 for r in rows)
        assert s.get('statistics-commit-pulses', s.master) == 1
        assert trace(s, s.slave) == []
        assert s.get('statistics-model-support', s.slave) is False
        sampled = collect(SimpleNamespace(io=nullcontext(), qmp=SimpleNamespace(command=s.query)), {})
        assert sampled['known'], sampled
        assert sampled['engines']['master']['controls']['0x20068010'] == 0x10
        assert sampled['engines']['slave']['controls']['0x20068010'] == 0
        for prop, value in (('statistics-control-count', 0), ('statistics-model-started', True),
                            ('statistics-control-trace', '[]')):
            error = s.query('qom-set', {'path': s.master, 'property': prop, 'value': value}, error=True)
            assert error['class'] == 'GenericError', error
        before = s.get('statistics-control-count', s.master)
        for i in range(300):
            s.write(0x20068000, i)
        rows = trace(s)
        assert len(rows) == 256 and rows[-1]['sequence'] == before+300
        assert rows[0]['sequence'] == before+45
        for address in (0x20068004, 0x2006800c, 0x20068018):
            s.write(address, 0)
        assert {int(r['address'], 16) for r in trace(s)[-3:]} == {0x20068004, 0x2006800c, 0x20068018}
        s.reset()
        assert trace(s) == [] and s.get('statistics-control-count', s.master) == 0
        assert s.get('statistics-model-started', s.master) is False
        result.update(observation_does_not_change_statistics=True, bounded_ring_keeps_sequence=True,
                      qtest_has_no_fake_cpu_pc=True, read_only_properties=True, reset_clears_diagnostics=True,
                      slave_is_separate=True, old_clear_alias_behavior_preserved=True, baseline=baseline)
        result['native_two_cpu_snapshot_known'] = True
    return {'schema': 1, 'completed': True, 'checks': result, 'camera_accessed': False,
            'guest_firmware_executed': False, 'physical_register_semantics_verified': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists(): raise FileExistsError('Existing evidence is immutable')
    try:
        record = check(args.qemu.resolve())
    except Exception as exc:
        record = {'schema': 1, 'completed': False, 'failure': {'type': type(exc).__name__, 'message': str(exc)}}
    with args.output.open('x', encoding='utf-8') as handle: json.dump(record, handle, indent=2)
    print(json.dumps(record), flush=True)
    raise SystemExit(0 if record['completed'] else 1)
