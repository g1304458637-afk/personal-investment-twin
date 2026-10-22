"""Offline, provenance-bound account-universe research; never a broker order."""
from dataclasses import replace
from datetime import date
from src.ledger import contracts as c
from src.strategy.data import Bar, CorporateAction, InstrumentSeries, SimulationData, UniverseMember
from src.strategy.engine import run_simulation
from src.strategy.report import enrich_summary, result_to_dict, buy_and_hold_curve
from src.strategy.sensitivity import sensitivity_report
from src.strategy.strategies.dual_ma import CloseSignal
from .ledger import read_csv, scope


def load(params, owned, stored=None):
    rows, file_sha = stored if stored is not None else read_csv(params.get('file_path'))
    columns={"row_type","symbol","market","security_type","date","open","high","low","close","volume","action","ex_date","ratio","cash_per_share","payment_date","tax_per_share"}
    rows=[{k:v for k,v in row.items() if k in columns} for row in rows]
    if params.get('corporate_actions_complete') is not True:
        raise ValueError('请核实并确认研究区间公司行动已完整提供；无行动也需明确确认。')
    source = c.text(params.get('source_ref'), 'source_ref')
    bars, actions = {}, []
    for row in rows:
        inst = c.security({**row, 'currency': params.get('currency')})
        key = inst['instrument_id']
        if key not in owned: raise ValueError('研究标的必须来自当前账户已记录的持仓或成交')
        if row.get('row_type', 'bar') == 'bar':
            day = date.fromisoformat(c.day(row.get('date'), 'date'))
            values = [float(c.number(row.get(k), k, positive=True)) for k in ('open','high','low','close')]
            volume = float(c.number(row.get('volume'), 'volume', nonnegative=True))
            bar = Bar(*values, volume=volume)
            if bar.high < max(bar.open,bar.close) or bar.low > min(bar.open,bar.close) or bar.low > bar.high:
                raise ValueError('inconsistent OHLC')
            bars.setdefault(key, []).append((day,bar))
        elif row.get('row_type') == 'action':
            kind = row.get('action')
            if kind not in {'split','cash_dividend'}: raise ValueError('研究目前仅支持拆并股、现金分红；配股换股等区间请拆分研究，不能伪造OHLC')
            ex = date.fromisoformat(c.day(row.get('ex_date'), 'ex_date'))
            pay = date.fromisoformat(c.day(row.get('payment_date'), 'payment_date')) if kind == 'cash_dividend' else None
            ratio = float(c.number(row.get('ratio'), 'ratio', positive=True)) if kind == 'split' else 1.0
            gross = float(c.number(row.get('cash_per_share'), 'cash_per_share', nonnegative=True)) if pay else 0.0
            tax = float(c.number(row.get('tax_per_share'), 'tax_per_share', nonnegative=True)) if pay else 0.0
            if pay and (pay < ex or tax > gross): raise ValueError('invalid dividend payment/tax')
            actions.append(CorporateAction(key,ex,kind,ratio,gross,pay,tax))
        else: raise ValueError('row_type must be bar or action')
    if not bars or len(bars) > 8: raise ValueError('需要1至8个标的的真实OHLCV')
    members, series, dates = {}, {}, set()
    seen = set()
    # Share changes precede a per-post-split-share dividend on the same day.
    actions.sort(key=lambda a:(a.ex_date,a.instrument,0 if a.action=='split' else 1))
    for a in actions:
        identity = (a.instrument,a.ex_date,a.action)
        if identity in seen: raise ValueError('duplicate corporate action')
        seen.add(identity)
        if a.instrument not in bars: raise ValueError('action has no price series')
    for key, pairs in sorted(bars.items()):
        pairs.sort(key=lambda x:x[0]); ds = tuple(d for d,_ in pairs)
        if len(ds) < 6 or len(set(ds)) != len(ds): raise ValueError('每标的至少6条、日期不能重复')
        for a in (a for a in actions if a.instrument==key):
            if a.ex_date not in ds: raise ValueError('corporate action ex-date requires an actual raw bar')
        splits=[a for a in actions if a.instrument==key and a.action=='split']
        factors=tuple(__import__('math').prod(1/a.ratio for a in splits if a.ex_date<=d) for d in ds)
        series[key]=InstrumentSeries(key,ds,tuple(b for _,b in pairs),tuple(b.close/f for (_,b),f in zip(pairs,factors)),factors)
        members[key]=UniverseMember(key,key,ds[0],None); dates.update(ds)
    dates.update(a.payment_date for a in actions if a.payment_date and a.payment_date<=max(dates))
    digest=c.fingerprint({'file_sha256':file_sha,'source':source,'currency':params.get('currency'),'actions_confirmed':True})
    return SimulationData(tuple(sorted(dates)),series,members,tuple(actions),digest), {'source_ref':source,'file_sha256':file_sha,'data_fingerprint':digest,
        'universe_policy':'当前账户已出现的证券；存在回顾选择及幸存者偏差，不代表当时全市场可选池',
        'normalized_rows_sha256':c.fingerprint(rows),'source_rows':rows,'price_type':'unadjusted_OHLCV','corporate_actions':'用户确认完整；不自动推断或联网核实'}


