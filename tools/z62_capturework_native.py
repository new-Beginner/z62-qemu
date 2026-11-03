"""Build/run the standalone capture pixel core inside this workspace only."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def ascii_root():
    alias=Path('Q:/')
    if alias.is_dir() and alias.samefile(ROOT): return alias
    if str(ROOT).isascii(): return ROOT
    raise ValueError('Use the verified workspace ASCII alias or an ASCII checkout')


def compile_probe(output):
    root=ascii_root(); output=Path(output).absolute()
    if not output.resolve().is_relative_to(ROOT): raise ValueError('Native output must stay inside workspace')
    lock=json.loads((ROOT/'.runtime/relocated-toolchain-manifest-r73.json').read_text(encoding='utf-8'))
    tool_root=Path(lock['root']).resolve()
    if not tool_root.is_relative_to(ROOT): raise ValueError('Use the relocated workspace compiler')
    compiler=root/tool_root.relative_to(ROOT)/'ucrt64/bin/gcc.exe'
    if not compiler.is_file(): raise FileNotFoundError('Workspace UCRT64 GCC is required')
    output.mkdir(parents=True,exist_ok=True)
    executable=output/'capturework-pixels-probe.exe'
    environment=dict(os.environ,TEMP=str(root/'.runtime/tmp'),TMP=str(root/'.runtime/tmp'),
        TMPDIR=str(root/'.runtime/tmp'),PATH=str(compiler.parent)+os.pathsep+os.environ.get('PATH',''))
    command=[str(compiler),'-std=c11','-O2','-Wall','-Wextra','-Werror','-pedantic',
        '-I',str(root/'qemu/z62-capturework'),str(root/'tests/native/z62_capturework_pixels_probe.c'),'-o',str(executable)]
    completed=subprocess.run(command,cwd=str(output),env=environment,capture_output=True,text=True,encoding='utf-8',timeout=60)
    if completed.returncode: raise RuntimeError(completed.stderr)
    return executable,environment


def run(executable,environment,case,*args):
    result=subprocess.run([str(executable),case,*map(str,args)],env=environment,
        capture_output=True,text=True,encoding='utf-8',timeout=60)
    if result.returncode: raise RuntimeError(result.stderr or result.stdout)
    return json.loads(result.stdout)


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
