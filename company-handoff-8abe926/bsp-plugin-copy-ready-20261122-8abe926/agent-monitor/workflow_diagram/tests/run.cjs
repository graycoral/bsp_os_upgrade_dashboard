const {spawn} = require('node:child_process');
const path = require('node:path');
const root = path.resolve(__dirname, '../..');
const cli = path.join(require('./toolchain.cjs'), '@playwright/test/cli.js');
const args = process.argv.slice(2);
const child = spawn(process.execPath, [cli, 'test', '--config', path.join(__dirname, 'playwright.config.cjs'), ...args], {
  cwd: root, stdio: 'inherit', env: process.env,
});
child.on('exit', code => process.exitCode = code === null ? 1 : code);
child.on('error', error => { console.error(error.message); process.exitCode = 1; });
