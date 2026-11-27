"""Fixed read-only command for the SSH account when Agent Monitor is offline."""

# Runs with Linux system Python, without importing or provisioning the plugin.
# Only selected display fields leave the server. Open an existing store without
# initializing defaults, creating a lock file, migrating or writing any rows.
READ_SETTINGS = """
import hashlib
import json
from pathlib import Path
import sqlite3
import sys


def read_settings():
    home = Path.home() / '.local/share/bsp-agent-monitor'
    location = home / 'runtime-location.json'
    runtime = home / 'runtime'
    if location.is_symlink():
        return {'issue': 'location'}
    if location.exists():
        with location.open('rb') as f:
            saved = json.loads(f.read(16385))
        path = saved.get('path')
        if not isinstance(path, str) or not Path(path).is_absolute():
            return {'issue': 'location'}
        runtime = Path(path)
    db = runtime / 'shared-settings.db'
    if any(p.is_symlink() for p in (db, *db.parents)):
        return {'issue': 'location'}
    if not db.is_file():
        return {'issue': 'missing'}
    with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True, timeout=1) as c:
        c.execute('PRAGMA query_only=ON')
        c.execute('PRAGMA trusted_schema=OFF')
        c.execute('BEGIN')
        if c.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone() != ('1',):
            return {'issue': 'format'}
        prefs = json.loads(c.execute('SELECT data_json FROM connector_preferences WHERE id=1').fetchone()[0])
        runner, port = sys.argv[1:]
        pinned = prefs.get('expected_runner_id')
        if (pinned and pinned != runner) or (not pinned and prefs.get('preferred_connector_port') != int(port)):
            return {'issue': 'target'}
        cfg = json.loads(c.execute('SELECT data_json FROM shared_settings WHERE id=1').fetchone()[0])
        limits = json.loads(c.execute('SELECT data_json FROM timeouts WHERE id=1').fetchone()[0])
    integration = {k: cfg.get(k, '') for k in ('tc_root', 'installer_path', 'flash_profile')}
    for key in ('installer_roots', 'global_defaults'):
        integration[key] = cfg.get(key, [])
    preview = {'integration': integration, 'timeouts': {'default_seconds': limits.get('default_seconds')}}
    # A display revision, scoped to the fields actually returned; never used for writes.
    preview['revision'] = hashlib.sha256(json.dumps(preview, sort_keys=True).encode()).hexdigest()
    return preview


try:
    print(json.dumps(read_settings()))
except (OSError, ValueError, KeyError, IndexError, TypeError, AttributeError, sqlite3.Error):
    print(json.dumps({'issue': 'unreadable'}))
"""

ISSUES = {
    'missing': 'SSH 계정의 ~/.local/share/bsp-agent-monitor에 연결된 런타임에서 shared-settings.db를 찾지 못했습니다.',
    'location': 'SSH 계정의 runtime-location.json 또는 런타임 경로를 확인하세요.',
    'target': 'Linux 설정 DB에 지정된 커넥터와 현재 보드 커넥터가 다릅니다.',
    'format': 'Linux 공통 설정 DB 버전을 확인하세요.',
    'unreadable': 'SSH 계정으로 Linux 공통 설정 DB를 읽을 수 없습니다.',
}
