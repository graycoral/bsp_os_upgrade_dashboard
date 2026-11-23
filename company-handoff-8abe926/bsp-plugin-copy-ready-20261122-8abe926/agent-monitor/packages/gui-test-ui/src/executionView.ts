// Compatibility functions stay lazy; importing this module does not read a browser.
import {getDefaultGuiTestHost,type ExecutionView} from './host';
export type {ExecutionView} from './host';
export function readExecutionView(){return getDefaultGuiTestHost().mode}
export function applyExecutionView(mode:ExecutionView){getDefaultGuiTestHost().applyMode(mode)}
