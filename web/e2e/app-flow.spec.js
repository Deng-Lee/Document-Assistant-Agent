import { expect, test } from "@playwright/test";

const BJJ_MARKDOWN = `---
type: BJJ
title: E2E Turtle Log
---

## 2026-03-09
- position: turtle
- orientation: 下位
- distance: 近距离
- goal: escape
- your_action: tripod post
- opponent_response: dragged me back
- opponent_control: 袖子
- your_adjustment: elbow inside recovery
- notes: head position stayed tight
`;

test("browser regression covers dashboard ingest, chat stream, traces replay, and evaluation launch", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("API ok")).toBeVisible();

  await page.getByLabel("source_path_hint").fill("e2e_bjj.md");
  await page.getByLabel("markdown_text").fill(BJJ_MARKDOWN);
  await page.getByRole("button", { name: "导入文本" }).click();
  await expect(jsonCard(page, "最近一次导入结果")).toContainText("doc_id");

  await page.goto("/chat");
  await page.getByLabel("user_message").fill("我在下位 turtle 被对手抓袖子，想 escape，应该怎么做？");
  await page.getByRole("button", { name: "流式发送消息" }).click();
  await expect(page.getByText("started")).toBeVisible();
  await expect(page.getByText("completed")).toBeVisible();
  await expect(jsonCard(page, "最新对话返回")).toContainText("trace_id");

  const responsePayload = JSON.parse(await jsonCard(page, "最新对话返回").textContent());
  const traceId = responsePayload.trace_id;

  await page.goto("/traces");
  await expect(page.locator(".trace-row strong").filter({ hasText: traceId }).first()).toBeVisible();
  await page.getByRole("button", { name: "运行 replay" }).click();
  await expect(jsonCard(page, "Replay 结果")).toContainText("trace_id");

  await page.goto("/evaluation");
  await page.getByLabel("trace_ids (comma separated)").fill(traceId);
  await page.getByRole("button", { name: "运行评测" }).click();
  await expect(jsonCard(page, "最近一次启动结果")).toContainText("eval_run_id");
  await expect(page.locator(".trace-row strong").filter({ hasText: /eval_/ }).first()).toBeVisible();
});

function jsonCard(page, title) {
  return page.locator("section.panel").filter({ has: page.getByRole("heading", { name: title }) }).locator("pre");
}
