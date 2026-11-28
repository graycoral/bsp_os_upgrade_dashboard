"""Validate the filesystem boundary for a Linux SSH streamlocal forward."""

import os
from pathlib import Path
import stat

import httpx


def shared_socket_path(value, owner_uid):
    path = Path(value)
    if not path.is_absolute() or type(owner_uid) is not int or owner_uid < 0:
        raise ValueError('Shared SSH socket requires an absolute path and trusted owner UID')
    return path


def validate_shared_socket(value, owner_uid):
    path = shared_socket_path(value, owner_uid)
    try:
        if path.resolve(strict=True) != path:
            raise ValueError('Shared SSH socket path cannot use symlinks')
        for parent in path.parents:
            info = parent.lstat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid not in {0, owner_uid} or info.st_mode & 0o022:
                raise ValueError('Shared SSH socket ancestors must be protected from other local writers')
        info = path.lstat()
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != owner_uid or info.st_mode & 0o007:
            raise ValueError('Shared SSH socket must belong to the approved UID with owner/group access only')
    except OSError:
        raise ValueError('Shared SSH socket is unavailable') from None
    return path


def shared_uds_transport(value, owner_uid):
    path = validate_shared_socket(value, owner_uid)
    return httpx.HTTPTransport(uds=os.fspath(path), trust_env=False)
