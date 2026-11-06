import {createBrowserGuiTestHost,type GuiTestModuleContext} from '../../../packages/gui-test-ui/src';

export const guiTestHost=createBrowserGuiTestHost();

/** Keep Dashboard snapshot knowledge at the embedding boundary. */
export function toGuiTestModuleContext(job:Record<string,any>|null):GuiTestModuleContext|null {
  if(!job?.id)return null;
  return {
    job_id:job.id,plan_version:job.plan_version,fingerprint:job.fingerprint,
    paused:job.paused,session_status:job.session?.status,
    modules:(Array.isArray(job.modules)?job.modules:[]).map((module:Record<string,any>)=>{
      const stage=module.stages?.device_test;
      return {id:module.id,name:module.name,status:stage?.status,attempt_id:stage?.attempts?.at(-1)?.id,
        automatic:!!stage?.automation,request_hash:stage?.automation?.request_hash,
        frozen_run_id:stage?.automation?.payload?.id,source_revision:stage?.automation?.payload?.source_revision,
        automation_blocked:stage?.automation_blocked,blocked_reason:stage?.blocked_reason};
    }),
  };
}
