/** Portable read-only diagram contract, version 1. No host/API types are required. */
export type DiagramTone = 'blue' | 'red' | 'gray' | 'green';
export type StageStatus = 'PENDING' | 'RUNNING' | 'DISPATCHING' | 'WAITING_INPUT' | 'SUCCEEDED' | 'FAILED' | 'UNKNOWN' | 'CANCEL_REQUESTED' | 'CANCELLED' | 'NOT_APPLICABLE';
export type ServerStageName = 'analysis' | 'design' | 'code' | 'build' | 'verification' | 'device_test';
export interface DiagramStagePart {
  id: ServerStageName;
  label: string;
  status: StageStatus;
  statusLabel: string;
  detail: string;
  complete: boolean;
  running: boolean;
  tone: DiagramTone;
}
export interface DiagramStage {
  id: 'analysis' | 'design' | 'implementation' | 'verification' | 'test';
  label: string;
  parts: DiagramStagePart[];
  complete: boolean;
  running: boolean;
}
export interface DiagramModule {
  id: string;
  key: string;
  name: string;
  group: 'boot' | 'main' | 'unknown';
  percent: number | null;
  stages: DiagramStage[];
  activity: 'running' | 'waiting' | 'failed' | 'unknown' | 'complete' | 'transition';
  tone: DiagramTone;
  summary: string;
  detail: string;
  runningStages: ServerStageName[];
  diagnostics: string[];
}
export interface DiagramGroup {
  id: 'boot' | 'main';
  label: string;
  modules: DiagramModule[];
  percent: number | null;
}
export interface DiagramModel {
  contractVersion: 1;
  contextKey: string;
  jobId: string | null;
  title: string;
  storedAt: string | null;
  paused: boolean;
  bootReady: boolean | null;
  overallPercent: number | null;
  groups: DiagramGroup[];
  unassigned: DiagramModule[];
  diagnostics: string[];
}
export interface SnapshotObservation {
  status: 'checking' | 'ready' | 'failed' | 'regressed' | 'empty';
  receivedAt: number | null;
  receivedMonoMs: number | null;
  staleAfterMs: number;
  needsConfirmation: boolean;
  detail: string;
}
export interface SnapshotHealth {
  fresh: boolean;
  label: string;
  tone: DiagramTone;
}
/** Supply only after the provider's scope, observation time and expiry are verified. */
export interface AconObservation {
  provider: string;
  jobId: string;
  moduleId?: string;
  scope: 'job' | 'module';
  state: 'connected' | 'disconnected' | 'not_started' | 'unknown';
  observedAt: number;
  expiresAt: number;
  activity?: boolean;
}
export interface DiagramTabProps {
  model: DiagramModel;
  observation: SnapshotObservation;
  active: boolean;
  acon?: AconObservation[];
}
