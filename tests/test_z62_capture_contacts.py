"""Fail-closed host fanout checks; electrical semantics use native QEMU tests."""
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from trace_z62_capture_contact_route import fanout


class FakeMachine:
    def __init__(self):
        self.writes = []
        self.corrupt = False
        self.ambiguous = False
        self.qmp = SimpleNamespace(command=self.query)

    def _words(self, address, count):
        i = (address - 0xC18037DC) // 56
        row = [0] * 14
        row[0], row[1], row[2] = 0x58+i, 11+i, 0x04282014
        row[8], row[9], row[10], row[12], row[13] = 1, 4+i, 69+i, 0x1022A92B, 2
        if self.corrupt:
            row[12] ^= 2
        return row

    def query(self, command, arguments):
        if command == 'qom-list':
            return [{'name': n, 'type': 'child<nikon-z72-boot-config>'} for n in ('master', 'slave')]
        if arguments['property'] == 'master-role':
            return self.ambiguous or arguments['path'].endswith('/master')
        return 0

    def _qtest(self, command):
        self.writes.append(command)


class CaptureContactFanoutTests(unittest.TestCase):
    def test_contact_polarity_and_routing(self):
        machine = FakeMachine()
        for pin, level in ((1, 0), (13, 0), (13, 1), (1, 1)):
            fanout(machine, pin, level)
        self.assertEqual(machine.writes, [
            'set_irq_in /machine/unattached/master capture-contact 0 1',
            'set_irq_in /machine/unattached/master capture-contact 1 1',
            'set_irq_in /machine/unattached/master capture-contact 1 0',
            'set_irq_in /machine/unattached/master capture-contact 0 0'])

    def test_binding_mismatch_prevents_contact(self):
        machine = FakeMachine()
        machine.corrupt = True
        with self.assertRaises(ValueError):
            fanout(machine, 1, 0)
        self.assertFalse(machine.writes)

    def test_ambiguous_engine_prevents_contact(self):
        machine = FakeMachine()
        machine.ambiguous = True
        with self.assertRaises(ValueError):
            fanout(machine, 1, 0)
        self.assertFalse(machine.writes)

    def test_unknown_contact_prevents_write(self):
        for pin, level in ((14, 0), (1, 2), ('1', 0)):
            machine = FakeMachine()
            with self.subTest(pin=pin, level=level), self.assertRaises(ValueError):
                fanout(machine, pin, level)
            self.assertFalse(machine.writes)


if __name__ == '__main__':
    unittest.main()
