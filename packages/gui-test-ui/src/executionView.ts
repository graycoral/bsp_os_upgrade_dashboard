export type ExecutionView = 'default' | 'live';

const storageKey = 'gui-execution-view';

function readExecutionView(): ExecutionView {
  const requested = new URLSearchParams(location.search).get('guiExecution');
  if (requested) return requested === 'live' ? 'live' : 'default';
  try { return localStorage.getItem(storageKey) === 'live' ? 'live' : 'default'; }
  catch { return 'default'; }
}

export const executionView = readExecutionView();

// Commit the preference after navigation succeeds. A cancelled beforeunload
// prompt must leave the current page and its saved mode unchanged.
const requested = new URLSearchParams(location.search).get('guiExecution');
if (requested === 'live' || requested === 'default') {
  try { localStorage.setItem(storageKey, executionView); } catch { /* The URL still selects the mode. */ }
}

export function applyExecutionView(mode: ExecutionView) {
  const url = new URL(location.href);
  url.searchParams.set('guiExecution', mode);
  location.assign(url.href);
}
