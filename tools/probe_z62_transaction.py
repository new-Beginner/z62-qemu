# SPDX-License-Identifier: GPL-2.0-or-later
"""Native Windows r5 no-firmware DMA -> sensor IRQ92 transaction checks."""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch
import probe_z62_functional_raw as raw
import reference_updates
import z62_transaction_device as transaction

MASTER = '/machine/master-sensor'
SLAVE = '/machine/slave-sensor'
COUNTERS = ('raw-source-events', 'raw-completions', 'raw-ignored', 'raw-coalesced')
REASON = 'raw-completion-last-reason'
CONFIG, MODE, STATUS, MASK = 0x20065400, 0x20065504, 0x20065508, 0x2006550C


class Session(raw.Session):
    def sensor(self, prop, path=MASTER):
        # QMP errors propagate: absent/unknown diagnostics must never become 0.
        return self.get(prop, path)

    def status(self):
        return int(self.access(f'readl {STATUS:#x}').split()[1], 16)

    def arm(self, mask=0xF3, mode=0x8000, config=0x10011):
        for addr, value in ((CONFIG, config), (MODE, mode), (MASK, mask)):
            self.write(addr, value)

    def counts(self, expected, path=MASTER):
        actual = tuple(self.sensor(name, path) for name in COUNTERS)
        assert actual == expected, (actual, expected)
        assert actual[0] == sum(actual[1:]), actual

    def irq92(self):
        # Drain asynchronous GPIO notifications before examining the history.
        self.status()
        return [item for item in self.irqs if item.endswith(' 3')]

    def reset(self):
        self.query('system_reset')
        deadline = time.monotonic() + 5
        while self.sensor(REASON) != 'reset' and time.monotonic() < deadline:
            time.sleep(.01)
        self.status()
        self.irqs.clear()
        self.counts((0, 0, 0, 0))
        assert self.status() == 0


def close_owned_session(process, session, streams, sockets, qmp_ready):
    """Best effort QMP shutdown, bounded fallback on this Popen object only."""
    notes = []
    try:
        if process.poll() is None:
            if qmp_ready:
                try:
                    session.query('quit')
                except (OSError, ValueError, AssertionError) as exc:
                    notes.append('QMP quit: ' + repr(exc))
            else:
                process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
        if process.poll() is None:
            raise RuntimeError('Owned QEMU did not exit')
    finally:
        for handle in (*streams, *sockets):
            try:
                handle.close()
            except OSError as exc:
                notes.append('Close: ' + repr(exc))
    return notes


@contextmanager
def session(binary, enabled=True, dma=True, intercept=MASTER, machine='nikon-z62-dual-lab',
            intercept_name='sysbus-irq'):
    with tempfile.TemporaryDirectory(dir=os.environ.get('PI_SCRATCH_DIR'), prefix='z62-transaction-',
                                     ignore_cleanup_errors=True) as folder:
        qmp_port, wire_port = raw.free_port(), raw.free_port()
        command = [str(binary.resolve()), '-M', machine, '-smp', '4,maxcpus=5',
                   '-display', 'none', '-serial', 'none', '-monitor', 'none', '-nic', 'none', '-S',
                   '-qmp', f'tcp:127.0.0.1:{qmp_port},server=on,wait=off',
                   '-qtest', f'tcp:127.0.0.1:{wire_port},server=on,wait=off',
                   '-qtest-log', 'NUL' if os.name == 'nt' else '/dev/null']
        if dma:
            command += ['-global', 'nikon-z72-input-config.functional-raw=on']
        if enabled:
            command += ['-global', 'nikon-z62-sensor-config.functional-raw-completion=on']
        with (Path(folder) / 'qemu.log').open('wb') as log:
            process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=log)
        sockets, streams = [], []
        s = Session()
        qmp_ready = False
        try:
            sock = raw.connect(qmp_port, process)
            sockets.append(sock)
            sock.settimeout(60)
            s.qmp = sock.makefile('rwb')
            streams.append(s.qmp)
            json.loads(s.qmp.readline())
            s.query('qmp_capabilities')
            qmp_ready = True
            sock = raw.connect(wire_port, process)
            sockets.append(sock)
            sock.settimeout(60)
            s.wire = sock.makefile('rwb')
            streams.append(s.wire)
            s.command, s.irqs = command, []
            if intercept:
                s.access(f'irq_intercept_out {intercept} {intercept_name}')
            assert not s.query('query-status')['running']
            yield s
        except Exception:
            print((Path(folder) / 'qemu.log').read_text(errors='replace'))
            raise
        finally:
            primary_failure = sys.exc_info()[0] is not None
            try:
                notes = close_owned_session(process, s, streams, sockets, qmp_ready)
                for note in notes:
                    print('Cleanup note: ' + note, file=sys.stderr)
            except Exception as cleanup_error:
                if not primary_failure:
                    raise
                print('Cleanup failure (original exception preserved): ' + repr(cleanup_error), file=sys.stderr)


