import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';
const local=(path:string)=>fileURLToPath(new URL(path,import.meta.url));
export default defineConfig(({mode})=>({
 plugins:[react()],
 resolve:{dedupe:['react','react-dom'],alias:{'react':local('./node_modules/react'),'react-dom':local('./node_modules/react-dom')}},
 ...(mode==='standalone'?{root:local('../../gui_test/web'),build:{outDir:local('../../gui_test/static'),emptyOutDir:true}}:{}),
 server:{proxy:{'/api':'http://127.0.0.1:8765'}}
}));
