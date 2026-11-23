"""Read-only path projection; never used to resolve or launch an execution."""
import re
from urllib.parse import urlsplit, urlunsplit
from .logs import redact


def display_path(value):
    text = str(value or '')
    if '://' in text:
        try:
            url = urlsplit(text)
            text = urlunsplit((url.scheme, url.netloc.rsplit('@', 1)[-1], url.path, '', ''))
        except ValueError:
            return '[경로 확인 불가]'
    return redact(re.sub(r'[\x00-\x1f\x7f]', ' ', text))[:4096]


def server_paths(manager, runner_id):
    active = manager.sources.state()['active']
    result = {'selected_tc_source': display_path(active.get('location')), 'run': None}
    runs = []
    for run in manager.store.all():
        integration = run.get('integration') or {}
        pinned = run.get('runner_id_snapshot') or integration.get('config', {}).get('runner_id')
        if not run.get('simulation') and pinned == runner_id:
            runs.append(run)
    if not runs:
        return result
    priority = {'RUNNING': 3, 'UNKNOWN': 3, 'PAUSED': 2, 'QUEUED': 1}
    run = max(runs, key=lambda r: (priority.get(r['state'], 0), r.get('created_at') or '', r['id']))
    integration = run.get('integration') or {}
    batch = integration.get('batch') or {}
    result['run'] = {
        'id': run['id'], 'state': run['state'],
        'historical': run['state'] in {'COMPLETED', 'CANCELLED'},
        'installer': display_path(integration.get('request', {}).get('installer_path')),
        'tc_source': display_path(integration.get('config', {}).get('tc_root') or (run.get('source_snapshot') or {}).get('location')),
        'batch_id': batch.get('batch_id'),
        'execution_ids': [(a.get('process_ref') or '').removeprefix('windows:') for a in run.get('attempts', [])[-32:]],
    }
    return result


def path_text(status):
    data = status.get('server_paths')
    if data is None:
        return '서버 경로 미수신 · 연결 후 확인할 수 있습니다.'
    lines = []
    if status.get('state') != 'CONNECTED' or status.get('fresh') is False:
        lines.append('과거 수신 정보 · 현재 연결 상태 확인 필요')
    lines.append('Linux 선택 TC 소스: ' + (display_path(data.get('selected_tc_source')) or '미설정'))
    run = data.get('run')
    if not run:
        return '\n'.join(lines + ['플래싱·TC 실행: 요청 전'])
    lines += [('이전 실행' if run.get('historical') else '현재 실행') + ': ' + display_path(run['id']) + ' · ' + display_path(run['state']),
              'Linux 설치 BAT: ' + (display_path(run.get('installer')) or '이 실행에 없음'),
              'Linux 실행 TC 소스: ' + (display_path(run.get('tc_source')) or '기록 없음')]
    records = [r for r in status.get('execution_paths', []) if r.get('id') in run.get('execution_ids', []) or
               (run.get('batch_id') and r.get('batch_id') == run['batch_id'])]
    image = next((r for r in records if r.get('kind') == 'batch-prepare' and r.get('working_directory')), None)
    tc = next((r for r in records if r.get('kind') != 'batch-prepare' and r.get('working_directory')), None)
    missing = '경로 기록 없음' if run.get('historical') else '준비 전 또는 경로 미수신'
    lines += ['Windows 이미지 작업 폴더: ' + (display_path(image['working_directory']) if image else missing),
              'Windows TC 작업 폴더: ' + (display_path(tc['working_directory']) if tc else missing)]
    if tc:
        lines.append('TC 실행 ID: ' + display_path(tc['id']))
    lines.append('Windows 경로는 마지막 수신 기록이며 파일의 현재 존재 여부는 확인하지 않습니다.')
    return '\n'.join(lines)
