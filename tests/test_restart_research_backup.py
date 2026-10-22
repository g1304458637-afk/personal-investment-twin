from datetime import date, timedelta
import io
import json
from pathlib import Path
import sqlite3
import pytest
from test_real_account_ledger import SCOPE, OPEN, INITIAL, SEC, row, quote, commit
from src.core.canonical_execution import canonical_execution, execution_time, instrument_ref, fee_fact
from src.persistence.repository import _dump, _execution_payload
from toujing_core_runtime.product import ProductRuntime
from toujing_core_runtime.backup import BackupRuntime, recover_pending
from toujing_core_runtime.research import run, load, net_benchmark, spec_for
from src.ledger.pretrade import check


def setup(tmp_path):
    product=ProductRuntime(tmp_path/'facts.sqlite3')
    commit(product,'opening',opening=OPEN,records=[INITIAL])
    return product


def trade(product,identifier,day,side='SELL',quantity=100,fee=1):
    x=canonical_execution(**SCOPE,instrument=instrument_ref(local_symbol='600000',market='XSHG',security_type='equity',currency='CNY'),
        event_time=execution_time(day,precision='second' if 'T' in day else 'date',source_timezone='Asia/Shanghai'),side=side,
        executed_quantity=quantity,executed_price=12,fee=fee_fact(fee,currency='CNY'),source='test',source_record_ref=identifier,execution_id=identifier)
    with product.repo.transaction() as db:
        db.execute('INSERT INTO canonical_executions VALUES(?,?,?,?,?,?,?)',(x.execution_id,SCOPE['subject_id'],SCOPE['account_id'],x.event_time.ordering_key,x.execution_sequence,x.instrument.instrument_id,_dump(_execution_payload(x))))
    return x


def csv(tmp_path,count=80,action=False):
    path=tmp_path/'bars.csv';rows=['row_type,symbol,market,security_type,date,open,high,low,close,volume,action,ex_date,ratio,cash_per_share,payment_date,tax_per_share']
    for i in range(count):
        day=(date(2025,1,1)+timedelta(days=i)).isoformat(); price=12 if not action or i<5 else 11
        rows.append(f'bar,600000,XSHG,equity,{day},{price},{price+1},{price-1},{price},1000,,,,,,')
    if action:rows.append('action,600000,XSHG,equity,,,,,,,cash_dividend,2025-01-06,,1,2025-01-09,0.1')
    path.write_text('\n'.join(rows));return path


def test_pretrade_is_hypothetical_and_scope_cutoff(tmp_path):
    p=setup(tmp_path); ledger=p.ledger_runtime();fp=ledger.state_fingerprint(**SCOPE) if False else ledger.state_fingerprint(SCOPE['subject_id'],SCOPE['account_id'])
    args={**SEC,'side':'BUY','quantity':'10','price':'12','fee':'1'}
    result=check(ledger.repo.ledger_profile(**SCOPE) if False else ledger.repo.ledger_profile(SCOPE['subject_id'],SCOPE['account_id']),ledger.repo.ledger_events(SCOPE['subject_id'],SCOPE['account_id']),(),(),args,'2025-01-02')
    assert result['status']=='simulated' and result['before']['equity']=='11200' and result['after']['cash']=='9879'
    assert result['after']['equity']=='11199' and not result['similar_history']
    assert ledger.state_fingerprint(SCOPE['subject_id'],SCOPE['account_id'])==fp
    result=check(ledger.repo.ledger_profile(SCOPE['subject_id'],SCOPE['account_id']),ledger.repo.ledger_events(SCOPE['subject_id'],SCOPE['account_id']),(),(),{**args,'side':'SELL','quantity':'101'},'2025-01-02')
    assert result['status']=='blocked' and result['after'] is None
    p.close()


def test_journal_server_time_and_retrospective_association(tmp_path):
    p=setup(tmp_path)
    commit(p,'plan',entry={'entry_id':'plan-1','text':'观察','invalidation':'跌破假设','recorded_at':'2000-01-01', 'proposed_trade':{**SEC,'side':'SELL','quantity':'100','price':'12','fee':'1'}})
    entries=p.repo.journal_entries(SCOPE['subject_id'],SCOPE['account_id']);assert entries[0]['recorded_at']>'2026' and entries[0]['entry_type']=='plan'
    x=trade(p,'past','2025-01-02T10:00:00')
    commit(p,'link',entry={'entry_id':'link','text':'关联历史成交','plan_id':'plan-1','execution_id':x.execution_id})
    link=p.repo.journal_entries(SCOPE['subject_id'],SCOPE['account_id'])[-1]
    assert link['timing']=='retrospective' and link['same_side'] and link['same_instrument']
    with pytest.raises(ValueError):commit(p,'link',entry={'entry_id':'link2','text':'重复关联','plan_id':'plan-1','execution_id':x.execution_id})
    with pytest.raises(ValueError):commit(p,'note',entry={'entry_id':'bad','text':'跨账户','plan_id':'foreign'})
    p.close()