def check_off(binary):
    with session(binary, enabled=False) as s:
        assert s.sensor('functional-raw-completion') is False
        s.configure()
        s.arm()
        s.fill()
        s.submit()
        s.verify_slots(raw.pattern(), guards=True)
        s.counts((1, 0, 1, 0))
        assert s.sensor(REASON) == 'disabled'
        assert s.get('raw-accepted') == 1 and s.status() == 0 and not s.irq92()
        return {'default_off_real_dma_no_irq': True, 'command': s.command}


def check_no_dma(binary):
    with session(binary, dma=False) as s:
        s.configure()
        s.arm()
        s.fill()
        s.submit()
        s.verify_slots(b'\xa5' * raw.SIZE)
        s.counts((0, 0, 0, 0))
        assert s.status() == 0 and not s.irq92()
        return {'completion_enabled_but_dma_off_no_source': True}


def check_transactions(binary):
    expected = raw.pattern()
    with session(binary) as s:
        assert s.sensor('laboratory-frame-completion') is False
        s.configure()
        s.arm()
        s.fill()
        # Configuration and legacy frame input must not create transaction success.
        s.access(f'set_irq_in {MASTER} frame-end 0 1')
        s.access(f'set_irq_in {MASTER} frame-end 0 0')
        time.sleep(.05)
        s.counts((0, 0, 0, 0))
        assert not s.irq92() and s.status() == 0
        rejects = [(0x20069A08, 2273), (0x20069A5C, 0),
                   (0x20069A5C, raw.SLOTS[0] + 4), (0x20069A5C, 0x20065508)]
        for addr, value in rejects:
            s.configure()
            s.write(addr, value)
            s.submit()
            s.verify_slots(b'\xa5' * raw.SIZE, guards=True)
            s.counts((0, 0, 0, 0))
            assert not s.irq92() and s.status() == 0
        s.configure()
        # Successful DMA with wrong mode, then wrong config, then unarmed consumer.
        for n, settings in enumerate(({'mode': 0}, {'config': 0x10010}, {'mask': 0xF1}), 1):
            s.arm(**settings)
            s.submit()
            s.verify_slots(expected, guards=True)
            s.counts((n, 0, n, 0))
            assert s.sensor(REASON) == ('unarmed-mask' if n == 3 else 'mode-mismatch')
            assert not s.irq92() and s.status() == 0
        # Arming afterwards must not replay an ignored event.
        s.arm()
        assert not s.irq92() and s.status() == 0
        s.fill()
        s.submit()
        s.verify_slots(expected, guards=True)
        s.counts((4, 1, 3, 0))
        assert s.get('raw-accepted') == 4 and s.get('raw-bytes') == 16 * raw.SIZE
        assert s.status() == 2 and s.irq92() == ['IRQ raise 3']
        # A second complete DMA while status is pending coalesces, no new edge.
        s.fill()
        s.submit()
        s.verify_slots(expected, guards=True)
        s.counts((5, 1, 3, 1))
        assert s.sensor(REASON) == 'coalesced'
        assert s.irq92() == ['IRQ raise 3']
        s.write(STATUS, 2)
        assert s.status() == 0 and s.irq92() == ['IRQ raise 3', 'IRQ lower 3']
        s.submit()
        s.verify_slots(expected, guards=True)
        s.counts((6, 2, 3, 1))
        assert s.status() == 2
        assert s.irq92() == ['IRQ raise 3', 'IRQ lower 3', 'IRQ raise 3']
        s.counts((0, 0, 0, 0), SLAVE)
        assert s.sensor('init-completions') == s.sensor('frame-completions') == 0
        for name in (*COUNTERS, REASON):
            s.query('qom-set', {'path': MASTER, 'property': name,
                              'value': 'reset' if name == REASON else 0}, error=True)
        s.query('qom-get', {'path': MASTER, 'property': 'does-not-exist'}, error=True)
        history = list(s.irq92())
        s.reset()
        assert s.sensor(REASON) == 'reset'
        s.configure()
        s.arm()
        s.submit()
        s.counts((1, 1, 0, 0))
        assert s.irq92() == ['IRQ raise 3']
        return {'real_dma_success_irq92_edges': history, 'four_slots_full_readback': True,
                'bytes_per_slot': raw.SIZE, 'pattern_sha256': hashlib.sha256(expected).hexdigest(),
                'bad_descriptors_no_side_effects': len(rejects), 'mode_and_mask_gates': True,
                'no_replay_on_arm': True, 'pending_coalesced': True, 'w1c_rearm': True,
                'reset': True, 'qom_read_only_unknown_is_error': True,
                'legacy_init_and_frame_counters_unchanged': True, 'command': s.command}


