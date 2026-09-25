import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';

const { adaptReviewPack, episodeExitQuality, episodeTagsFor, playbookTagFor,
  prepareMonthlyHeatmap, addEpisodeTag, removeEpisodeTag,
  EPISODE_TAG_MAX_COUNT, EPISODE_TAG_MAX_LENGTH }
  = await import('../src/data/reviewPack.ts');

const demoUrl = new URL('../src/generated/review-pack-demo.json', import.meta.url);

async function loadRaw() {
  return JSON.parse(await readFile(demoUrl, 'utf8'));
}

async function load() {
  return adaptReviewPack(await loadRaw());
}

test('adapter parses the generated review pack without altering any number', async () => {
  const raw = await loadRaw();
  const pack = await load();
  assert.equal(pack.subjectId, raw.subject_id);
  assert.equal(pack.accountId, raw.account_id);
  assert.equal(pack.asOf, raw.as_of);
  assert.equal(pack.coverage.executionCount, raw.coverage.execution_count);
  assert.equal(pack.coverage.episodeCount, raw.coverage.episode_count);
  assert.equal(pack.coverage.firstDate, raw.coverage.first_date);
  assert.equal(pack.exitQuality.episodes.length, raw.exit_quality.episodes.length);
  // Every transported value is byte-identical to the payload.
  for (let index = 0; index < pack.exitQuality.episodes.length; index += 1) {
    const view = pack.exitQuality.episodes[index];
    const rawEpisode = raw.exit_quality.episodes[index];
    assert.equal(view.episodeId, rawEpisode.episode_id);
    assert.equal(view.mfeAmount, rawEpisode.mfe_amount);
    assert.equal(view.maeAmount, rawEpisode.mae_amount);
    assert.equal(view.realizedPnl, rawEpisode.realized_pnl);
    assert.equal(view.exitEfficiency, rawEpisode.exit_efficiency);
    assert.equal(view.facts.holdDays, rawEpisode.facts.hold_days);
  }
  // Episodes without an efficiency yet surface as null, never as a guess.
  const withoutEfficiency = pack.exitQuality.episodes.find((item) => item.exitEfficiency === null);
  assert.ok(withoutEfficiency, 'artifact should exercise the null-efficiency path');
  assert.equal(pack.calendar.months.length, raw.calendar.months.length);
  assert.equal(pack.calendar.months[0].realizedPnl, raw.calendar.months[0].realized_pnl);
  assert.equal(pack.playbook.tags.length, raw.playbook.tags.length);
  assert.equal(pack.playbook.untaggedEpisodeCount, raw.playbook.untagged_episode_count);
});

test('adapter fails closed on any tampered payload', async () => {
  const good = await loadRaw();
  const mutations = [
    (r) => { r.schema_version = 'review_pack.v2'; },
    (r) => { r.subject_id = ''; },
    (r) => { r.coverage.execution_count = -1; },
    (r) => { r.coverage.execution_count = Number.NaN; },
    (r) => { r.coverage.first_date = '2025/01/02'; },
    (r) => { delete r.coverage; },
    (r) => { r.exit_quality.episodes[0].mfe_amount = Number.NaN; },
    (r) => { r.exit_quality.episodes[0].exit_efficiency = '0.6'; },
    (r) => { r.exit_quality.episodes[0].facts.peak_date = 'not-a-date'; },
    (r) => { r.exit_quality.episodes.push(r.exit_quality.episodes[0]); }, // duplicate episode ids
    (r) => { r.calendar.months[0].month = '2025-13'; },
    (r) => { r.calendar.months[0].win_count = r.calendar.months[0].closed_count + 1; }, // wins > closed
    (r) => { r.calendar.months.reverse(); }, // months must ascend
    (r) => { r.calendar.days[0].closed_count = -1; },
    (r) => { r.behavior_flags.tilt[0].trigger_date = '2025-06-03T00:00:00'; },
    // trade_count null is legal since the unevaluated-window item exists
    // (trigger day has no observed trading day after it); wrong types and
    // negative counts must still fail closed.
    (r) => { r.behavior_flags.tilt[0].window.trade_count = 'many'; },
    (r) => { r.behavior_flags.tilt[0].window.trade_count = -1; },
    (r) => { r.behavior_flags.tilt[0].window.avg_size_change_pct = 'up'; },
    (r) => { r.playbook.tags[0].confidence = 'maybe'; },
    (r) => { r.playbook.tags[0].win_count = r.playbook.tags[0].episode_count + 1; }, // wins > episodes
    (r) => { r.playbook.untagged_episode_count = -2; },
    (r) => { r.episode_tags[0].tags = [null]; },
    (r) => { r.episode_tags.push(r.episode_tags[0]); }, // duplicate tagged episode ids
  ];
  for (const mutate of mutations) {
    const raw = JSON.parse(JSON.stringify(good));
    mutate(raw);
    assert.throws(() => adaptReviewPack(raw), `mutation should fail closed: ${mutate}`);
  }
  // Non-payload shapes fail closed too.
  assert.throws(() => adaptReviewPack({}));
  assert.throws(() => adaptReviewPack(null));
});

