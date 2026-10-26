import { validatePublishedInvestmentCard } from './investmentSharing.ts';
import type { PublishedInvestmentCard } from './investmentSharing.ts';

export interface CommunityCompany { id: string; name: string; ticker: string; sector: string }
export interface CommunityEvidence { id: string; companyId: string; title: string; locator: string; excerpt: string; period: string }
export interface CommunityReply { id: string; author: string; text: string; createdAt: string; evidenceId?: string; stance: '补充证据' | '提出反证' | '交流观点' }
export interface CommunityUpdate { id: string; title: string; body: string; date: string; status: '持续观察' | '论点增强' | '需要修正'; evidenceId?: string }
export interface CommunityPost { id: string; companyId: string; title: string; author: string; role: string; publishedAt: string; summary: string; thesis: string; risk: string; watchpoints: string[]; evidenceIds: string[]; topic: string; replies: CommunityReply[]; updates: CommunityUpdate[]; isOwn?: boolean; investment?: PublishedInvestmentCard }
export interface CommunityState { version: 1; posts: CommunityPost[]; followedCompanyIds: string[]; followedPostIds: string[]; savedPostIds: string[] }
export interface CommunityDraft { companyId: string; title: string; thesis: string; risk: string; watch: string; evidenceIds: string[] }

export const companies: CommunityCompany[] = [
  { id: 'catl', name: '宁德时代', ticker: '300750.SZ', sector: '动力电池' },
  { id: 'moutai', name: '贵州茅台', ticker: '600519.SH', sector: '白酒' },
  { id: 'tencent', name: '腾讯控股', ticker: '0700.HK', sector: '互联网服务' },
];

// Every excerpt is invented for this offline interaction demo; none represents a real report quotation.
export const evidences: CommunityEvidence[] = [
  { id: 'catl-e1', companyId: 'catl', title: '经营现金流观察卡（演示）', locator: '演示素材·主题摘要', excerpt: '【SYNTHETIC / 演示改写】观察经营现金流与利润的匹配程度，并追踪营运资本变化。', period: '示例观察期' },
  { id: 'catl-e2', companyId: 'catl', title: '产能利用率观察卡（演示）', locator: '演示素材·研究问题', excerpt: '【SYNTHETIC / 演示改写】新增产能的爬坡节奏可能影响阶段性效率，需结合后续披露验证。', period: '后续披露待观察' },
  { id: 'moutai-e1', companyId: 'moutai', title: '渠道库存观察卡（演示）', locator: '演示素材·主题摘要', excerpt: '【SYNTHETIC / 演示改写】跟踪渠道库存与终端动销是否出现方向分化。', period: '示例观察期' },
  { id: 'tencent-e1', companyId: 'tencent', title: '业务组合观察卡（演示）', locator: '演示素材·研究问题', excerpt: '【SYNTHETIC / 演示改写】比较不同业务的投入、变现与资本配置节奏，避免用单一指标概括整体。', period: '后续披露待观察' },
];

