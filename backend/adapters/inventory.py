"""Read-only, streaming three-tree inventory. Limits bound preparation work, not policy."""
import hashlib
import os
import stat
from pathlib import Path, PurePosixPath

from backend.contracts import canonical_json, report_hash
from backend.domain.policy import Conflict

MAX_FILES = 250_000
MAX_TOTAL_BYTES = 1 << 40
VCS = {'.git', '.repo', '.hg', '.svn'}


def _identity(item):
    return (item.st_dev, item.st_ino, item.st_mode, item.st_size, item.st_mtime_ns, item.st_ctime_ns)


def _tree(root):
    entries, directories, stamps, total = {}, {}, {}, 0
    root = root.resolve(strict=True)
    def scan(folder):
        nonlocal total
        before = folder.stat()
        names = sorted(name for name in os.listdir(folder) if name not in VCS)
        directories[folder] = (_identity(before), names)
        for name in names:
            if name in VCS:
                continue
            path = folder / name
            before = path.lstat()
            relative = path.relative_to(root).as_posix()
            if stat.S_ISLNK(before.st_mode):
                target = os.readlink(path)
                if not path.resolve(strict=False).is_relative_to(root):
                    raise ValueError('Symlink escapes the input tree.')
                entry = {'kind': 'link', 'mode': stat.S_IMODE(before.st_mode), 'target': target,
                         'sha256': hashlib.sha256(os.fsencode(target)).hexdigest(), 'size': before.st_size}
            elif stat.S_ISDIR(before.st_mode):
                scan(path)
                continue
            elif stat.S_ISREG(before.st_mode):
                total += before.st_size
                if total > MAX_TOTAL_BYTES:
                    raise ValueError('Input tree byte limit exceeded.')
                with path.open('rb') as stream:
                    digest = hashlib.file_digest(stream, 'sha256').hexdigest()
                entry = {'kind': 'file', 'mode': stat.S_IMODE(before.st_mode), 'sha256': digest, 'size': before.st_size}
            else:
                raise ValueError('Unsupported input filesystem object.')
            if _identity(before) != _identity(path.lstat()):
                raise ValueError('Input changed during inventory.')
            entries[relative] = entry
            stamps[relative] = _identity(before)
            if len(entries) > MAX_FILES:
                raise ValueError('Input tree file limit exceeded.')
    scan(root)
    # Recheck all files AND directory membership, catching late additions/removals.
    for folder, (identity, names) in directories.items():
        if _identity(folder.stat()) != identity or sorted(name for name in os.listdir(folder) if name not in VCS) != names:
            raise ValueError('Input tree changed during inventory.')
    for relative, entry in entries.items():
        path = root / relative
        current = path.lstat()
        if _identity(current) != stamps[relative]:
            raise ValueError('Input changed during inventory.')
        if entry['kind'] == 'link':
            if not path.is_symlink() or os.readlink(path) != entry['target']:
                raise ValueError('Input link changed during inventory.')
        else:
            # Streaming second pass establishes a stable complete manifest, including
            # edits that preserve length and occur after the first per-file check.
            with path.open('rb') as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() != entry['sha256']:
                    raise ValueError('Input contents changed during inventory.')
        if _identity(path.lstat()) != stamps[relative]:
            raise ValueError('Input changed during the final inventory check.')
    for folder, (identity, names) in directories.items():
        if _identity(folder.stat()) != identity or sorted(name for name in os.listdir(folder) if name not in VCS) != names:
            raise ValueError('Input tree changed during the final inventory check.')
    return {'root': str(root), 'sha256': report_hash(entries), 'entries': entries}


def _module_keys(profile, path):
    found = []
    for module in profile.get('modules', []):
        for target in module.get('target_paths', []):
            cleaned = target.replace('\\', '/').rstrip('/')
            if cleaned.startswith('/') or '..' in PurePosixPath(cleaned).parts:
                raise ValueError('Module target paths must be relative input paths.')
            if path == cleaned or path.startswith(cleaned + '/'):
                found.append(module.get('stable_key') or module['name'])
                break
    return sorted(set(found))


def build_vendor_inventory(profile):
    """Compare old_base to vendor_tree; retain new_base identities for analysis.

    Empty module_keys means globally discoverable changes, never guessed attribution.
    """
    if profile.get('execution', 'demo') == 'demo':
        manifests = {name: {'root': 'simulation:' + name, 'sha256': report_hash({'simulation': name}), 'entries': {}}
                     for name in ('old_base', 'vendor_tree', 'new_base')}
        changes = []
        for index, module in enumerate(profile.get('modules', [])):
            key = module.get('stable_key') or module['name']
            path = f'simulation/module-{index}/vendor-change.txt'
            entry = {'kind': 'file', 'mode': 420, 'size': 0, 'sha256': report_hash({'simulation': key})}
            changes.append({'change_id': 'change-' + report_hash({'simulation': key, 'path': path}),
                            'path': path, 'kind': 'add', 'before': None, 'after': entry, 'new_base': None,
                            'module_keys': [key]})
        value = {'schema_version': 1, 'simulation': True, 'manifests': manifests, 'changes': changes}
        return value | {'sha256': report_hash(value)}
    try:
        manifests = {}
        for name in ('old_base', 'vendor_tree', 'new_base'):
            path = Path(profile.get(name, ''))
            if not profile.get(name) or not path.is_absolute() or not path.is_dir():
                raise ValueError('All three absolute input trees are required.')
            manifests[name] = _tree(path)
        old, vendor, new = (manifests[name]['entries'] for name in ('old_base', 'vendor_tree', 'new_base'))
        changes = []
        identities = {name: manifest['sha256'] for name, manifest in manifests.items()}
        for path in sorted(set(old) | set(vendor)):
            before, after = old.get(path), vendor.get(path)
            if before == after:
                continue
            kind = ('add' if before is None else 'delete' if after is None else
                    'link' if before['kind'] != after['kind'] or before.get('target') != after.get('target') else
                    'mode' if before['sha256'] == after['sha256'] else 'modify')
            identity = {'manifests': identities, 'path': path, 'before': before, 'after': after}
            changes.append({'change_id': 'change-' + report_hash(identity), 'path': path, 'kind': kind,
                            'before': before, 'after': after, 'new_base': new.get(path), 'module_keys': _module_keys(profile, path)})
        # Tree-to-tree drift is rejected rather than accepted as a mixed baseline.
        if any(_tree(Path(profile[name]))['sha256'] != item['sha256'] for name, item in manifests.items()):
            raise ValueError('Input tree changed while preparing the three-tree inventory.')
        value = {'schema_version': 1, 'simulation': False, 'manifests': manifests, 'changes': changes}
        return value | {'sha256': report_hash(value)}
    except (OSError, ValueError, RuntimeError):
        raise Conflict('Input inventory is unreadable, unstable, exceeds bounds, or contains an escaping link.', 'ENVIRONMENT', 422) from None
