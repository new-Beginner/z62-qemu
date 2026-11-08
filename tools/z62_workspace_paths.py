"""ASCII access paths whose physical data stays inside the selected workspace."""
import os
from pathlib import Path as NativePath

ROOT=NativePath(os.environ.get('Z62_PROJECT_ROOT',str(NativePath(__file__).resolve().parents[1]))).resolve()
ALIAS=NativePath(os.environ.get('Z62_PROJECT_DRIVE','Q:/'))
OLD_RUNTIME=NativePath('<USERPROFILE>/Documents/Z62-QEMU-runtime')
OLD_TEMP=NativePath('<USERPROFILE>/AppData/Local/Temp')
OLD_TOOLS=ROOT.parent/'z62-qemu-tools'


def ensure_alias():
    if not ALIAS.is_dir() or not ALIAS.samefile(ROOT):
        raise ValueError('The ASCII drive must point to this workspace')


def logical(path):
    path=NativePath(path)
    if not path.is_absolute():
        return path
    if path.is_relative_to(OLD_RUNTIME):
        path=ROOT/'.runtime/migrated/c-runtime'/path.relative_to(OLD_RUNTIME)
    elif path.is_relative_to(OLD_TOOLS):
        path=ROOT/'.runtime/tools'/path.relative_to(OLD_TOOLS)
    elif path.is_relative_to(OLD_TEMP):
        relative=path.relative_to(OLD_TEMP)
        if relative.parts and relative.parts[0].startswith('z62-'):
            path=ROOT/'.runtime/migrated/c-temp'/relative
    if path.is_relative_to(ROOT):
        ensure_alias()
        canonical=path.resolve()
        if not canonical.is_relative_to(ROOT):
            raise ValueError('Workspace path escaped through a link')
        return ALIAS/canonical.relative_to(ROOT)
    if path.drive.casefold()==ALIAS.drive.casefold():
        ensure_alias()
        if not path.resolve().is_relative_to(ROOT):
            raise ValueError('Alias path escaped the workspace')
    return path


def guard_write(path):
    canonical=NativePath(str(path)).absolute().resolve()
    if not canonical.is_relative_to(ROOT):
        raise ValueError('Project output must stay in the workspace: '+str(path))


class WorkspacePath(type(NativePath())):
    def __init__(self,*args):
        super().__init__(str(logical(NativePath(*args))))

    def resolve(self,strict=False):
        return type(self)(NativePath(str(self)).resolve(strict=strict))

    def absolute(self):
        return type(self)(NativePath(str(self)).absolute())

    def open(self,mode='r',*args,**kwargs):
        if any(flag in mode for flag in ('w','a','x','+')):
            guard_write(self)
        return super().open(mode,*args,**kwargs)

    def mkdir(self,*args,**kwargs):
        guard_write(self); return super().mkdir(*args,**kwargs)

    def unlink(self,*args,**kwargs):
        guard_write(self); return super().unlink(*args,**kwargs)

    def rmdir(self):
        guard_write(self); return super().rmdir()

    def rename(self,target):
        guard_write(self); target=type(self)(target); guard_write(target)
        return super().rename(target)

    def replace(self,target):
        guard_write(self); target=type(self)(target); guard_write(target)
        return super().replace(target)
