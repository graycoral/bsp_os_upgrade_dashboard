const {defineConfig} = require('./runtime.cjs');
const path = require('node:path');
module.exports = defineConfig({
  testDir: __dirname, testMatch: /.*\.spec\.ts$/, fullyParallel: false, workers: 1,
  timeout: 45000, outputDir: path.resolve(__dirname, '../../.local-reports/workflow-diagram-artifacts'),
  reporter: [['list'], ['json', {outputFile: path.resolve(__dirname, '../../.local-reports/workflow-diagram-results.json')}]],
  use: {baseURL: `http://127.0.0.1:${process.env.WORKFLOW_TEST_PORT || 43129}`, viewport: {width: 1440, height: 1000},
    screenshot: 'only-on-failure', trace: 'retain-on-failure',
    launchOptions: {executablePath: process.env.BSP_BROWSER_EXECUTABLE}},
});
