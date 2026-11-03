"""Handle RSP console packets without accepting arbitrary monitor commands."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import probe_z62_input_counters as probe


class CounterTests(unittest.TestCase):
    def test_multiple_console_packets_complete_before_value_is_used(self):
        class Remote:
            def __init__(self): self.replies = iter(['O'+b'23\r\n'.hex(), 'OK'])
            def command(self, packet):
                self.command_text = bytes.fromhex(packet.split(',')[1]).decode()
                return 'O'+b'1'.hex()
            def receive(self): return next(self.replies)
        remote = Remote(); result = probe.read_property(remote, 'continuous-frames')
        self.assertEqual(result['value'], 123)
        self.assertEqual(remote.command_text, 'qom-get /machine/master-input continuous-frames')

    def test_mutating_monitor_text_is_rejected_before_network(self):
        with self.assertRaises(ValueError): probe.read_property(None, 'continuous-frames; quit')


if __name__ == '__main__': unittest.main()
