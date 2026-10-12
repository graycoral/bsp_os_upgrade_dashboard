export type Data = Record<string, any>;
export async function api(path: string, options: RequestInit = {}) {
  const headers = new Headers({'Content-Type':'application/json', 'X-BSP-Client':'dashboard', ...options.headers});
  let pendingSlot: string | null = null;
  if (headers.has('Idempotency-Key')) {
    const bytes = new TextEncoder().encode(path + String(options.body));
    const hash = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))).map(x=>x.toString(16).padStart(2,'0')).join('');
    pendingSlot = 'bsp-pending-' + hash;
    const previous = localStorage.getItem(pendingSlot);
    if (previous) headers.set('Idempotency-Key', previous);
    else localStorage.setItem(pendingSlot, headers.get('Idempotency-Key')!);
  }
  const response = await fetch('/api/v1' + path, { ...options, headers });
  if (pendingSlot && response.status < 500) localStorage.removeItem(pendingSlot);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const e = new Error(data.message || (Array.isArray(data.detail) ? data.detail.map((x: Data) => x.msg).join(' · ') : data.detail) || '요청을 처리하지 못했습니다.') as Error & {status?: number};
    e.status = response.status;
    (e as Error & {code?:string}).code = data.code;
    throw e;
  }
  return data;
}
export const stages = ['analysis','design','code','build','verification','device_test'];
export const labels: Record<string,string> = {analysis:'요구사항 분석',design:'설계',code:'코드 구현',build:'빌드',verification:'검증',device_test:'장비 테스트'};
export const statusNames: Record<string,string> = {PENDING:'대기',RUNNING:'진행 중',WAITING_INPUT:'수동 시험 대기',SUCCEEDED:'완료',FAILED:'실패',UNKNOWN:'상태 확인 필요',CANCEL_REQUESTED:'취소 중',CANCELLED:'취소됨',NOT_APPLICABLE:'해당 없음'};
