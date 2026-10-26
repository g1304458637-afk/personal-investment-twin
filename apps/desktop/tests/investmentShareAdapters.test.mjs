import assert from 'node:assert/strict';
import test from 'node:test';

const { investmentInputsFromLedger, investmentInputsFromView } = await import('../src/data/investmentShareAdapters.ts');

function episode(overrides = {}) {
  return {
    episodeId: 'private-episode-id', subjectId: 'subject-a', instrumentId: '600000.SH', displayName: '浦发银行',
    isSynthetic: false, currency: 'CNY', status: 'closed', openedAt: '2025-01-01T00:00:00Z', closedAt: '2025-03-01T00:00:00Z',
    durationDays: 60, durationKind: 'final', quantity: null, averageCost: null, valuationAt: null, valuationPrice: null, marketValue: null,
    outcome: { result_kind: 'realized', pnl: 125, return_value: 0.05, result_at: '2025-03-01', availability: 'available', reason: null, outcome_id: 'private-outcome-id' },
    ...overrides,
  };
}

function view(overrides = {}) {
  return {
    subjectId: 'subject-a', asOf: '2025-03-02', dataTier: 'authorized_beta',
    portfolioState: { status: 'available', reason: null },
    summary: { openEpisodeCount: 1, closedEpisodeCount: 1, currentPositionCount: 1 },
    openEpisodes: [episode({ status: 'open', closedAt: null, outcome: { result_kind: 'marked', pnl: -20, return_value: -0.02, result_at: '2025-03-02', availability: 'available', reason: 'private reason', outcome_id: 'private-id' } })],
    closedEpisodes: [episode()], primaryEpisodeId: null,
    ...overrides,
  };
}

function ledger(overrides = {}) {
  return {
    subject_id: 'subject-a', account_id: 'account-a', enabled: true,
    profile: { opening_date: '2025-01-01', currency: 'CNY', initial_cash: 1000 },
    snapshot: {
      status: 'available', as_of: '2025-03-01', currency: 'CNY', errors: [], warnings: [], definitions: [],
      equity: 1600, net_contributions: 500, period_pnl: 100,
      positions: [
        { symbol: 'AAA', quantity: 2, market_value: 600, cost_basis: 550 },
        { symbol: 'BBB', quantity: 1, market_value: 400, cost_basis: 390 },
      ],
      episodes: [{ episode_id: 'private-episode', symbol: 'AAA', opened_at: '2025-01-02', closed_at: '2025-02-01', status: 'closed', realized_pnl: 20, source_refs: ['/private/path.csv'] }],
      daily: [{ date: '2025-01-01', equity: 1000 }, { date: '2025-03-01', equity: 1600 }],
    },
    events: [{ source_ref: '/private/path.csv' }], executions: [{ execution_id: 'private-execution' }],
    ...overrides,
  };
}

test('view adapter rejects cross-subject and unavailable accounts', () => {
  assert.throws(() => investmentInputsFromView(view(), null, 'subject-b'), /subject_mismatch/);
  const crossSubjectRow = view();
  crossSubjectRow.closedEpisodes[0].subjectId = 'subject-b';
  assert.throws(() => investmentInputsFromView(crossSubjectRow, null, 'subject-a'), /subject_mismatch/);
  assert.throws(() => investmentInputsFromView(view({ portfolioState: { status: 'unavailable' } }), null, 'subject-a'), /portfolio_unavailable/);
});

test('authorized view remains local-account sourced and excludes account and episode ids', () => {
  const inputs = investmentInputsFromView(view(), null, 'subject-a');
  assert.equal(inputs[0].source, 'local_account');
  assert.equal(inputs[0].kind, 'episode');
  assert.equal(inputs[0].metrics.returnValue, -0.02);
  assert.match(inputs[0].definitions[0], /持有中结果/);
  assert.equal(inputs[1].metrics.returnValue, 0.05);
  assert.match(inputs[1].definitions[0], /已实现结果/);
  assert.equal(inputs.at(-1).kind, 'period');
  assert.match(JSON.stringify(inputs), /local_account/);
  for (const privateValue of ['subject-a', 'account-a', 'private-episode-id', 'private-outcome-id', 'private reason']) {
    assert.ok(!JSON.stringify(inputs).includes(privateValue));
  }
  assert.ok(inputs.every(item => item.source !== 'synthetic'));
});

test('synthetic view cannot be promoted to a real source and unavailable outcomes are omitted', () => {
  const synthetic = view({ dataTier: 'synthetic', openEpisodes: [], closedEpisodes: [episode({ isSynthetic: true, outcome: { availability: 'unavailable', pnl: null, return_value: null, result_kind: 'unavailable', result_at: null, reason: 'private', outcome_id: null } })] });
  const inputs = investmentInputsFromView(synthetic, null, 'subject-a');
  assert.equal(inputs.some(item => item.kind === 'episode'), false);
  assert.ok(inputs.every(item => item.source === 'synthetic'));
  assert.equal(inputs.find(item => item.kind === 'period').metrics.returnValue, undefined);
  assert.equal(inputs.find(item => item.kind === 'period').metrics.maxDrawdown, undefined);
});

