"""Prepare whole installer/TC trees without changing the user's active TC source."""
from pathlib import Path
import os
from .models import TestError
from .discovery import discover
from ..execution.source import read_source
from ..execution.source_snapshots import manifest, publish, file_manifest


def prepare_inputs(request, config, destination):
    from ..execution.installer_snapshots import freeze_installer
    root = Path(destination)
    installer = freeze_installer(request['installer_path'], config['installer_roots'], root / 'installers',
                                 max_total=config.get('max_bundle_bytes', 64 * 1024**3))
    source = Path(config['tc_root'])
    if not source.is_absolute() or any(p.is_symlink() or (getattr(p.lstat(), 'st_file_attributes', 0) & 0x400) for p in [source, *source.parents]):
        raise TestError('TC root must not contain links', 'SOURCE_UNSAFE', 422)
    files = read_source(source)
    value = manifest(files, {'kind': 'integration-folder', 'location': str(source)}, config.get('metadata', {}))
    # A second full read catches replacements during acquisition. Producer folders
    # must already be published and immutable before the request is submitted.
    if file_manifest(read_source(source)) != value['files']:
        raise TestError('TC source changed while preparing', 'SOURCE_CHANGED')
    directory = root / 'tc' / value['snapshot_id']
    publish(files, value, directory)
    catalog = discover(directory, config.get('metadata', {})) | {'revision': value['source_revision'], 'branch': 'integration'}
    return {'catalog': catalog, 'source_snapshot': {k: value[k] for k in ('snapshot_id', 'source_revision')},
            'source_directory': str(directory), 'installer_snapshot': installer,
            'installer_directory': str(root / 'installers' / installer['snapshot_id'])}
