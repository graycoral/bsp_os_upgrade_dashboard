import React, {Profiler, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {DiagramTab} from './workflow_diagram/web/DiagramTab';
import {toDiagramModel} from './workflow_diagram/adapters/dashboard';
import {jobFixture, moduleFixture, scaleFixture, stage} from './fixtures';

const w = window as any;
function Host() {
  const [snapshot, setSnapshot] = useState(jobFixture([moduleFixture('A'), moduleFixture('B', 'main', {name: '같은 이름'})]));
  const [contextKey, setContext] = useState('demo:job-A');
  const [active, setActive] = useState(true);
  const [acon, setAcon] = useState<any[]>([]);
  const [observation, setObservation] = useState<any>({status: 'ready', receivedAt: Date.now(), receivedMonoMs: performance.now(), staleAfterMs: 5400, needsConfirmation: false, detail: ''});
  const [hostile, setHostile] = useState(false);
  w.wdTest = {setSnapshot, setContext, setActive, setAcon, setHostile, setObservation,
    fixtures: {jobFixture, moduleFixture, scaleFixture, stage}, snapshot,
    refresh: () => setObservation((old: any) => ({...old, status: 'ready', receivedMonoMs: performance.now(), receivedAt: Date.now(), needsConfirmation: false})),
  };
  const start = performance.now(); const model = toDiagramModel(snapshot, {contextKey});
  w.wdMetrics ||= {renders: 0, renderMs: [], adapterMs: []}; w.wdMetrics.adapterMs.push(performance.now() - start);
  return <>
    {hostile && <style>{'button{font-size:48px;line-height:4;padding:50px}p{margin:100px}svg{width:999px;height:999px}*{box-sizing:content-box}'}</style>}
    <Profiler id="diagram" onRender={(_id, _phase, duration) => {w.wdMetrics.renders++; w.wdMetrics.renderMs.push(duration);}}>
      <DiagramTab model={model} observation={observation} active={active} acon={acon}/>
    </Profiler>
    <div id="outside-css-sentinel"><button>Company button</button></div>
  </>;
}
createRoot(document.getElementById('root')!).render(<Host/>);