test('episode matching only ever returns the requested episode record', async () => {
  const raw = await loadRaw();
  const pack = await load();
  const wanted = raw.exit_quality.episodes[0].episode_id;
  const match = episodeExitQuality(pack, wanted);
  assert.equal(match.episodeId, wanted);
  assert.equal(match.instrument, raw.exit_quality.episodes[0].instrument);
  assert.equal(episodeExitQuality(pack, 'pe_not_in_pack'), null);
  const tagged = raw.episode_tags[0];
  assert.deepEqual(episodeTagsFor(pack, tagged.episode_id), tagged.tags);
  assert.deepEqual(episodeTagsFor(pack, 'pe_not_in_pack'), []);
  const rawTag = raw.playbook.tags[0];
  const aggregate = playbookTagFor(pack, rawTag.tag);
  assert.equal(aggregate.episodeCount, rawTag.episode_count);
  assert.equal(aggregate.confidence, rawTag.confidence);
  assert.equal(playbookTagFor(pack, '不存在的标签'), null);
});

test('monthly heatmap is pure layout: twelve fixed slots per year, backend numbers verbatim', async () => {
  const raw = await loadRaw();
  const pack = await load();
  const years = prepareMonthlyHeatmap(pack.calendar.months);
  const expectedYears = [...new Set(raw.calendar.months.map((month) => month.month.slice(0, 4)))].sort();
  assert.deepEqual(years.map((year) => year.year), expectedYears);
  for (const year of years) {
    assert.equal(year.cells.length, 12);
    for (let index = 0; index < 12; index += 1) {
      const key = `${year.year}-${String(index + 1).padStart(2, '0')}`;
      const rawMonth = raw.calendar.months.find((month) => month.month === key);
      const cell = year.cells[index];
      if (rawMonth) {
        assert.equal(cell.month, key);
        assert.equal(cell.realizedPnl, rawMonth.realized_pnl);
        assert.equal(cell.closedCount, rawMonth.closed_count);
        assert.equal(cell.winCount, rawMonth.win_count);
      } else {
        assert.equal(cell, null);
      }
    }
  }
  // Empty input yields no fabricated years or months.
  assert.deepEqual(prepareMonthlyHeatmap([]), []);
  // Multi-year input groups into sorted years without inventing numbers.
  const multi = prepareMonthlyHeatmap([
    { month: '2024-12', realizedPnl: -100, closedCount: 1, winCount: 0 },
    { month: '2025-01', realizedPnl: 50, closedCount: 1, winCount: 1 },
  ]);
  assert.deepEqual(multi.map((year) => year.year), ['2024', '2025']);
  assert.equal(multi[0].cells[11].realizedPnl, -100);
  assert.equal(multi[1].cells[0].realizedPnl, 50);
});

test('episode tag client validation strips, dedupes, and enforces the documented limits', () => {
  assert.equal(EPISODE_TAG_MAX_LENGTH, 24);
  assert.equal(EPISODE_TAG_MAX_COUNT, 8);
  // Trims and adds.
  assert.deepEqual(addEpisodeTag([], '  按计划执行  '), { ok: true, tags: ['按计划执行'] });
  // Empty input is a rejection, not a silent no-op tag.
  assert.equal(addEpisodeTag(['a'], '   ').ok, false);
  // Exact duplicate after trimming.
  assert.deepEqual(addEpisodeTag(['按计划执行'], '按计划执行 '), { ok: false, reason: 'duplicate_tag' });
  // Over-long tag rejected without truncation (never fabricate a tag).
  assert.equal(addEpisodeTag([], 'x'.repeat(EPISODE_TAG_MAX_LENGTH + 1)).ok, false);
  assert.deepEqual(addEpisodeTag([], 'x'.repeat(EPISODE_TAG_MAX_LENGTH)), { ok: true, tags: ['x'.repeat(EPISODE_TAG_MAX_LENGTH)] });
  // Count cap.
  const full = Array.from({ length: EPISODE_TAG_MAX_COUNT }, (_v, i) => `tag-${i}`);
  assert.deepEqual(addEpisodeTag(full, 'one-more'), { ok: false, reason: 'too_many_tags' });
  // removeEpisodeTag never mutates; unknown tags are a no-op.
  const original = ['a', 'b'];
  assert.deepEqual(removeEpisodeTag(original, 'a'), ['b']);
  assert.deepEqual(original, ['a', 'b']);
  assert.deepEqual(removeEpisodeTag(original, 'zzz'), ['a', 'b']);
});

test('episode pages and the account home load the pack through the sanctioned paths', async () => {
  const service = await readFile(new URL('../src/data/runtimeService.ts', import.meta.url), 'utf8');
  assert.match(service, /reviewPack:.*runtimeRequest<unknown>\("review_pack\.get"/);
  assert.match(service, /setEpisodeTags:.*runtimeRequest<unknown>\("episode_tags\.set"/);
  const loader = await readFile(new URL('../src/pages/AccountReviewPack.tsx', import.meta.url), 'utf8');
  // Browser preview binds the generated demo artifact through the vite-only wrapper.
  assert.match(loader, /import\("@\/data\/reviewPackDemo"\)/);
  // Real accounts go through the runtime API and the fail-closed adapter; a
  // cross-account response is rejected before it can render.
  assert.match(loader, /realUserApi\.reviewPack/);
  assert.match(loader, /adaptReviewPack/);
  assert.match(loader, /review_pack_account_mismatch/);
  const wrapper = await readFile(new URL('../src/data/reviewPackDemo.ts', import.meta.url), 'utf8');
  assert.match(wrapper, /import source from "@\/generated\/review-pack-demo\.json"/);
  const episodePage = await readFile(new URL('../src/pages/PositionEpisodePage.tsx', import.meta.url), 'utf8');
  assert.match(episodePage, /episodeExitQuality/);
  assert.match(episodePage, /setEpisodeTags/);
  const investmentsPage = await readFile(new URL('../src/pages/InvestmentsPage.tsx', import.meta.url), 'utf8');
  assert.match(investmentsPage, /AccountReviewPackPanel/);
});
