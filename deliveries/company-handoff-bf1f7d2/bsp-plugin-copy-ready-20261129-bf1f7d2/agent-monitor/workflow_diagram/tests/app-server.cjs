const path = require('node:path');
const {realpathSync} = require('node:fs');
const {pathToFileURL} = require('node:url');
module.exports.startAppServer = async function startAppServer() {
  const root = path.resolve(__dirname, '../../apps/web');
  const repository = path.resolve(__dirname, '../..');
  const toolchain = realpathSync(require('./toolchain.cjs'));
  const {createServer} = await import(pathToFileURL(path.join(toolchain, 'vite/dist/node/index.js')).href);
  // Fixtures import sibling source modules; installed dependencies may be a junction.
  const server = await createServer({root, configFile: path.join(root, 'vite.config.ts'),
    server: {host: '127.0.0.1', port: 0, fs: {allow: [repository, toolchain]}}});
  await server.listen(); const address = server.httpServer.address();
  return {url: `http://127.0.0.1:${address.port}`, close: () => server.close()};
};