const fixtures: CommunityPost[] = [
  {
    id: 'catl-cashflow', companyId: 'catl', title: '从现金流质量开始，拆解电池业务的跟踪框架', author: '林间观察', role: '长期研究者', publishedAt: '2026-10-20',
    summary: '一份虚构的研究过程示例：先看利润与现金流的匹配，再拆解产能爬坡和营运资本，结论保持待验证。',
    thesis: '【虚构示例】我倾向把现金流质量作为观察业务韧性的入口，而不是直接把某一期表现外推。若现金转化与利润长期背离，应该回到应收、库存、付款节奏等环节找原因。接下来再看新增产能是否按计划爬坡，以及产品结构变化能否解释效率差异。这个框架只提出可检验的问题，不构成买卖判断。',
    risk: '样本期和指标口径可能不一致；产业周期、客户结构及会计确认节奏都会改变表面关系。单条演示素材不足以支持结论，且这里没有使用真实财务数据。',
    watchpoints: ['后续披露中现金流与利润是否持续匹配', '营运资本变化能否由业务节奏解释', '产能爬坡信息是否与效率变化相互印证'],
    evidenceIds: ['catl-e1', 'catl-e2'], topic: '财报研究',
    replies: [
      { id: 'catl-r1', author: '阿禾', text: '补一个检验思路：把营运资本变化拆开看，避免只比较现金流总额。', createdAt: '2026-10-21', evidenceId: 'catl-e1', stance: '补充证据' },
      { id: 'catl-r2', author: '北岸', text: '提出反证：若现金流差异主要来自结算时点，单期背离并不能说明经营质量走弱。', createdAt: '2026-10-22', evidenceId: 'catl-e1', stance: '提出反证' },
      { id: 'catl-r3', author: '青石', text: '建议把产能利用与产品结构分开记录，后续更容易复盘因果假设。', createdAt: '2026-10-22', stance: '交流观点' },
    ],
    updates: [
      { id: 'catl-u1', title: '补充观察边界', body: '单期现金流波动先作为待解释现象，不据此调整长期判断。', date: '2026-10-21', status: '持续观察', evidenceId: 'catl-e1' },
      { id: 'catl-u2', title: '加入产能爬坡问题', body: '把新增产能的进度与效率变化并列追踪，等待后续材料交叉验证。', date: '2026-10-23', status: '论点增强', evidenceId: 'catl-e2' },
    ],
  },
  { id: 'moutai-channel', companyId: 'moutai', title: '渠道信号要和终端反馈一起看', author: '一杯清茶', role: '消费观察', publishedAt: '2026-10-18', summary: '虚构示例：把渠道库存和终端动销作为一组问题持续观察。', thesis: '【虚构示例】渠道环节的变化需要和终端反馈交叉验证，不能由单一渠道信号推导整体需求。', risk: '演示材料不含真实数据，观察口径可能存在滞后。', watchpoints: ['库存与动销是否同向', '不同渠道反馈是否一致'], evidenceIds: ['moutai-e1'], topic: '行业观察', replies: [], updates: [] },
  { id: 'tencent-mix', companyId: 'tencent', title: '业务组合研究先明确各自的驱动因素', author: '远山', role: '公司研究', publishedAt: '2026-10-16', summary: '虚构示例：用业务投入、变现和资本配置问题搭建复盘清单。', thesis: '【虚构示例】业务组合的变化需要分项观察，再讨论整体资源配置是否与长期重点一致。', risk: '不同业务口径与周期差异较大，不能直接横向类比。', watchpoints: ['业务投入与变现节奏', '资本配置逻辑是否延续'], evidenceIds: ['tencent-e1'], topic: '研究方法', replies: [], updates: [] },
  { id: 'my-research', companyId: 'moutai', title: '我的渠道研究问题清单', author: '我', role: '个人研究', publishedAt: '2026-10-23', summary: '虚构的个人研究示例，用于展示作者标记和后续更新。', thesis: '【虚构示例】先列出能被后续材料验证的问题，暂不形成结论。', risk: '目前只有演示素材，证据不足以回答研究问题。', watchpoints: ['后续是否出现可核验的终端反馈'], evidenceIds: ['moutai-e1'], topic: '行业观察', replies: [], updates: [], isOwn: true },
];

export function createInitialCommunityState(): CommunityState {
  return { version: 1, posts: fixtures.map(clonePost), followedCompanyIds: ['catl'], followedPostIds: ['catl-cashflow'], savedPostIds: [] };
}

function clonePost(post: CommunityPost): CommunityPost {
  return { ...post, watchpoints: [...post.watchpoints], evidenceIds: [...post.evidenceIds], replies: post.replies.map(x => ({ ...x })), updates: post.updates.map(x => ({ ...x })), ...(post.investment ? { investment: structuredClone(post.investment) } : {}) };
}
const text = (v: unknown, max = 4000): v is string => typeof v === 'string' && v.trim().length > 0 && v.trim().length <= max;
const evidenceFor = (id: string, companyId: string) => evidences.some(e => e.id === id && e.companyId === companyId);
const validStatus = (v: unknown): v is CommunityUpdate['status'] => v === '持续观察' || v === '论点增强' || v === '需要修正';
const validStance = (v: unknown): v is CommunityReply['stance'] => v === '补充证据' || v === '提出反证' || v === '交流观点';
const investmentPostFields = ['id', 'companyId', 'title', 'author', 'role', 'publishedAt', 'summary', 'thesis', 'risk', 'watchpoints', 'evidenceIds', 'topic', 'replies', 'updates', 'isOwn', 'investment'];