test('eligible authoritative return survives a missing PnL and uses view as-of when result date is absent', () => {
  const source = view({
    openEpisodes: [episode({ status: 'open', closedAt: null, outcome: {
      result_kind: 'marked', pnl: null, return_value: 0.12, result_at: null,
      availability: 'available', reason: null, outcome_id: null,
    } })],
    closedEpisodes: [],
  });
  const input = investmentInputsFromView(source, null, 'subject-a').find(item => item.kind === 'episode');
  assert.equal(input.metrics.pnl, undefined);
  assert.equal(input.metrics.returnValue, 0.12);
  assert.equal(input.asOf, '2025-03-02');
  assert.equal(input.end, undefined);

  source.openEpisodes[0].outcome.result_kind = 'unavailable';
  const rejected = investmentInputsFromView(source, null, 'subject-a');
  assert.equal(rejected.some(item => item.kind === 'episode'), false);
});

test('view null metrics stay absent and allocation weights retain their securities denominator', () => {
  const allocation = {
    positions_value: 1000, position_count: 2, skipped_no_market_value: 1, hhi: 0.5,
    definition: 'do not copy this runtime text',
    positions: [
      { instrument_id: 'AAA', display_name: 'Alpha', quantity: 1, market_value: 600, currency: 'CNY', weight: 0.6, as_of: '2025-03-02' },
      { instrument_id: 'BBB', display_name: 'Beta', quantity: 1, market_value: 400, currency: 'CNY', weight: 0.4, as_of: '2025-03-02' },
    ],
  };
  const inputs = investmentInputsFromView(view({
    openEpisodes: [],
    closedEpisodes: [episode({ outcome: { result_kind: 'unavailable', pnl: null, return_value: null, result_at: null, availability: 'unavailable', reason: 'private', outcome_id: null } })],
  }), allocation, 'subject-a');
  const episodeInput = inputs.find(item => item.kind === 'episode');
  const holdings = inputs.find(item => item.kind === 'holdings');
  assert.equal(episodeInput, undefined);
  assert.deepEqual(holdings.holdings.map(row => row.weight), [0.6, 0.4]);
  assert.equal(holdings.metrics.equity, undefined);
  assert.equal(holdings.holdings.reduce((sum, row) => sum + row.weight, 0), 1);
  assert.match(holdings.definitions.join(' '), /部分证券因缺少市值/);
  assert.ok(!JSON.stringify(inputs).includes('do not copy this runtime text'));
});

test('view allocations with mixed currencies or malformed weights are not partially normalized', () => {
  const allocation = {
    positions_value: 1000, position_count: 2, skipped_no_market_value: 0, hhi: null, definition: 'private',
    positions: [
      { instrument_id: 'AAA', display_name: 'Alpha', quantity: 1, market_value: 600, currency: 'CNY', weight: 0.6, as_of: '2025-03-02' },
      { instrument_id: 'BBB', display_name: 'Beta', quantity: 1, market_value: 400, currency: 'HKD', weight: 1.2, as_of: '2025-03-02' },
    ],
  };
  const inputs = investmentInputsFromView(view(), allocation, 'subject-a');
  assert.equal(inputs.some(item => item.kind === 'holdings'), false);
  const fallback = investmentInputsFromView(view(), { ...allocation, positions: allocation.positions.map((row, index) => ({ ...row, currency: 'CNY', weight: index ? null : 0.6 })) }, 'subject-a');
  const holdingInput = fallback.find(item => item.kind === 'holdings');
  assert.ok(holdingInput);
  assert.equal(holdingInput.holdings.some(row => row.weight !== undefined), false);
  assert.match(holdingInput.definitions.join(' '), /比例不完整或无效/);
});

