"""Server port selection shared by the Windows launcher and its local Manager."""
import argparse


def port_argument(value):
    try:
        port = int(value)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError('서버 포트는 1~65535 사이의 정수여야 합니다.') from None
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError('서버 포트는 1~65535 사이의 정수여야 합니다.')
    return port


def set_port(value, port):
    """Change only the endpoint; retain imported service identity and all boards."""
    import copy
    from ..core.connector_bootstrap import ConnectorBootstrap
    from ..core.models import TestError
    if type(port) is not int or not 1 <= port <= 65535:
        raise TestError('서버 포트는 1~65535 사이의 정수여야 합니다.', 'CONNECTOR_CONFIG', 422)
    value = copy.deepcopy(value)
    setup = value.setdefault('_setup', {})
    if not isinstance(setup, dict):
        raise TestError('연결 설정 형식을 확인하세요.', 'CONNECTOR_CONFIG', 422)
    if setup.get('connector_bootstrap') is not None:
        profile = ConnectorBootstrap.model_validate(setup['connector_bootstrap']).model_dump()
        profile['endpoint']['remote_dashboard_port'] = port
        setup['connector_bootstrap'] = profile
    setup['remote_dashboard_port'] = port
    return value


def save_server_port(manager, port):
    from ..core.models import TestError
    from ..core.connector_bootstrap import plain_path
    from ..execution.launch import LaunchLock, read_active
    from .automatic_serial import idle_records
    from scripts.setup_ports import PortsProfile
    from scripts.setup_runtime import save_json
    with manager.control_lock:
        value = set_port(manager.settings.read(), port)
        # The same explicit value is safe even while the current connection runs.
        if value == manager.settings.read():
            return {'server_port': port, 'changed': False}
        if (getattr(manager, 'mirror_applying', False) or
                manager.thread and manager.thread.is_alive() or
                read_active(manager.home / 'runtime') is not None):
            raise TestError('연결 종료 후 --server-port로 다시 실행하세요. 기존 설정은 유지됩니다.', 'CONNECTOR_BUSY', 409)
        try:
            with LaunchLock(manager.home / 'runtime' / 'setup-launch.lock'), LaunchLock(manager.home / 'runtime' / 'runner.lock'):
                with idle_records(manager.home):
                    try:
                        PortsProfile(manager.home / 'setup-ports.json').resolve({'remote_dashboard_port': port})
                    except ValueError as exc:
                        raise TestError('서버 포트와 커넥터 역방향 포트가 중복되거나 포트 설정이 올바르지 않습니다.', 'CONNECTOR_CONFIG', 422) from exc
                    # Initial setup can have no board/SSH fields yet. Avoid full
                    # Settings.save validation or changing the serial transport.
                    target = plain_path(manager.home / 'windows-runner.json')
                    save_json(target, value)
        except RuntimeError as exc:
            raise TestError('연결 준비 중입니다. 연결 종료 후 다시 실행하세요.', 'CONNECTOR_BUSY', 409) from exc
        return {'server_port': port, 'changed': True}