function validPost(value: unknown): value is CommunityPost {
  if (!value || typeof value !== 'object') return false;
  const p = value as CommunityPost;
  const portfolio = p.companyId === 'portfolio';
  return typeof p.id === 'string' && (portfolio ? validatePublishedInvestmentCard(p.investment) && Object.keys(p).every(k => investmentPostFields.includes(k)) : companies.some(c => c.id === p.companyId) && p.investment === undefined) && text(p.title, 160) && text(p.author, 80) && text(p.role, 80) && text(p.publishedAt, 30) && text(p.summary, 500) && text(p.thesis) && text(p.risk) && text(p.topic, 80) && (p.isOwn === undefined || typeof p.isOwn === 'boolean') && Array.isArray(p.watchpoints) && p.watchpoints.length > 0 && p.watchpoints.every(x => text(x, 240)) && Array.isArray(p.evidenceIds) && (portfolio ? p.evidenceIds.length === 0 : p.evidenceIds.every(id => evidenceFor(id, p.companyId))) && Array.isArray(p.replies) && p.replies.every(r => r && text(r.id, 100) && text(r.author, 80) && text(r.text, 1200) && text(r.createdAt, 30) && validStance(r.stance) && (r.evidenceId === undefined || (!portfolio && evidenceFor(r.evidenceId, p.companyId)))) && Array.isArray(p.updates) && p.updates.every(u => u && text(u.id, 100) && text(u.title, 160) && text(u.body, 1200) && text(u.date, 30) && validStatus(u.status) && (u.evidenceId === undefined || (!portfolio && evidenceFor(u.evidenceId, p.companyId))));
}

export function loadCommunityState(raw: string | null): CommunityState {
  if (raw === null) return createInitialCommunityState();
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object') return createInitialCommunityState();
    const s = parsed as CommunityState;
    const postIds = new Set(Array.isArray(s.posts) ? s.posts.map(p => p?.id) : []);
    if (s.version !== 1 || !Array.isArray(s.posts) || !s.posts.every(validPost) || new Set(s.posts.map(p => p.id)).size !== s.posts.length || !Array.isArray(s.followedCompanyIds) || !s.followedCompanyIds.every(id => companies.some(c => c.id === id)) || !Array.isArray(s.followedPostIds) || !s.followedPostIds.every(id => postIds.has(id)) || !Array.isArray(s.savedPostIds) || !s.savedPostIds.every(id => postIds.has(id))) return createInitialCommunityState();
    return { version: 1, posts: s.posts.map(clonePost), followedCompanyIds: [...s.followedCompanyIds], followedPostIds: [...s.followedPostIds], savedPostIds: [...s.savedPostIds] };
  } catch { return createInitialCommunityState(); }
}

function requireEvidence(ids: string[], companyId: string): void {
  if (!Array.isArray(ids) || !ids.every(id => typeof id === 'string' && evidenceFor(id, companyId))) throw new Error('引用材料必须属于所选公司');
}
function requirePost(state: CommunityState, postId: string): CommunityPost {
  const post = state.posts.find(p => p.id === postId);
  if (!post) throw new Error('找不到讨论');
  return post;
}

export function publishCommunityPost(state: CommunityState, draft: CommunityDraft): CommunityState {
  if (!companies.some(c => c.id === draft.companyId) || !text(draft.title, 160) || !text(draft.thesis, 4000) || !text(draft.risk, 1600) || !text(draft.watch, 1000)) throw new Error('请填写公司、标题、论点、风险和观察要点');
  requireEvidence(draft.evidenceIds, draft.companyId);
  const post: CommunityPost = { id: crypto.randomUUID(), companyId: draft.companyId, title: draft.title.trim(), author: '我', role: '个人研究', publishedAt: new Date().toISOString().slice(0, 10), summary: draft.thesis.trim().slice(0, 240), thesis: draft.thesis.trim(), risk: draft.risk.trim(), watchpoints: draft.watch.split(/[\n；;]/).map(x => x.trim()).filter(Boolean), evidenceIds: [...draft.evidenceIds], topic: '财报研究', replies: [], updates: [], isOwn: true };
  if (!post.watchpoints.length || post.watchpoints.some(x => x.length > 240)) throw new Error('请填写有效的观察要点');
  return { ...state, posts: [...state.posts.map(clonePost), post] };
}