def test_encrypted_backup_restore_restart_and_preferences(tmp_path):
    p=setup(tmp_path);b=BackupRuntime(p)
    commit(p,'note',entry={'entry_id':'note','text':'用户复盘'})
    # Separate chat archive is included using SQLite online backup.
    from toujing_core_runtime.chat_archive import ChatArchive
    archive=ChatArchive(b.chat)
    with archive.connect() as db: db.execute('INSERT INTO validated_conversations_v1 VALUES(?,?)',('scope','{}'))
    path=tmp_path/'account.tjbackup';args={'file_path':str(path),'backup_password':'long-private-password','preferences':{'toujing.theme':'light','toujing.userStrategies':'[]'}}
    created=b.create(args);assert created['encrypted'] and '用户复盘'.encode() not in path.read_bytes()
    with pytest.raises(ValueError,match='密码'):b.preview({**args,'backup_password':'incorrect-password'})
    before=b.preview(args)
    commit(p,'events',records=[row('deposit','later','2025-01-02',amount='500')])
    with pytest.raises(ValueError,match='失效'):b.restore({**args,'expected_preview_fingerprint':before['preview_fingerprint'],'confirm_replace_all':True})
    preview=b.preview(args);restored=b.restore({**args,'expected_preview_fingerprint':preview['preview_fingerprint'],'confirm_replace_all':True})
    assert restored['restored'] and p.ledger_runtime().snapshot(SCOPE['subject_id'],SCOPE['account_id'])['cash']=='10000'
    assert b.pending({})['pending']['preferences']['toujing.theme']=='light'
    assert not p.repo.path.with_name(p.repo.path.name+'.restore-pending.json').exists()
    p.close();p=ProductRuntime(tmp_path/'facts.sqlite3');assert p.repo.journal_entries(SCOPE['subject_id'],SCOPE['account_id'])[0]['text']=='用户复盘'
    assert BackupRuntime(p).pending({})['pending']['restore_id']==restored['restore_id']
    BackupRuntime(p).ack({'restore_id':restored['restore_id']});assert BackupRuntime(p).pending({})['pending'] is None
    p.close()


def test_research_oos_sensitivity_persist_and_owned_universe(tmp_path):
    p=setup(tmp_path);path=csv(tmp_path)
    args={**SCOPE,'mode':'strategy','file_path':str(path),'source_ref':'test raw OHLCV','corporate_actions_complete':True,'test_start':'2025-02-10','strategy_id':'dual_ma','parameter':'commission_rate','values':[0,0.001]}
    result=run(p,args)
    assert result['provenance']['price_type']=='unadjusted_OHLCV'
    assert max(r['date'] for r in result['train']['equity'])<result['test_start']<=min(r['date'] for r in result['test']['equity'])
    assert result['test']['equity'][0]['equity']==1000000
    assert result['sensitivity'] and '合成' not in json.dumps(result['sensitivity'],ensure_ascii=False)
    assert p.repo.journal_entries(SCOPE['subject_id'],SCOPE['account_id'])[0]['run_id']==result['run_id']
    # Editing only test-period prices cannot alter train fills or sensitivity.
    content=path.read_text();path.write_text(content.replace('2025-03-01,12,13,11,12','2025-03-01,14,15,13,14'))
    modified=run(p,args);assert modified['train']==result['train'] and modified['sensitivity']==result['sensitivity']
    with pytest.raises(ValueError):run(p,{**args,'corporate_actions_complete':False})
    path.write_text(content.replace('600000','600001'))
    with pytest.raises(ValueError,match='当前账户'):run(p,args)
    p.close()


def test_research_dividend_receivable_payment_and_tax(tmp_path):
    p=setup(tmp_path);path=csv(tmp_path,20,action=True)
    data,_=load({'file_path':str(path),'currency':'CNY','source_ref':'test','corporate_actions_complete':True},set(p.ledger_runtime().instruments(SCOPE['subject_id'],SCOPE['account_id'])))
    spec,_=spec_for({'execution_assumptions':{'initial_cash':10000,'commission_rate':0,'min_commission':0,'stamp_duty_rate':0,'slippage_rate':0,'lot_size':1}})
    result=net_benchmark(spec,data)
    assert result.fills and result.fills[0].day==date(2025,1,2)
    entitlement=next(d for d in result.days if d.day==date(2025,1,6));paid=next(d for d in result.days if d.day==date(2025,1,9))
    qty=result.fills[0].quantity
    assert entitlement.equity==pytest.approx(10000) and paid.equity==pytest.approx(10000-qty*0.1)
    assert any(e['kind']=='dividend_payment' for e in paid.events)
    p.close()

