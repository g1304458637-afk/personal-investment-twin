import assert from 'node:assert/strict';
import test from 'node:test';
import { buildReviewCard } from '../src/lib/reviewCard.ts';

function fakeEntry() {
  const pricePoints = [];
  for (let i = 0; i < 60; i += 1) {
    const day = new Date(Date.UTC(2025, 0, 1) + i * 86400000).toISOString().slice(0, 10);
    pricePoints.push({ observedAt: day, price: 20 * (1 + i * 0.01), segment: "episode" });
  }
  const decision = (i, type) => ({
    occurredAt: pricePoints[i].observedAt + "T10:00:00",
    decisionType: type,
  });
  return {
    episodeId: "pe_abcdef123456",
    openedAt: pricePoints[0].observedAt,
    closedAt: pricePoints[59].observedAt,
    status: "closed",
    durationDays: 60,
    decisions: [decision(5, "open_position"), decision(20, "add_position"), decision(45, "reduce_position"), decision(59, "close_position")],
    pricePoints,
    result: { returnValue: 0.2456, resultKind: "realized", resultSign: "profit" },
  };
}

test('card is desensitized by construction: no instrument id, no absolute prices', () => {
  const card = buildReviewCard(fakeEntry());
  assert.ok(!card.svg.includes("pe_abcdef123456"), "episode id must not leak");
  // No absolute-price label: no currency symbol anywhere in the card.
  assert.ok(!card.svg.includes("¥") && !card.svg.includes("价格："), "absolute price labels must not leak");
  assert.ok(card.svg.includes("归一化"), "normalized-axis statement must be present");
  assert.ok(card.svg.includes("不构成任何投资建议"), "boundary must be present");
});

test('card shows rhythm and desensitized instrument code', () => {
  const card = buildReviewCard(fakeEntry());
  assert.ok(card.svg.includes("建仓 → 加仓 → 减仓 → 平仓"));
  assert.ok(/标的 #[0-9A-F]{4}/.test(card.svg), "anonymized instrument code expected");
  assert.ok(card.svg.includes("+24.6%"), "relative return expected");
  assert.ok(card.svg.includes("已实现结果"));
});

test('card generation is deterministic', () => {
  assert.equal(buildReviewCard(fakeEntry()).svg, buildReviewCard(fakeEntry()).svg);
});

test('open episode uses 至今 and marked label', () => {
  const entry = fakeEntry();
  entry.closedAt = null;
  entry.status = "open";
  entry.result = { returnValue: -0.05, resultKind: "marked", resultSign: "loss" };
  const card = buildReviewCard(entry);
  assert.ok(card.svg.includes("至今"));
  assert.ok(card.svg.includes("持有中估值"));
  assert.ok(card.svg.includes("-5.0%"));
});
