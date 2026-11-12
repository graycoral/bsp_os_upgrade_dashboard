import {useEffect,useRef,useState} from 'react';
type Data=Record<string,any>;
/** Read-only discovery polls independently of TC catalog/source materialization. */
export default function ConnectorStatus({request,onStatus,active=true}:{request:(path:string)=>Promise<Data>;onStatus:(value:Data)=>void;active?:boolean}) {
  const [value,setValue]=useState<Data>({boards:[],fresh:false}),[error,setError]=useState('');
  const callback=useRef(onStatus);callback.current=onStatus;
  useEffect(()=>{if(!active)return;let alive=true,pending=false;
    async function refresh(){if(pending)return;pending=true;try{const result=await request('/connector/inventory');if(alive){setValue(result);setError('');callback.current(result);}}
      catch(e){if(alive){setError((e as Error).message);setValue(old=>({...old,fresh:false}));}}finally{pending=false;}}
    void refresh();const timer=setInterval(refresh,2000);return()=>{alive=false;clearInterval(timer);};
  },[request,active]);
  const labels:Record<string,string>={CONNECTED:'연결',RUNNING:'시험 중',UNKNOWN:'확인 필요',RESERVED:'예약',DISCONNECTED:'미연결',ERROR:'오류'};
  return <section className="gt-connector-status" aria-label="보드 커넥터 현황"><strong>보드 커넥터</strong>
    <span>등록 {value.boards.length}대 · 감지 {value.boards.filter((b:Data)=>b.detected).length}대</span>
    {!value.boards.length&&<small>커넥터에서 연결하면 보드가 자동으로 표시됩니다.</small>}
    {value.boards.map((board:Data)=><span key={(value.runner_id||'')+':'+board.board_id} className={'gt-connector-board '+(!value.fresh?'stale':board.state.toLowerCase())}>
      <i aria-hidden="true"/> {board.name||board.board_id} · {board.com} · {!value.fresh?'확인 필요 · 오래된 정보':labels[board.state]||'확인 필요'}{board.blocked_reason==='HOST_BUSY'?' · 다른 보드 작업 대기':''}
    </span>)}
    {error&&<small role="status">상태를 새로 확인하지 못했습니다.</small>}
  </section>;
}
