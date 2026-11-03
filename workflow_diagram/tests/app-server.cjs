const path = require('node:path');
const {pathToFileURL} = require('node:url');
module.exports.startAppServer = async function startAppServer() {
  const root = path.resolve(__dirname, '../../apps/web');
  const {createServer} = await import(pathToFileURL(path.join(require('./toolchain.cjs'), 'vite/dist/node/index.js')).href);
  const server = await createServer({root, configFile: path.join(root, 'vite.config.ts'), server: {host: '127.0.0.1', port: 0}});
  await server.listen(); const address = server.httpServer.address();
  return {url: `http://127.0.0.1:${address.port}`, close: () => server.close()};
};
