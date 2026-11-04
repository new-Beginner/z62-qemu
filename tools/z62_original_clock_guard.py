"""Wait for the original hardware clock setup; never substitute frequency/time."""
from contextlib import contextmanager
import time
from unittest.mock import patch
from record_z62_action_evidence import require


def wait_for_clock(machine,timeout=10):
    deadline=time.monotonic()+timeout;samples=[]
    while True:
        words=machine._words(0x04266008,3)
        require(len(words)==3 and all(type(v) is int and 0<=v<=0xffffffff for v in words),
            'Malformed original hardware clock read')
        samples.append(words)
        if words[2]>0:return samples
        if time.monotonic()>=deadline:raise TimeoutError('Original hardware clock never acquired a nonzero frequency')
        if machine.process.poll() is not None:raise RuntimeError('Original process ended before clock setup')
        time.sleep(.02)


@contextmanager
def qualified_snapshot(module):
    previous=module.snapshot;records=[]
    def snapshot(machine,layout):
        if not records:
            samples=wait_for_clock(machine);records.extend(samples)
        return previous(machine,layout)
    with patch.object(module,'snapshot',snapshot):yield records
