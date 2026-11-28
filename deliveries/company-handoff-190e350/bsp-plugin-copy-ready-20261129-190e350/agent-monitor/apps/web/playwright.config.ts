import { defineConfig } from '@playwright/test';
export default defineConfig({
 testDir:'../../tests/e2e', timeout:45000, fullyParallel:false, workers:1,
 outputDir:'../../.local-reports/browser-artifacts',
 reporter:[['list'],['json',{outputFile:'../../.local-reports/browser-results.json'}]],
 use:{baseURL:`http://127.0.0.1:${process.env.BSP_E2E_PORT||8766}`,viewport:{width:1440,height:1000},screenshot:'only-on-failure',trace:'retain-on-failure',launchOptions:{executablePath:process.env.BSP_BROWSER_EXECUTABLE}},
});
