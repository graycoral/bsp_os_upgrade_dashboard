import {useState} from 'react';
import {applyExecutionView, executionView, type ExecutionView} from './executionView';
import './execution-view-settings.css';

export default function ExecutionViewSettings({className='', disabled=false}:{className?:string;disabled?:boolean}) {
  const [selected,setSelected]=useState<ExecutionView>(executionView);
  return <section className={'execution-view-settings '+className} aria-label="Test 현황 보기 모드">
    <h2>Test 현황 보기 모드</h2>
    <div className="execution-view-settings-controls">
      <label>보기 모드<select aria-label="Test 현황 보기 모드" value={selected} disabled={disabled} onChange={e=>setSelected(e.target.value as ExecutionView)}><option value="default">기본 모드</option><option value="live">실제 연결 모드</option></select></label>
      <button type="button" disabled={disabled||selected===executionView} onClick={()=>applyExecutionView(selected)}>보기 모드 적용</button>
    </div>
  </section>;
}