def check_edge_input(binary):
    # GPIO injection is ONLY an input edge unit test, NOT evidence of DMA.
    with session(binary) as s:
        s.arm()
        for _ in range(2):
            s.access(f'set_irq_in {MASTER} raw-dma-complete 0 1')
        s.counts((1, 1, 0, 0))
        assert s.irq92() == ['IRQ raise 3']
        s.write(STATUS, 2)
        s.access(f'set_irq_in {MASTER} raw-dma-complete 0 1')
        s.counts((1, 1, 0, 0))
        assert s.status() == 0
        assert s.irq92() == ['IRQ raise 3', 'IRQ lower 3']
        s.reset()  # clear latched-high input too
        s.arm()
        s.access(f'set_irq_in {MASTER} raw-dma-complete 0 1')
        s.counts((1, 1, 0, 0))
        assert s.irq92() == ['IRQ raise 3']
        s.access(f'set_irq_in {MASTER} raw-dma-complete 0 0')
        s.access(f'set_irq_in {MASTER} raw-dma-complete 0 1')
        s.counts((2, 1, 0, 1))
        assert s.irq92() == ['IRQ raise 3']
        return {'gpio_unit_test_only': True, 'repeated_high_no_duplicate': True,
                'reset_clears_edge': True, 'pending_level_no_false_edge': True}


def check_isolation(binary):
    with session(binary, intercept=SLAVE) as s:
        # Arm both consumers so the slave IRQ test cannot pass merely masked.
        registers = {**raw.descriptors(), CONFIG: 0x10011, MODE: 0x8000, MASK: 0xF3}
        with patch.object(raw, 'descriptors', return_value=registers):
            raw.configure_slave(s)  # paused CPU2 MMIO writes AND readback
        s.configure()
        s.arm()
        s.fill()
        s.access(f'set_irq_in {raw.SLAVE} raw-submit 0 1')
        s.access(f'set_irq_in {raw.SLAVE} raw-submit 0 0')
        assert s.get('raw-last-reason', raw.SLAVE) == 'not-writable-ram'
        s.counts((0, 0, 0, 0), SLAVE)
        s.counts((0, 0, 0, 0))
        s.verify_slots(b'\xa5' * raw.SIZE)
        s.submit()
        s.verify_slots(raw.pattern(), guards=True)
        s.counts((1, 1, 0, 0))
        s.counts((0, 0, 0, 0), SLAVE)
        assert not s.irq92()  # intercepted SLAVE IRQ92 stays low
        return {'slave_invalid_dma_no_source': True, 'master_success_no_slave_irq': True,
                'both_consumers_armed': True,
                'slave_setup': 'paused CPU2 GDB MMIO; no guest execution', 'command': s.command}


