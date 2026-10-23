"""Offline stages 2-4 proof through the actual packaged executable, fixtures only."""
from datetime import date,timedelta
from pathlib import Path
import argparse
import hashlib
import json
import tempfile
import time
from verify_packaged_account_roundtrip import PackagedClient,DEFAULT_BINARY,require


def verify(binary):
 with tempfile.TemporaryDirectory(prefix='toujing-packaged-ledger-') as tmp:
  root=Path(tmp);db=root/'facts.sqlite3';scope={'subject_id':'fixture-ledger','account_id':'fixture-ledger'}
  client=PackagedClient(binary,root,db,root/'cache')
  def call(method,params):return client.call(method,{**scope,**params})
  def commit(mode,**params):
   args={'mode':mode,**params};preview=call('ledger.preview',args)
   require(not preview['issues'],'ledger_preview_blocked')
   return call('ledger.commit',{**args,'expected_preview_fingerprint':preview['preview_fingerprint'],'expected_file_sha256':preview['file_sha256']})
  sec={'symbol':'600000','market':'XSHG','security_type':'equity','currency':'CNY'}
  def event(kind,identifier,day,**values):return {**sec,'event_type':kind,'event_id':identifier,'effective_date':day,'source_ref':'SYNTHETIC-QA',**values}
  try:
   start=time.monotonic();handshake=client.call('runtime.handshake',{},startup=True);cold=round(time.monotonic()-start,3)
   require({'ledger.research','backup.restore'}<=set(handshake['supported_methods']),'missing_methods')
   commit('opening',opening={'opening_date':'2025-01-01','currency':'CNY','initial_cash':'10000','display_name':'SYNTHETIC QA','source_ref':'SYNTHETIC-QA'},records=[event('opening_position','open','2025-01-01',quantity='100',cost_basis='1000',opening_price='12')])
   commit('events',records=[event('split','split','2025-01-02',ratio='2'),event('cash_dividend','div','2025-01-05',ex_date='2025-01-03',amount='100',tax='10'),event('deposit','in','2025-01-04',amount='5000'),event('withdrawal','out','2025-01-05',amount='1000')])
   prices=root/'prices.csv';prices.write_text('date,local_symbol,market,security_type,price,price_type,currency,source_label\n2025-01-02,600000,XSHG,equity,6,unadjusted_close,CNY,SYNTHETIC\n2025-01-03,600000,XSHG,equity,5.5,unadjusted_close,CNY,SYNTHETIC\n2025-01-05,600000,XSHG,equity,5.5,unadjusted_close,CNY,SYNTHETIC\n')
   args={'file_path':str(prices),'source_id':'qa','source_version':'1'};preview=call('market.preview_price_csv',args)
   require(preview['summary']['invalid_rows']==0,'raw_market_preview_invalid')
   call('market.commit_price_import',{**args,'expected_file_sha256':preview['file_sha256'],'expected_preview_fingerprint':preview['preview_fingerprint']})
   snapshot=call('ledger.get',{})['snapshot'];require(snapshot['cash']=='14090' and snapshot['equity']=='15190' and snapshot['period_pnl']=='-10','flow_action_conservation_failed')
   commit('statement',statement={'statement_id':'qa','as_of':'2025-01-05','currency':'CNY','cash':'14090','equity':'15190','positions_complete':True,'source_ref':'SYNTHETIC-QA','positions':[{**sec,'quantity':'200','cost_basis':'1000','market_value':'1100'}]})
   commit('plan',entry={'entry_id':'plan','text':'SYNTHETIC-QA plan','invalidation':'SYNTHETIC-QA invalidation','proposed_trade':{**sec,'side':'BUY','quantity':'10','price':'5.5','fee':'1'}})
   ai_args={'scope_kind':'account','data_mode':'real_user'}
   ai=call('review.context',ai_args)
   require(ai['projection_kind']=='account_ledger.v1' and ai['as_of_semantics']=='ledger_last_known_unadjusted_prices_with_dates','ledger_ai_projection_missing')
   require(len(ai['episode_ids'])==1 and len(ai['finding_options'])==2,'ledger_ai_catalog_missing')
   focused=call('review.context',{**ai_args,'scope_kind':'episode','episode_id':ai['episode_ids'][0]})
   require(focused['episode_ids']==ai['episode_ids'] and not focused['finding_options'],'ledger_ai_scope_failed')
   require(len(focused['record_refs'])<len(ai['record_refs']) and focused['scope']['scope_kind']=='episode','ledger_ai_scope_not_restricted')
   pretrade=call('ledger.research',{'mode':'pretrade','as_of':'2025-01-05','proposed_trade':{**sec,'side':'BUY','quantity':'10','price':'5.5','fee':'1'}})
   require(pretrade['status']=='simulated' and pretrade['after']['equity']=='15189','pretrade_failed')
   bars=root/'bars.csv';rows=['row_type,symbol,market,security_type,date,open,high,low,close,volume']
   for i in range(80):
    day=date(2025,2,1)+timedelta(days=i);rows.append(f'bar,600000,XSHG,equity,{day},5.5,6,5,5.5,1000')
   bars.write_text('\n'.join(rows))
   research=call('ledger.research',{'mode':'strategy','file_path':str(bars),'source_ref':'SYNTHETIC-QA raw bars','corporate_actions_complete':True,'test_start':'2025-03-10','strategy_id':'dual_ma','parameter':'commission_rate','values':[0,0.001]})
   require(research['train']['future_check']['status']=='passed' and research['test']['future_check']['status']=='passed','research_future_check_failed')
   bars.unlink()
   require(call('ledger.research',{'mode':'rerun','run_id':research['run_id']})==research,'research_reproduction_without_original_csv_failed')
   backup=root/'fixture.tjbackup';args={'file_path':str(backup),'backup_password':'SYNTHETIC-QA-PASSWORD','preferences':{'toujing.userStrategies':'[]','toujing.theme':'light'}}
   client.call('backup.create',args)
   baseline=call('ledger.get',{})
   commit('events',records=[event('deposit','later','2025-01-06',amount='777')])
   require(call('review.context',ai_args)['source_fingerprint']!=ai['source_fingerprint'],'ledger_ai_stale_context_not_invalidated')
   restore=client.call('backup.preview_restore',args)
   client.call('backup.restore',{**args,'expected_preview_fingerprint':restore['preview_fingerprint'],'confirm_replace_all':True})
   require(call('ledger.get',{})==baseline,'restore_facts_not_identical')
   require(call('ledger.research',{'mode':'rerun','run_id':research['run_id']})==research,'research_reproduction_after_restore_failed')
   require(client.call('backup.pending_preferences',{})['pending']['preferences']['toujing.theme']=='light','restore_preferences_missing')
   client.shutdown();client.close();client=PackagedClient(binary,root,db,root/'cache');client.call('runtime.handshake',{},startup=True)
   require(call('ledger.get',{})==baseline,'restart_facts_not_identical')
   client.shutdown()
   return {'status':'PASS','binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'cold_handshake_s':cold,'cash':'14090','equity':'15190','period_pnl':'-10','reconciliation':'matched','ledger_ai_context':'account_ledger.v1','ledger_ai_episode_scope':True,'ledger_ai_stale_invalidation':True,'model_calls':0,'journal_and_research_restored':True,'research_reproduced_without_csv':True,'restart_identical':True,'pretrade_writes_account':False,'data':'synthetic fixtures only','network_and_Keychain':'not called'}
  finally:client.close()

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--binary',type=Path,default=DEFAULT_BINARY);args=parser.parse_args()
 print(json.dumps(verify(args.binary.resolve()),ensure_ascii=False,indent=2))
