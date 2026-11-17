import { test, expect } from "@playwright/test";

// Audit regression (2026-11-17): a prolonged publisher outage must not leave the tile dead.
// Opt-in; blocks only this browser context's requests for one channel. No backend or MediaMTX mutation.
test("live player recovers after a prolonged (150 s) mid-play outage", async ({ page }) => {
  test.skip(
    process.env.DIRA_LIVE_PLAYER_TEST !== "1",
    "Opt-in: uses local live MediaMTX, browser-only request blocking",
  );
  test.setTimeout(300000);
  let blocked = false;
  await page.route("**/sky_uk/**", async (route) => {
    if (blocked) await route.abort("failed");
    else await route.continue();
  });
  await page.goto("/");
  const tile = page.getByRole("button", { name: "Expand Sky News UK", exact: true });
  const video = tile.locator("video");
  const time = () => video.evaluate((v) => (v as HTMLVideoElement).currentTime);
  await expect.poll(time, { timeout: 40000 }).toBeGreaterThan(2);
  blocked = true;
  await page.waitForTimeout(150000);
  const frozen = await time();
  blocked = false;
  const restored = Date.now();
  await expect.poll(time, { timeout: 60000 }).toBeGreaterThan(frozen + 3);
  console.log(`recovered ${(Date.now() - restored) / 1000}s after the source returned`);
  await expect(tile.locator(".video-error")).toHaveCount(0);
});