test('allocation weights require complete matching valuation dates and values', () => {
  const base = {
    positions_value: 1000, position_count: 2, skipped_no_market_value: 0, hhi: null, definition: 'private',
    positions: [
      { instrument_id: 'AAA', display_name: 'Alpha', quantity: 1, market_value: 600, currency: 'CNY', weight: 0.6, as_of: '2025-03-02' },
      { instrument_id: 'BBB', display_name: 'Beta', quantity: 1, market_value: 400, currency: 'CNY', weight: 0.4, as_of: '2025-03-03' },
    ],
  };
  for (const positions of [
    base.positions,
    base.positions.map((row, index) => index === 0 ? { ...row, as_of: null } : row),
    base.positions.map((row, index) => ({ ...row, as_of: '2025-03-02', ...(index === 0 ? { market_value: null } : {}) })),
  ]) {
    const inputs = investmentInputsFromView(view(), { ...base, positions }, 'subject-a');
    const holdings = inputs.find(item => item.kind === 'holdings');
    assert.ok(holdings);
    assert.equal(holdings.holdings.some(row => row.weight !== undefined), false);
    assert.match(holdings.definitions.join(' '), /未展示任何仓位比例/);
  }
  const inconsistentDate = investmentInputsFromView(view(), base, 'subject-a').find(item => item.kind === 'holdings');
  assert.deepEqual(inconsistentDate.holdings.map(row => row.marketValue), [600, 400]);
  assert.match(inconsistentDate.definitions.join(' '), /估值日期缺失或不一致/);
});

test('ledger period never derives return or drawdown from equity changes or deposits', () => {
  const first = investmentInputsFromLedger(ledger(), 'subject-a', 'account-a').find(item => item.kind === 'period');
  const changed = ledger();
  changed.snapshot.equity = 9600;
  changed.snapshot.net_contributions = 8500;
  const second = investmentInputsFromLedger(changed, 'subject-a', 'account-a').find(item => item.kind === 'period');
  assert.equal(first.metrics.equity, 1600);
  assert.equal(second.metrics.equity, 9600);
  assert.equal(first.metrics.netContributions, 500);
  assert.equal(second.metrics.netContributions, 8500);
  assert.equal(first.metrics.returnValue, undefined);
  assert.equal(second.metrics.returnValue, undefined);
  assert.equal(first.metrics.maxDrawdown, undefined);
  assert.equal(first.metrics.pnl, 100);
  assert.match(first.definitions.join(' '), /未从资产变化推算收益率或最大回撤/);
});

test('ledger owner isolation and invalid snapshots fail closed', () => {
  assert.throws(() => investmentInputsFromLedger(ledger(), 'subject-b', 'account-a'), /account_mismatch/);
  assert.throws(() => investmentInputsFromLedger(ledger(), 'subject-a', 'account-b'), /account_mismatch/);
  assert.throws(() => investmentInputsFromLedger(ledger({ snapshot: { ...ledger().snapshot, status: 'invalid' } }), 'subject-a', 'account-a'), /ledger_invalid/);
  assert.throws(() => investmentInputsFromLedger(ledger({ snapshot: { ...ledger().snapshot, errors: [{ code: 'blocked' }] } }), 'subject-a', 'account-a'), /ledger_invalid/);
});

test('ledger rejects position rows whose explicit currency differs from snapshot currency', () => {
  const data = ledger();
  data.snapshot.positions[0].currency = 'USD';
  assert.throws(() => investmentInputsFromLedger(data, 'subject-a', 'account-a'), /currency_mismatch/);
});

test('ledger missing valuation never becomes zero or a partial set of normalized weights', () => {
  const data = ledger();
  data.snapshot.positions[1].market_value = null;
  const input = investmentInputsFromLedger(data, 'subject-a', 'account-a')[0];
  assert.equal(input.kind, 'holdings');
  assert.equal(input.holdings[0].marketValue, 600);
  assert.equal(input.holdings[1].marketValue, undefined);
  assert.equal(input.holdings.some(row => row.weight !== undefined), false);
  assert.match(input.definitions.join(' '), /未计算任何仓位比例/);
});

test('ledger holdings weights use only complete positive-quantity securities and the securities denominator', () => {
  const input = investmentInputsFromLedger(ledger(), 'subject-a', 'account-a')[0];
  assert.deepEqual(input.holdings.map(row => row.weight), [0.6, 0.4]);
  assert.match(input.definitions.join(' '), /不含现金/);
});

test('ledger episode exposes realized PnL only and serialized inputs contain no private ids or paths', () => {
  const inputs = investmentInputsFromLedger(ledger(), 'subject-a', 'account-a');
  const item = inputs.find(value => value.kind === 'episode');
  assert.equal(item.metrics.pnl, 20);
  assert.equal(item.metrics.returnValue, undefined);
  assert.equal(item.pnlBasis, 'realized');
  const json = JSON.stringify(inputs);
  for (const privateValue of ['subject-a', 'account-a', 'private-episode', 'private-execution', '/private/path.csv']) {
    assert.ok(!json.includes(privateValue));
  }
});

test('ledger episode filter returns only the requested episode and rejects unknown ids', () => {
  const item = investmentInputsFromLedger(ledger(), 'subject-a', 'account-a', 'private-episode');
  assert.equal(item.length, 1);
  assert.equal(item[0].kind, 'episode');
  assert.throws(() => investmentInputsFromLedger(ledger(), 'subject-a', 'account-a', 'another'), /episode_unavailable/);
});
