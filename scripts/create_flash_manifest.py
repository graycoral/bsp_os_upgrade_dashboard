"""Create a build artifact manifest; never execute scripts or contact a board."""
import argparse
import hashlib
import json
from pathlib import Path

from backend.gui_test.execution.flashing import contained, validate_manifest


def create_manifest(root, batch, output):
    root = Path(root).resolve(strict=True)
    output = Path(output).resolve()
    if output.is_relative_to(root):
        raise ValueError('Manifest output must be outside the image folder')
    files = {}
    for path in sorted(root.rglob('*')):
        name = path.relative_to(root).as_posix()
        checked = contained(root, name)
        if checked.is_file():
            with checked.open('rb') as stream:
                files[name] = hashlib.file_digest(stream, 'sha256').hexdigest()
    manifest = {'schema_version': 1, 'batch': batch, 'files': files}
    validate_manifest(manifest)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation protects previously published build identities.
    with output.open('x', encoding='utf-8') as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
    parser.add_argument('--batch', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    create_manifest(args.root, args.batch, args.output)


if __name__ == '__main__':
    main()