export function publishInvestmentPost(state: CommunityState, card: PublishedInvestmentCard, narrative: { title: string; thesis: string; risk: string; watch: string }): CommunityState {
  if (!validatePublishedInvestmentCard(card)) throw new Error('投资分享卡片无效，无法发布');
  if (!text(narrative?.title, 160) || !text(narrative?.thesis, 4000) || !text(narrative?.risk, 1600) || !text(narrative?.watch, 1000)) throw new Error('请填写标题、分享内容、风险和观察要点');
  const watchpoints = narrative.watch.split(/[\n；;]/).map(x => x.trim()).filter(Boolean);
  if (!watchpoints.length || watchpoints.some(x => x.length > 240)) throw new Error('请填写有效的观察要点');
  const topic = { episode: '投资经历', holdings: '持仓快照', period: '阶段表现' }[card.kind];
  const post: CommunityPost = {
    id: crypto.randomUUID(), companyId: 'portfolio', title: narrative.title.trim(), author: '我', role: '个人投资',
    publishedAt: new Date().toISOString(), summary: narrative.thesis.trim().slice(0, 240), thesis: narrative.thesis.trim(),
    risk: narrative.risk.trim(), watchpoints, evidenceIds: [], topic, replies: [], updates: [], isOwn: true,
    investment: structuredClone(card),
  };
  return { ...state, posts: [...state.posts.map(clonePost), post] };
}

export function storeInvestmentPost(storage: Pick<Storage, 'getItem' | 'setItem'>, card: PublishedInvestmentCard, narrative: { title: string; thesis: string; risk: string; watch: string }): CommunityState {
  const key = 'toujing-community-demo-v1';
  const state = publishInvestmentPost(loadCommunityState(storage.getItem(key)), card, narrative);
  storage.setItem(key, JSON.stringify(state));
  return state;
}

export function withdrawInvestmentPost(state: CommunityState, postId: string): CommunityState {
  const post = requirePost(state, postId);
  if (post.companyId !== 'portfolio' || post.isOwn !== true || post.author !== '我' || !validatePublishedInvestmentCard(post.investment)) throw new Error('只能撤回自己的投资分享');
  return {
    ...state, posts: state.posts.filter(p => p.id !== postId).map(clonePost),
    followedPostIds: state.followedPostIds.filter(id => id !== postId),
    savedPostIds: state.savedPostIds.filter(id => id !== postId),
  };
}

export function addCommunityReply(state: CommunityState, postId: string, input: { text: string; evidenceId?: string; stance: CommunityReply['stance'] }): CommunityState {
  const post = requirePost(state, postId);
  if (!text(input.text, 1200) || !validStance(input.stance)) throw new Error('请填写有效回复和交流立场');
  if (input.evidenceId && !evidenceFor(input.evidenceId, post.companyId)) throw new Error('引用材料必须属于该讨论公司');
  const reply: CommunityReply = { id: crypto.randomUUID(), author: '我', text: input.text.trim(), createdAt: new Date().toISOString().slice(0, 10), stance: input.stance, ...(input.evidenceId ? { evidenceId: input.evidenceId } : {}) };
  return { ...state, posts: state.posts.map(p => p.id === postId ? { ...clonePost(p), replies: [...p.replies.map(x => ({ ...x })), reply] } : clonePost(p)) };
}

export function addCommunityUpdate(state: CommunityState, postId: string, input: { title: string; body: string; status: CommunityUpdate['status']; evidenceId?: string }): CommunityState {
  const post = requirePost(state, postId);
  if (post.isOwn !== true) throw new Error('只能更新自己的讨论');
  if (!text(input.title, 160) || !text(input.body, 1200) || !validStatus(input.status)) throw new Error('请填写有效的更新标题、内容和状态');
  if (input.evidenceId && !evidenceFor(input.evidenceId, post.companyId)) throw new Error('引用材料必须属于该讨论公司');
  const update: CommunityUpdate = { id: crypto.randomUUID(), title: input.title.trim(), body: input.body.trim(), date: new Date().toISOString().slice(0, 10), status: input.status, ...(input.evidenceId ? { evidenceId: input.evidenceId } : {}) };
  return { ...state, posts: state.posts.map(p => p.id === postId ? { ...clonePost(p), updates: [...p.updates.map(x => ({ ...x })), update] } : clonePost(p)) };
}
