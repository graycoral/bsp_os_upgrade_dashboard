type Data = Record<string, any>;
const phases: Record<string, string> = {
  DISPATCHING: 'Windows 실행 요청', PREPARING: '이미지·TC 준비', ENTERING_LKSHELL: 'lkshell 진입',
  ENTERING_FASTBOOT: 'fastboot 진입', FLASHING: '이미지 퓨징', WAITING_BOOT: '부팅 대기',
  TESTING: 'TC 실행', COMPLETED: '실행 완료', FAILED: '실행 실패', UNKNOWN: '연결·장비 상태 확인 필요',
};

export function HardwareStatus({ stage }: { stage: Data }) {
  const auto = stage.automation;
  if (!auto) return stage.automation_blocked ? <p role="status">자동 퓨징 대기: {stage.automation_blocked}</p> : null;
  const report = auto.report || {};
  const tests: Data[] = report.tests || [];
  const flashes: Data[] = report.flashes || [];
  return <section className="hardware-status" aria-label="자동 퓨징 및 테스트">
    <p role="status"><strong>{phases[auto.phase] || auto.phase}</strong> · TC {tests.filter(t => ['PASS', 'FAIL'].includes(t.state)).length}/{auto.payload.tests.length}개 완료</p>
    {stage.result?.cases && <p>{Object.entries(stage.result.cases).map(([name, state]) => `${name}: ${state}`).join(' · ')}</p>}
    <details><summary>퓨징·TC 결과 및 로그</summary>
      {flashes.map(f => <div key={f.board.board_id}><strong>{f.board.board_id} · {f.success ? '퓨징 완료' : '퓨징 실패'} · {f.boot_ready ? '부팅 준비 확인' : '부팅 미확인'}</strong><pre>{f.result.stdout}{'\n'}{f.result.stderr}</pre></div>)}
      {tests.map(t => <div key={t.tc_id}><strong>{t.tc_id} · {t.state}</strong><pre>{t.stdout}{'\n'}{t.stderr}</pre></div>)}
      {(report.events || []).map((event: Data, i: number) => <p key={i}>{phases[event.phase] || event.phase}: {event.message}</p>)}
      {report.reason && <p>{report.reason}</p>}
      <small>실행 ID: {auto.payload.id}</small>
    </details>
  </section>;
}
