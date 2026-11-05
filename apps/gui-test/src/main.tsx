import {createRoot} from 'react-dom/client';
import TestPage from '../../../packages/gui-test-ui/src/TestPage';
createRoot(document.getElementById('root')!).render(<TestPage standalone/>);