def check_conflict(binary):
    command = [str(binary.resolve()), '-M', 'nikon-z62-dual-lab', '-smp', '4,maxcpus=5',
               '-display', 'none', '-serial', 'none', '-monitor', 'none', '-nic', 'none', '-S',
               '-global', 'nikon-z62-sensor-config.functional-raw-completion=on',
               '-global', 'nikon-z62-sensor-config.laboratory-frame-completion=on']
    result = subprocess.run(command, capture_output=True, timeout=20)
    message = result.stderr.decode(errors='replace')
    assert result.returncode != 0 and 'conflicts with laboratory-frame-completion' in message
    return {'dual_sources_rejected': True, 'stderr': message, 'command': command}


def check_z72(binary):
    with session(binary, enabled=False, dma=False, intercept=None, machine='nikon-z72-dual-lab') as s:
        entries = s.query('qom-list', {'path': '/machine/unattached'})
        paths = ['/machine/unattached/' + entry['name'] for entry in entries
                 if entry['type'] == 'child<nikon-z72-input-config>']
        assert len(paths) == 2
        for path in paths:
            assert not s.get('functional-raw', path)
            assert s.get('raw-accepted', path) == s.get('raw-rejected', path) == 0
        s.write(0x20068104, 1)
        for path in paths:
            assert s.get('raw-accepted', path) == s.get('raw-rejected', path) == 0
        return {'z72_default_no_raw_activity': True, 'command': s.command}


def r4_regression(binary):
    # Reuse unchanged r4 checks but substitute this probe's QMP-quit lifecycle.
    # Completion stays default off, and its source output is intercepted as r4 expects.
    def factory(binary, enabled):
        return session(binary, enabled=False, dma=enabled, intercept=raw.MASTER,
                       intercept_name='raw-complete')
    with patch.object(raw, 'session', factory):
        result = raw.run(binary)
    # r4's static capability label does not describe the composite r5 binary.
    result.pop('sensor_irq_completion_added')
    result['transaction_completion_enabled'] = False
    result['scope'] = 'unchanged r4 checks on r5, transaction property default off'
    return result


def run(binary):
    manifest = json.loads((binary.parent.parent / 'transaction-build-manifest.json').read_text(encoding='utf-8'))
    digest = hashlib.sha256(binary.read_bytes()).hexdigest()
    assert manifest['transaction_device'] == transaction.identity()
    assert manifest['binary_sha256'] == digest
    reference_updates.verify_binary(binary)
    return {'schema': 1, 'version': transaction.VERSION, 'binary_sha256': digest,
            'firmware_loaded': False, 'guest_executed': False,
            'checks': [check_off(binary), check_no_dma(binary), check_transactions(binary),
                       check_edge_input(binary), check_isolation(binary), check_conflict(binary), check_z72(binary)],
            'r4_regression': r4_regression(binary)}


def publish_exclusive(output, result):
    """Publish fully serialized evidence atomically, without replacing any path."""
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(result, indent=2) + '\n').encode('utf-8')
    fd, pending = tempfile.mkstemp(prefix=output.name + '.', suffix='.tmp', dir=output.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        # Hard-link publication is exclusive and same-filesystem. Unlike replace,
        # it also rejects a competing writer that appeared after the precheck.
        os.link(pending, output)
    finally:
        Path(pending).unlink(missing_ok=True)


def run_to_file(binary, output):
    if output.exists() or output.is_symlink():
        raise FileExistsError('Refusing to overwrite qtest evidence: ' + str(output))
    try:
        result = run(binary)
    except Exception as exc:
        publish_exclusive(output, {'completed': False, 'version': transaction.VERSION,
                                   'failure': {'type': type(exc).__name__, 'message': str(exc)}})
        raise
    publish_exclusive(output, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run_to_file(args.qemu, args.output)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