@pytest.mark.parametrize('day,timing',[('2030-01-02T10:00:00','before_execution'),('2025-01-02','unverifiable_date_only')])
def test_plan_link_uses_actual_time_precision(tmp_path,day,timing):
    p=setup(tmp_path)
    commit(p,'plan',entry={'entry_id':'plan','text':'计划','invalidation':'失效','proposed_trade':{**SEC,'side':'SELL','quantity':'100','price':'12','fee':'1'}})
    trade(p,'fill',day)
    commit(p,'link',entry={'entry_id':'link','text':'关联','plan_id':'plan','execution_id':'fill'})
    assert p.repo.journal_entries(SCOPE['subject_id'],SCOPE['account_id'])[-1]['timing']==timing
    p.close()


def test_unknown_fee_never_becomes_precise_zero_and_void_is_audited(tmp_path):
    p=setup(tmp_path);trade(p,'unknown','2025-01-02',fee=None)
    result=p.ledger_runtime().snapshot(SCOPE['subject_id'],SCOPE['account_id'])
    assert result['cash'] is None and result['equity'] is None and result['fees'] is None
    commit(p,'void',target_event_id='execution:unknown',reason='券商原件核对待重录')
    assert len(p.repo.executions(SCOPE['subject_id'],SCOPE['account_id']))==1
    assert p.ledger_runtime().snapshot(SCOPE['subject_id'],SCOPE['account_id'])['cash']=='10000'
    p.close()


def test_interrupted_restore_rolls_back_before_open_on_restart(tmp_path,monkeypatch):
    import toujing_core_runtime.backup as module
    p=setup(tmp_path);b=BackupRuntime(p);args={'file_path':str(tmp_path/'old.tjbackup'),'backup_password':'long-private-password','preferences':{}}
    b.create(args);commit(p,'events',records=[row('deposit','new','2025-01-02',amount='500')])
    original=module._copy
    def interrupted(source,target):
        if Path(target)==b.chat: raise KeyboardInterrupt('simulated power loss after facts replacement')
        return original(source,target)
    preview=b.preview(args)
    with monkeypatch.context() as m:
        m.setattr(module,'_copy',interrupted)
        with pytest.raises(KeyboardInterrupt):b.restore({**args,'expected_preview_fingerprint':preview['preview_fingerprint'],'confirm_replace_all':True})
    assert p.repo.path.with_name(p.repo.path.name+'.restore-pending.json').exists()
    p.close();p=ProductRuntime(tmp_path/'facts.sqlite3')
    assert p.ledger_runtime().snapshot(SCOPE['subject_id'],SCOPE['account_id'])['cash']=='10500'
    assert not p.repo.path.with_name(p.repo.path.name+'.restore-pending.json').exists()
    p.close()


def test_export_limit_produces_no_unrestorable_backup(tmp_path,monkeypatch):
    import toujing_core_runtime.backup as module
    p=setup(tmp_path);dest=tmp_path/'oversize.tjbackup'
    monkeypatch.setattr(module,'LIMIT',100)
    with pytest.raises(ValueError,match='expanded backup'):
        BackupRuntime(p).create({'file_path':str(dest),'backup_password':'long-private-password','preferences':{}})
    assert not dest.exists();p.close()


def test_unsupported_contract_multiplier_fails_closed(tmp_path):
    from src.ledger.contracts import event
    with pytest.raises(ValueError,match='unsupported_security_type'):
        event({**INITIAL,'security_type':'option'},'CNY')
    p=setup(tmp_path);trade(p,'oversell','2025-01-02',quantity=101)
    result=p.ledger_runtime().snapshot(SCOPE['subject_id'],SCOPE['account_id'])
    assert result['status']=='invalid' and result['positions']==[] and result['equity'] is None and result['opening_equity'] is None
    p.close()


def test_research_reproduces_from_persisted_input_after_csv_removed(tmp_path):
    p=setup(tmp_path);path=csv(tmp_path)
    args={**SCOPE,'mode':'strategy','file_path':str(path),'source_ref':'SYNTHETIC','corporate_actions_complete':True,'test_start':'2025-02-10','strategy_id':'dual_ma'}
    result=run(p,args);path.unlink()
    assert run(p,{**SCOPE,'mode':'rerun','run_id':result['run_id']})==result
    p.close();p=ProductRuntime(tmp_path/'facts.sqlite3')
    assert run(p,{**SCOPE,'mode':'rerun','run_id':result['run_id']})==result
    with pytest.raises(ValueError,match='不存在'):run(p,{**SCOPE,'mode':'rerun','run_id':'foreign'})
    p.close()
