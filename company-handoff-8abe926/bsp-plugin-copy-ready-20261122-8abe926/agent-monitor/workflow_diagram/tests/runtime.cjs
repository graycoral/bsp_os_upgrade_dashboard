// Explicitly reuse the installed host toolchain; this does not install dependencies.
module.exports = require(require('node:path').join(require('./toolchain.cjs'), '@playwright/test'));
