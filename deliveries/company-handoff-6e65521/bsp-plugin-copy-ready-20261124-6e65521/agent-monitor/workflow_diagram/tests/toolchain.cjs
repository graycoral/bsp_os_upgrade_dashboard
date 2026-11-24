const path = require('node:path');
module.exports = path.resolve(process.env.WORKFLOW_TOOLCHAIN_DIR || path.join(__dirname, '../../apps/web/node_modules'));
