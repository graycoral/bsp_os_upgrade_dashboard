import {createRoot} from 'react-dom/client';
import {TestPage,createBrowserGuiTestHost} from '../../../packages/gui-test-ui/src';
const host=createBrowserGuiTestHost();
createRoot(document.getElementById('root')!).render(<TestPage standalone host={host}/>);
