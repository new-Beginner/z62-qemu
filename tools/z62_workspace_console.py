"""Adapt only a newly generated host's filesystem paths to workspace storage."""
from pathlib import Path


def apply_console(source):
    source=Path(source).absolute()
    if source.name!='source' or not source.parent.name.startswith(('z62-reference-','z72-reference-','z72-latest-')):
        raise ValueError('A fresh private source copy is required')
    from z62_workspace_paths import ROOT
    if not source.resolve().is_relative_to(ROOT):
        raise ValueError('Runtime source must be physically in the workspace')
    for path in (source/'tools').glob('*.py'):
        if path.name=='z62_workspace_paths.py':
            continue
        text=path.read_text(encoding='utf-8')
        anchor='from pathlib import Path\n'
        if anchor in text:
            path.write_text(text.replace(anchor,'from tools.z62_workspace_paths import WorkspacePath as Path\n'),
                            encoding='utf-8',newline='\n')
    (source/'tools/z62_workspace_paths.py').write_bytes(Path(__file__).with_name('z62_workspace_paths.py').read_bytes())
