"""Verify a company delivery using a trusted checkout and an independent SSH signer list."""
import argparse
import hashlib
from pathlib import Path
import json
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps/agent-monitor'))
from plugin_delivery import verify_evidence


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    for name in ('prior', 'current', 'evidence'):
        parser.add_argument(name, type=Path)
    parser.add_argument('--allowed-signers', type=Path, required=True)
    parser.add_argument('--identity', required=True)
    parser.add_argument('--signature', type=Path, required=True)
    args = parser.parse_args()
    receipt = (args.evidence / 'RELEASE_EVIDENCE.json').read_bytes()
    subprocess.run(['ssh-keygen', '-Y', 'verify', '-f', str(args.allowed_signers), '-I', args.identity,
                    '-n', 'bsp-plugin-release-v1', '-s', str(args.signature)], input=receipt, check=True,
                   stdout=subprocess.DEVNULL)
    result = verify_evidence(args.prior, args.current, args.evidence, hashlib.sha256(receipt).hexdigest())
    print(json.dumps(result | {'signer': args.identity}))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        sys.exit(f'Release verification failed: {exc}')
