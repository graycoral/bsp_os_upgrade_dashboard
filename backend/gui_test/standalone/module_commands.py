"""Publish the company module inventory to an already-running full Monitor."""
import json

from ..core.integration import CONTRACT_VERSION
from ..core.models import TestError
from .bsp_plugin_client import BspPluginClient
from .plugin_parser import module_parser
from .plugin_settings_file import strict_json


def execute_modules(argv, *, home, port, managed_status):
    parser = module_parser()
    args = parser.parse_args(argv)
    if args.operation == 'publish':
        if args.expected_version < 0:
            parser.error('--expected-version must be nonnegative')
        modules = strict_json(args.file.read_bytes())
        if not isinstance(modules, list):
            raise ValueError('Module source must be a JSON array')
    if args.runtime_id is not None or args.package_version is not None:
        if not (port and args.runtime_id and args.package_version):
            parser.error('Supply --monitor-port, --runtime-id and --package-version together')
        endpoint = f'http://127.0.0.1:{port}'
        pins = {'runtime_id': args.runtime_id, 'package_version': args.package_version}
    else:
        status = managed_status()
        if status.get('state') != 'READY' or status.get('deployment', {}).get('state') in {'UPDATE_REQUIRED', 'UNVERIFIED'}:
            raise ValueError('A matching running full Agent Monitor is required for modules')
        endpoint = status['url']
        if port and endpoint != f'http://127.0.0.1:{port}':
            raise ValueError('Configured Monitor uses another port')
        pins = {key: status['health'][key] for key in ('runtime_id', 'package_version')}
    client = BspPluginClient(endpoint, expected_identity=pins, log_dir=home / 'plugin-logs')
    try:
        health = client.request('GET', '/api/v1/health')
        if (health.get('integration_contract_version') != CONTRACT_VERSION
                or any(health.get(key) != value for key, value in pins.items())):
            raise TestError('Full Monitor identity does not match the supplied pins', 'SERVICE_IDENTITY_MISMATCH', 409)
        if not {'plugin-module-catalog-v1', 'bsp-control-v1'}.issubset(health.get('capabilities', [])):
            raise ValueError('Full Monitor module catalog capability is required')
        result = client.module_catalog() if args.operation == 'list' else client.publish_modules(
            modules, expected_version=args.expected_version)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        return 0
    except TestError as exc:
        if exc.code == 'VERSION_CONFLICT':
            raise TestError('HTTP 409. Run modules list and compare the current version before publishing.',
                            exc.code, 409) from None
        raise
    finally:
        client.client.close()
