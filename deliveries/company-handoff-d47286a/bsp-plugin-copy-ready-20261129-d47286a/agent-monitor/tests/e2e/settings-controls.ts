// Navigation helpers only: every test still asserts its own visible state and
// saved values. Switching categories must reveal the retained editor, not rebuild it.
export async function selectTestSetting(page: any, category: 'basic'|'source'|'command'|'suite'|'view') {
  const panel = page.getByRole('button', { name: 'Test 설정', exact: true });
  if (await panel.getAttribute('aria-expanded') === 'false') await panel.click();
  await page.getByRole('combobox', { name: 'Test 설정 항목', exact: true }).selectOption(category);
}

export async function expandTestDetails(page: any, title: string) {
  const summary = page.locator('summary').filter({ hasText: new RegExp('^' + title + '$') });
  if (await summary.locator('..').getAttribute('open') === null) await summary.click();
}

export async function editCommand(page: any) {
  await selectTestSetting(page, 'command');
  await expandTestDetails(page, '명령 직접 편집');
}

export async function editConnection(page: any) {
  await selectTestSetting(page, 'basic');
  await expandTestDetails(page, '연결 상세 설정');
}
