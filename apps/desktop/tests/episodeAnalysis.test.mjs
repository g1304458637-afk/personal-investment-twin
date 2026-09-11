import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';
import { episodeAnalysisTarget, episodeSection, hasDemoReviewSource } from '../src/workspace/episodeSample.ts';
const source = path => readFile(new URL(`../src/${path}`, import.meta.url), 'utf8');

test('only the registered showcase owner gets an analysis entry; unrelated examples cannot borrow answers', () => {
  assert.equal(hasDemoReviewSource('SYN_STUDY_SHOWCASE', 'SYN_STUDY_SHOWCASE'), true);
  assert.equal(hasDemoReviewSource('SYN_STUDY_SHOWCASE', 'SYN_STUDY_SHOWCASE_REFERENCE'), false);
  assert.equal(hasDemoReviewSource('local-user', 'ACC-1'), false);
});
test('demo navigation maps only a display-scoped episode and preserves same-stock canonical ids', async () => {
  const panel = await source('components/review/DecisionAnalysisWorkspace.tsx');
  assert.match(panel, /mapping\?\.display_episode_id !== base.episode_id/);
  assert.match(panel, /base\.episode_id === mapping\.canonical_episode_id/);
  assert.match(panel, /mapping.decision_display_ids\[id\]/);
  assert.match(panel, /if \(displayId\) navigateDecision\(displayId\)/);
  assert.match(panel, /if \(base\.episode_id === mapping\.canonical_episode_id\) \{\s*navigateDecision\(id\);/);
  const page = await source('pages/PositionEpisodePage.tsx');
  assert.match(page, /data.mode === "demo" \? "synthetic_showcase" : "real_user"/);
});

test('analysis deep links select only the requested section and encode the episode', () => {
  assert.equal(episodeAnalysisTarget('owned/a?b'), '/investments/episodes/owned%2Fa%3Fb?section=analysis');
  assert.equal(episodeSection(new URLSearchParams('section=analysis&decision=owned')), 'analysis');
  assert.equal(episodeSection(new URLSearchParams('section=unknown')), 'process');
});
test('episode analysis reuses the real runtime and keeps results mounted across section changes', async () => {
  const page = await source('pages/PositionEpisodePage.tsx');
  assert.match(page, /hidden=\{sampleSection !== "analysis"\}/);
  assert.match(page, /analysisVisited \|\| sampleSection === "analysis"/);
  assert.match(page, /initialMode="analysis"/);
  assert.match(page, /key=\{`\$\{episode.subjectId\}:\$\{episode.accountId\}:\$\{episode.episodeId\}`\}/);
  assert.match(page, /data.mode === "real_user" && episode.accountId/);
  assert.match(page, /onDecision=\{setSelectedDecisionId\}/);
  assert.doesNotMatch(page, /reviewService.start|synthetic_pair/);
});
test('owned Episode routes to DSA while shared, pair and legacy modes retain scoped review', async () => {
  const panel = await source('components/review/DecisionAnalysisWorkspace.tsx');
  assert.match(panel, /const supportsConversation = !scope\.share_id && !scope\.compare_pair/);
  assert.match(panel, /!scope\.data_mode \|\| scope\.data_mode === "real_user" \|\| scope\.data_mode === "synthetic_showcase"/);
  assert.match(panel, /\{supportsConversation \? \(live/);
  assert.match(panel, /to=\{`\/ask\?episode=\$\{encodeURIComponent\(base\.episode_id\)\}`\}/);
  assert.match(panel, /<Link[^>]*>\{t\("Analyze this investment"\)\}<\/Link>/);
  assert.match(panel, /: <Button size="sm" disabled=\{!live\} variant="primary" aria-pressed=\{mode === "analysis"\}/);
  assert.match(panel, /aria-pressed=\{mode === "analysis"\}/);
  assert.match(panel, /locale === "zh-CN" \? "笔记与历史" : "Notes & history"/);
  assert.match(panel, /\{supportsConversation \? <p[^>]*>\{locale === "zh-CN" \? "要继续连续对话/);
  assert.match(panel, /: <>\s*<label className="block space-y-2 text-sm">/);
  assert.match(panel, /\[consent, setConsent\] = useState\(false\)/);
  assert.match(panel, /if \(!live \|\| !consent \|\| !context \|\| busy \|\| loading\) return/);
  assert.match(panel, /onClick=\{\(\) => void analyze\(\)\}/);
  assert.match(panel, /guard.current.accepts\(ticket\)/);
  assert.doesNotMatch(panel, /setConsent\(true\)/);
  assert.doesNotMatch(panel, /\/ask\?episode=.*question|\/ask\?episode=.*send/);
});
test('answer shows versioned highlights before a collapsed canonical evidence appendix', async () => {
  const panel = await source('components/review/DecisionAnalysisWorkspace.tsx');
  const answer = await source('components/review/ReviewAnswer.tsx');
  assert.match(panel, /<ReviewAnswer answer=\{answer\} context=\{context\}/);
  assert.match(answer, /f.qualification/);
  assert.match(answer, /view.qualification/);
  assert.doesNotMatch(panel + answer, /Method and source details|Executed review tools|JSON.stringify\(fact.value/);
  assert.doesNotMatch(answer, /dangerouslySetInnerHTML/);
  assert.match(answer, /<details[^>]*data-review-evidence>/);
  assert.ok(answer.indexOf('view.findings.map') < answer.indexOf('data-review-evidence'));
  assert.doesNotMatch(answer, /<details[^>]*\bopen(?:[\s=>])/);
  assert.match(panel, /t\(h.claim\)/);
  assert.doesNotMatch(panel, /<p className="text-sm">\{t\(answer.question_kind\)\}/);
});
test('browser analysis exposes a disabled input without pretending to call a model', async () => {
  const panel = await source('components/review/DecisionAnalysisWorkspace.tsx');
  assert.match(panel, /<div className="review-offline">/);
  assert.match(panel, /\{!supportsConversation \? <>\s*<label/);
  assert.match(panel, /textarea className=\{inputClass\} disabled/);
  assert.match(panel, /No model has been called/);
});
