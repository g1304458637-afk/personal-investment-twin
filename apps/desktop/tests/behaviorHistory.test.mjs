import assert from "node:assert/strict";
import test from "node:test";

import { historyDisplayMode } from "../src/data/behaviorHistory.ts";

function series(points) {
  return {
    metricId: "portfolio_concentration_hhi",
    methodId: "hhi_security_weights_v1",
    methodVersion: "1",
    dataTier: "synthetic",
    limitations: [],
    points,
  };
}

test("one valid HHI snapshot is not presented as a trend", () => {
  assert.equal(
    historyDisplayMode(
      series([
        {
          date: "2025-01-06T00:00:00",
          value: 0.42,
          status: "complete",
          sourceEvidenceId: "ev_one",
        },
      ]),
    ),
    "single",
  );
});

test("multiple HHI snapshots retain real dates for a series", () => {
  const input = series([
    {
      date: "2025-01-06T00:00:00",
      value: 0.42,
      status: "complete",
      sourceEvidenceId: "ev_one",
    },
    {
      date: "2025-01-17T00:00:00",
      value: 0.36,
      status: "complete",
      sourceEvidenceId: "ev_two",
    },
  ]);

  assert.equal(historyDisplayMode(input), "series");
  assert.deepEqual(
    input.points.map((point) => point.date),
    ["2025-01-06T00:00:00", "2025-01-17T00:00:00"],
  );
});
