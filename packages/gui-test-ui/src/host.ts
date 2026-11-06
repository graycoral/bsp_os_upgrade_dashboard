export type ExecutionView = 'default' | 'live';

/** All paths are relative to the GUI Test API selected by the host. */
export interface GuiTestHost {
  request(path:string, method?:string, data?:unknown, signal?:AbortSignal):Promise<any>;
  download(path:string):string;
  readonly mode:ExecutionView;
  applyMode(mode:ExecutionView):void;
  storage:{getItem(key:string):string|null;setItem(key:string,value:string):void;removeItem(key:string):void};
  /** Enables Run creation/control and identifies leases owned by this host.
   * Omission makes Runs observation-only; source/settings editing may remain
   * separately permitted. The server always enforces control authority. */
  ownsSession?(controller:string):boolean;
}

/** Dashboard projection: the shared UI does not depend on BSP stage snapshots. */
export interface GuiTestModuleContext {
  job_id:string;
  plan_version:number;
  fingerprint:string;
  paused?:boolean;
  session_status?:string;
  modules:Array<{
    id:string; name:string; status?:string; attempt_id?:string;
    automatic:boolean; request_hash?:string; frozen_run_id?:string;
    source_revision?:string; automation_blocked?:boolean; blocked_reason?:string;
  }>;
}

/** Explicitly create at app startup (or lazily on first mount), never on import. */
export function createBrowserGuiTestHost():GuiTestHost {
  const storage:GuiTestHost['storage']={
    getItem(key){try{return localStorage.getItem(key)}catch{return null}},
    setItem(key,value){try{localStorage.setItem(key,value)}catch{/* Optional preference. */}},
    removeItem(key){try{localStorage.removeItem(key)}catch{/* Optional preference. */}},
  };
  const requested=new URLSearchParams(location.search).get('guiExecution');
  const mode:ExecutionView=requested?requested==='live'?'live':'default':storage.getItem('gui-execution-view')==='live'?'live':'default';
  // The URL commits the preference only after the destination page loads.
  if(requested==='live'||requested==='default')storage.setItem('gui-execution-view',mode);
  const base='/api/v1/gui-test'+(mode==='live'?'/live':'');
  let session:string|undefined;
  function sessionId(){
    if(session)return session;
    try{session=sessionStorage.getItem('gui-session')||crypto.randomUUID();sessionStorage.setItem('gui-session',session)}
    catch{session=crypto.randomUUID()}
    return session;
  }
  return {
    mode,storage,
    async request(path,method='GET',data,signal){
      const response=await fetch(base+path,{method,signal,headers:{'Content-Type':'application/json','X-BSP-Client':'dashboard','X-GUI-Session':sessionId(),'Idempotency-Key':crypto.randomUUID()},...(data===undefined?{}:{body:JSON.stringify(data)})});
      if(!response.ok){const error=await response.json();throw new Error(error.message||JSON.stringify(error.detail))}
      return response.json();
    },
    download:path=>base+path,
    ownsSession:controller=>controller===sessionId(),
    applyMode(next){const url=new URL(location.href);url.searchParams.set('guiExecution',next);location.assign(url.href)},
  };
}

let defaultHost:GuiTestHost|undefined;
export function getDefaultGuiTestHost(){return defaultHost??=createBrowserGuiTestHost()}
