import {test,expect} from '@playwright/test';

test('command center: stream control, evidence, search, rules and brief',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('/');
 await expect(page.getByText('Connected',{exact:true})).toBeVisible();
 await expect(page.getByRole('button',{name:'Expand Kuwait TV'})).toBeVisible();
 await page.getByRole('button',{name:'Pause simulation'}).click();
 await expect(page.getByRole('button',{name:'Resume simulation'})).toBeVisible();
 await expect(page.getByRole('button',{name:'Resume simulation'})).toHaveAttribute('aria-pressed','false');
 await page.getByRole('button',{name:'Expand Kuwait TV'}).click();
 await expect(page.getByRole('dialog')).toBeVisible();
 await page.getByLabel('Close dialog').click();
 await page.getByLabel('Search intelligence').fill('النفط');
 await page.getByLabel('Search intelligence').press('Enter');
 await expect(page.locator('.result-row').first()).toBeVisible();
 await page.locator('.result-row').first().click();
 await expect(page.getByText('Evidence ID',{exact:true})).toBeVisible();
 await page.getByLabel('Close dialog').click();
 await page.getByRole('button',{name:'Signals & alerts',exact:true}).click();
 await page.getByLabel('Add rule').click();
 await page.getByLabel('Rule name').fill('Browser acceptance rule');
 await page.getByLabel('Pattern',{exact:true}).fill('اختبار');
 await page.getByRole('button',{name:'Save rule'}).click();
 await expect(page.getByText('Browser acceptance rule',{exact:true})).toBeVisible();
 await page.getByLabel('Toggle Browser acceptance rule').click();
 await expect(page.getByLabel('Toggle Browser acceptance rule')).toHaveAttribute('aria-pressed','false');
 await page.getByLabel('Delete Browser acceptance rule').click();
 await expect(page.getByText('Browser acceptance rule',{exact:true})).toHaveCount(0);
 await page.getByRole('button',{name:'Generate brief',exact:true}).click();
 await expect(page.locator('.brief-card').first()).toBeVisible();
 await expect(page.getByRole('button',{name:'Generate brief',exact:true})).toBeEnabled();
 await page.locator('.evidence-links button').first().click();
 await expect(page.getByRole('dialog')).toBeVisible();
 await page.getByLabel('Close dialog').click();
 const download=page.waitForEvent('download');
 await page.getByLabel('Export brief').first().click();
 expect((await download).suggestedFilename()).toMatch(/^dira-.*\.md$/);
 await page.getByRole('button',{name:'Command center',exact:true}).click();
 await page.getByRole('button',{name:'Resume simulation'}).click();
 expect(errors).toEqual([]);
});

test('Arabic RTL and mobile navigation remain usable without horizontal overflow',async({page})=>{
 await page.setViewportSize({width:390,height:844});
 await page.goto('/');
 await expect(page.getByText('Connected',{exact:true})).toBeAttached();
 await page.getByRole('button',{name:'العربية',exact:true}).click();
 await expect(page.locator('html')).toHaveAttribute('dir','rtl');
 await expect(page.getByRole('heading',{name:'مركز القيادة.'})).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
 await page.screenshot({path:'../docs/dira-mobile.png',fullPage:true});
 await page.getByRole('button',{name:'أرشيف الرصد',exact:true}).click();
 await expect(page.getByLabel('Archive query')).toBeVisible();
 await page.getByRole('button',{name:'حالة النظام',exact:true}).click();
 await expect(page.getByRole('heading',{name:'خدمات المنصة'})).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
});

test('Obsidian theme and reconnect restore the stream',async({page})=>{
 await page.goto('/');
 await expect(page.getByText('Connected',{exact:true})).toBeVisible();
 await expect(page.locator('html')).toHaveCSS('background-color','rgb(12, 14, 18)');
 await expect(page.locator('.panel').first()).toHaveCSS('backdrop-filter','blur(40px)');
 await expect(page.locator('.heading-actions .primary')).toHaveCSS('background-color','rgb(245, 158, 11)');
 await page.screenshot({path:'../docs/dira-desktop.png',fullPage:true});
 await page.context().setOffline(true);
 await page.context().setOffline(false);
 await page.reload();
 await expect(page.getByText('Connected',{exact:true})).toBeVisible();
 await expect(page.locator('.transcript-row').first()).toBeVisible();
});

test('cloud egress and manual scheduling are disclosed', async ({page}) => {
 test.skip(process.env.DIRA_TEST_CLOUD !== '1', 'Requires the isolated mocked-cloud configuration');
 await page.goto('/');
 await expect(page.getByText('Cloud briefs enabled: evidence text leaves this Mac when a brief is generated.', {exact:false})).toBeVisible();
 await expect(page.getByText('Manual generation only.', {exact:false})).toBeVisible();
});
