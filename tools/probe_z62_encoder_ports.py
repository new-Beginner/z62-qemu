"""Resolve actual controller GPIO MMIO/QOM bindings without running firmware."""
import argparse
import json
from pathlib import Path
import shutil
import tempfile

from probe_z62_transaction import session
from run_z62_capture_contacts import DEFAULT_QEMU, verify_build
from z62_encoder_input import discover_gpio_ports
from export_z62_body_contract import original, ROOT


def run(output):
    build = verify_build(DEFAULT_QEMU)
    record = {'schema': 1, 'completed': False, 'firmware_executed': False,
              'qemu_sha256': build['binary_sha256']}
    with output.open('x', encoding='utf-8') as handle:
        try:
            _, controller_sha = original('controller')
            record['controller_sha256'] = controller_sha
            # The dual board only instantiates its MCU when a controller image
            # is specified. Keep CPUs paused; this is topology, not execution.
            with tempfile.TemporaryDirectory(prefix='z62-encoder-ports-') as folder:
                staged = Path(folder) / 'controller.bin'
                if not str(staged).isascii() or ',' in str(staged):
                    raise ValueError('Native QEMU needs an ASCII controller path')
                shutil.copyfile(ROOT / 'artifacts/z62-reference-1.70/controller.bin', staged)
                machine = 'nikon-z62-dual-lab,controller-firmware=' + str(staged)
                with session(DEFAULT_QEMU, enabled=False, dma=False, intercept=None, machine=machine) as native:
                    record['ports'] = discover_gpio_ports(native.query)
            record['completed'] = True
        except Exception as exc:
            record['failure'] = {'type': type(exc).__name__, 'message': str(exc)}
        finally:
            json.dump(record, handle, indent=2)
    print(json.dumps(record, indent=2))
    return record['completed']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    raise SystemExit(0 if run(parser.parse_args().output) else 1)