def spec_for(params):
    from src.strategy.composite import FORMULA_SCHEMA, build_formula_strategy_spec, build_user_strategy_spec, make_formula_provider, make_provider
    from src.strategy.strategies.dual_ma import build_dual_ma_spec
    from src.strategy.strategies.rsi_mr import build_rsi_mr_spec
    from src.strategy.strategies.t1 import build_t1_spec
    from src.strategy.strategies.turtle import build_turtle_spec
    raw=params.get('strategy')
    if isinstance(raw,dict):
        if raw.get('schema_version')==FORMULA_SCHEMA:
            spec, normalized=build_formula_strategy_spec(raw); provider=make_formula_provider(normalized)
        else:
            spec, normalized=build_user_strategy_spec(raw); provider=make_provider(normalized)
    else:
        builders={'dual_ma':build_dual_ma_spec,'rsi':build_rsi_mr_spec,'t1':build_t1_spec,'turtle':build_turtle_spec}
        builder=builders.get(params.get('strategy_id','dual_ma'))
        if builder is None: raise ValueError('unknown research strategy')
        spec,provider=builder(),None
    # Only explicitly requested execution assumptions may replace a strategy's defaults.
    allowed={'initial_cash','commission_rate','min_commission','stamp_duty_rate','slippage_rate','lot_size','price_limit_pct'}
    assumptions=params.get('execution_assumptions',{})
    if not isinstance(assumptions,dict) or set(assumptions)-allowed: raise ValueError('invalid execution assumptions')
    normalized={k:float(c.number(v,k,positive=k in {'initial_cash','lot_size'},nonnegative=True)) for k,v in assumptions.items()}
    if 'lot_size' in normalized and normalized['lot_size']!=int(normalized['lot_size']): raise ValueError('lot_size must be integer')
    for k in ('commission_rate','stamp_duty_rate','slippage_rate','price_limit_pct'):
        if normalized.get(k,0)>0.5: raise ValueError('execution rate exceeds 50%')
    return replace(spec,params={**spec.params,**normalized}),provider


def window(data,start,end,label):
    series={}
    for key,item in data.series.items():
        pairs=[(d,b,a,f) for d,b,a,f in zip(item.dates,item.bars,item.adjusted_close,item.split_factors) if start<=d<=end]
        if pairs:
            factors=tuple(__import__('math').prod(1/a.ratio for a in data.actions if a.instrument==key and a.action=='split' and start<=a.ex_date<=p[0]) for p in pairs)
            series[key]=InstrumentSeries(key,tuple(p[0] for p in pairs),tuple(p[1] for p in pairs),tuple(p[1].close/f for p,f in zip(pairs,factors)),factors)
    if not series: raise ValueError('research window has no bars')
    return SimulationData(tuple(d for d in data.dates if start<=d<=end),series,
        {k:replace(data.members[k],list_date=max(start,data.members[k].list_date)) for k in series},
        tuple(a for a in data.actions if a.instrument in series and start<=a.ex_date<=end),data.fingerprint+':'+label)


def net_benchmark(spec,data):
    attempted=set(); count=len(data.members)
    def provider(params, dataset, day, held, pending_buys, **kwargs):
        candidates=[]
        for key,item in sorted(dataset.series.items()):
            if key in attempted or item.bar_on(day) is None: continue
            attempted.add(key)
            quantity=int(float(params['initial_cash'])/count/item.bar_on(day).close/int(params['lot_size']))*int(params['lot_size'])
            candidates.append(CloseSignal(key,'entry_candidate',1.0,'预先等额分配；首次收盘产生信号，下一实际开盘尝试一次',(),
                reason_code='net_buy_hold',intended_quantity=quantity))
        return [],candidates
    benchmark=replace(spec,strategy_id='research_net_buy_hold',params={**spec.params,'max_positions':count,'stop_loss_pct':0.0,'position_fraction':1.0/count})
    return run_simulation(benchmark,data,signal_provider=provider)


