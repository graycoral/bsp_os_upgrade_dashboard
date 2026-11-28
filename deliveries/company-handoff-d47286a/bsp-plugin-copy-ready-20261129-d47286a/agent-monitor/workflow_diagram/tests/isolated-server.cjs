const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {pathToFileURL} = require('node:url');

/** Copy only the portable implementation, proving apps/web and gui_test are absent. */
async function startIsolatedServer() {
  const root = path.resolve(__dirname, '../..');
  const isolated = fs.mkdtempSync(path.join(os.tmpdir(), 'bsp-workflow-isolated-'));
  const feature = path.join(isolated, 'workflow_diagram');
  for (const folder of ['web', 'adapters', 'host']) {
    fs.cpSync(path.join(root, 'workflow_diagram', folder), path.join(feature, folder), {recursive: true});
  }
  // Instrument only the disposable copy. Parent Profiler commits include memo bailouts;
  // this counter measures actual DiagramView body entries without altering product source.
  const viewPath = path.join(feature, 'web', 'DiagramTab.tsx');
  const viewSource = fs.readFileSync(viewPath, 'utf8');
  const entry = 'function DiagramView({model,observation,active,acon}:DiagramTabProps) {';
  if (viewSource.split(entry).length !== 2) throw Error('DiagramView test instrumentation entry changed; update the test probe explicitly');
  fs.writeFileSync(viewPath, viewSource.replace(entry, entry + '\n  (window as any).__wdViewEntries = ((window as any).__wdViewEntries || 0) + 1;\n'));
  fs.copyFileSync(path.join(__dirname, 'fixtures.ts'), path.join(isolated, 'fixtures.ts'));
  fs.copyFileSync(path.join(__dirname, 'host.tsx'), path.join(isolated, 'host.tsx'));
  fs.writeFileSync(path.join(isolated, 'index.html'), '<!doctype html><html lang="ko"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1"></head><body><div id="root"></div><script type="module" src="/host.tsx"></script></body></html>');
  const deps = require('./toolchain.cjs');
  const {createServer, build} = await import(pathToFileURL(path.join(deps, 'vite/dist/node/index.js')).href);
  const configuration = {configFile: false, root: isolated,
    resolve: {alias: {'react': path.join(deps, 'react'), 'react-dom': path.join(deps, 'react-dom')}, dedupe: ['react', 'react-dom']},
    server: {host: '127.0.0.1', port: 0}, esbuild: {jsx: 'automatic'},
  };
  await build({...configuration, build: {outDir: path.join(isolated, 'dist'), emptyOutDir: false}});
  const server = await createServer(configuration);
  await server.listen();
  const address = server.httpServer.address();
  return {url: `http://127.0.0.1:${address.port}`, isolated,
    async close() {
      await server.close();
      const resolved = path.resolve(isolated), temp = path.resolve(os.tmpdir());
      if (path.dirname(resolved) !== temp || !path.basename(resolved).startsWith('bsp-workflow-isolated-')) throw Error('Refusing cleanup outside owned temporary host');
      fs.rmSync(resolved, {recursive: true, force: true});
    }};
}
module.exports = {startIsolatedServer};
