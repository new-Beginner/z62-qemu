"""Capture the complete unittest discovery result without shell redirection."""
import argparse
from contextlib import redirect_stderr,redirect_stdout
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]


def check(output):
    output=Path(output).absolute()
    if not output.resolve().is_relative_to(ROOT): raise ValueError('Keep regression evidence inside workspace')
    if output.exists() or output.with_suffix('.log').exists(): raise FileExistsError('Use new evidence paths')
    output.parent.mkdir(parents=True,exist_ok=True)
    started=time.monotonic()
    with output.with_suffix('.log').open('x',encoding='utf-8',newline='\n') as log:
        with redirect_stdout(log),redirect_stderr(log):
            suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'))
            tested=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    result={'schema':1,'scope':'complete current tests/test*.py unittest discovery',
        'completed':tested.wasSuccessful() and not tested.skipped,'tests':tested.testsRun,
        'failures':len(tested.failures),'errors':len(tested.errors),'skipped':len(tested.skipped),
        'failure_names':[str(test) for test,_ in tested.failures],
        'error_names':[str(test) for test,_ in tested.errors],
        'skip_details':[(str(test),reason) for test,reason in tested.skipped],
        'elapsed_seconds':time.monotonic()-started,'python':sys.executable,
        'rawpy_available':importlib.util.find_spec('rawpy') is not None,
        'log_sha256':hashlib.sha256(output.with_suffix('.log').read_bytes()).hexdigest(),
        'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'camera_access_authorized':False,'test_root':str(ROOT/'tests')}
    with output.open('x',encoding='utf-8',newline='\n') as handle: json.dump(result,handle,ensure_ascii=False,indent=2)
    print(json.dumps(result,ensure_ascii=False),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--output',type=Path,required=True)
    result=check(parser.parse_args().output)
    raise SystemExit(0 if result['completed'] else 1)