def run(product,params):
    subject,account=scope(params); ledger=product.ledger_runtime(); profile=product.repo.ledger_profile(subject,account)
    if profile is None: raise ValueError('真实账本未启用')
    if params.get('mode')=='pretrade':
        from src.ledger.pretrade import check
        return check(profile,product.repo.ledger_events(subject,account),product.repo.executions(subject,account),product.repo.prices(subject,account),params.get('proposed_trade',{}),params.get('as_of'))
    if params.get('mode')=='history':
        snapshot=ledger.snapshot(subject,account,params.get('as_of')); journal=product.repo.journal_entries(subject,account)
        return {'schema_version':'ledger_history.v1','snapshot':snapshot,'journal':journal,
            'source_fingerprint':ledger.state_fingerprint(subject,account),
            'summary':{'closed_episodes':sum(bool(e['closed_at']) for e in snapshot['episodes']),
                'plans':sum(j['entry_type']=='plan' for j in journal),'linked_executions':sum(j['entry_type']=='link' for j in journal),
                'verified_before_execution':sum(j.get('timing')=='before_execution' for j in journal)},
            'limitations':['集中度只反映已记录证券，不穿透基金；资金流入不算收益。','缺少出入金时点前后估值时，不输出精确时间加权收益或收益率回撤。']}
    owned=set(ledger.instruments(subject,account))|{x.instrument.instrument_id for x in product.repo.executions(subject,account)}
    stored=None
    if params.get('mode')=='rerun':
        saved=next((j for j in product.repo.journal_entries(subject,account) if j['entry_type']=='research' and j.get('run_id')==params.get('run_id')),None)
        if saved is None: raise ValueError('研究记录不存在或不属于当前账户')
        if 'source_rows' not in saved or c.fingerprint(saved['source_rows'])!=saved['provenance'].get('normalized_rows_sha256'):
            raise ValueError('此旧研究没有可验证的输入快照，请重新提供CSV')
        stored=(saved['source_rows'],saved['provenance']['file_sha256'])
        params={**saved['request'],**{'subject_id':subject,'account_id':account,'mode':'strategy'}}
    elif params.get('mode')!='strategy': raise ValueError('unsupported research mode')
    data,provenance=load({**params,'currency':profile['currency']},owned,stored)
    source_rows=provenance.pop('source_rows')
    spec,provider=spec_for(params)
    cut=date.fromisoformat(c.day(params.get('test_start'),'test_start'))
    train=window(data,min(data.dates),date.fromordinal(cut.toordinal()-1),'train')
    test=window(data,cut,max(data.dates),'test')
    if len(train.dates)<3 or len(test.dates)<3: raise ValueError('训练、样本外均至少3个交易日')
    def report(part):
        result=run_simulation(spec,part,signal_provider=provider)
        # Rebuild a causal prefix rather than retaining future split factors.
        midpoint=part.dates[len(part.dates)//2]
        prefix=window(part,min(part.dates),date.fromordinal(midpoint.toordinal()-1),'prefix-check')
        check_result=run_simulation(spec,prefix,signal_provider=provider)
        full_payload,prefix_payload=result_to_dict(result),result_to_dict(check_result)
        for field in ('days','fills'):
            date_key='date' if field=='days' else 'day'
            observed=[r for r in full_payload[field] if r[date_key]<midpoint.isoformat()]
            if observed!=prefix_payload[field]: raise ValueError('future-function prefix check failed; research refused')
        benchmark=net_benchmark(spec,part)
        return {'future_check':{'status':'passed','cutoff':midpoint.isoformat()},'summary':result.summary,'equity':[{'date':d.day.isoformat(),'equity':d.equity,'cash':d.cash} for d in result.days],
            'fills':result_to_dict(result)['fills'], 'net_benchmark':{'summary':benchmark.summary,
                'equity':[{'date':d.day.isoformat(),'equity':d.equity} for d in benchmark.days]},
            'gross_benchmark':buy_and_hold_curve(part,float(spec.params['initial_cash']))}
    sensitivity=None
    if params.get('parameter'):
        if provider is not None and params['parameter'] not in {'commission_rate','slippage_rate'}: raise ValueError('自建策略目前支持佣金、滑点敏感度；其他参数请分别锁定规格运行')
        sensitivity=sensitivity_report(spec,train,parameter=params['parameter'],values=params.get('values'))
        sensitivity['limitations']=[x for x in sensitivity['limitations'] if '合成行情' not in x]+['仅在训练区间改变假设；不按样本外结果挑选参数。']
    saved_request={k:v for k,v in params.items() if k in {'source_ref','corporate_actions_complete','test_start','strategy_id','strategy','parameter','values','execution_assumptions'}}
    result={'request':saved_request,'source_rows':source_rows,'schema_version':'account_research.v1','subject_id':subject,'account_id':account,
        'provenance':provenance,'strategy':spec.as_dict(),'test_start':cut.isoformat(),'train':report(train),'test':report(test),'sensitivity':sensitivity,
        'limitations':['这是已知历史的时间切分检验，不能声称事前封存或真正未见数据；再次改参数后必须重新声明。',
            '两段独立现金起步，样本外指标从零暖机；不继承训练持仓，也不偷看训练末端后才产生的信号。',
            '净基准与策略共用费用、税、整手、滑点及涨跌停假设；首次收盘发信号、下一开盘尝试一次，失败留现金，不保证成交。',
            '仅用户提供拆并股与逐股现金分红；其他公司行动不能自动重放。分红按除权前日持仓、每股金额记应收，到账扣所填税。',
            '历史成交换手及利润因子按交易损益统计，分红计入净值、不计入平仓胜率；末尾应收分红仍计资产。',
            '标的池来自当前账户，存在选择偏差；不连接券商，不产生下单建议。']}
    result['run_id']='research_'+c.fingerprint(result)
    from datetime import datetime,timezone
    from src.persistence.repository import _dump
    with product.repo.transaction() as db:
        db.execute('INSERT OR IGNORE INTO account_journal_entries VALUES(?,?,?,?,?,?)',(subject,account,result['run_id'],'research',_dump(result),datetime.now(timezone.utc).isoformat()))
    return result
