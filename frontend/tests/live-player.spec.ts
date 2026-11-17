import { test, expect } from "@playwright/test";

test("live player recovers after initial playlist outage", async ({ page }) => {
  test.skip(
    process.env.DIRA_LIVE_PLAYER_TEST !== "1",
    "Opt-in: uses local live MediaMTX, browser-only request blocking",
  );
  test.setTimeout(80000);
  let blocked = true;
  await page.route("**/sky_uk/**", async (route) => {
    if (blocked) await route.abort("failed");
    else await route.continue();
  });
  await page.goto("/");
  const video = page
    .getByRole("button", { name: "Expand Sky News UK", exact: true })
    .locator("video");
  await expect(video).toBeAttached();
  await page.waitForTimeout(18000);
  blocked = false;
  await expect
    .poll(
      async () => video.evaluate((v) => (v as HTMLVideoElement).currentTime),
      { timeout: 40000 },
    )
    .toBeGreaterThan(1);
  await expect(
    page
      .getByRole("button", { name: "Expand Sky News UK", exact: true })
      .locator(".video-error"),
  ).toHaveCount(0);
});
