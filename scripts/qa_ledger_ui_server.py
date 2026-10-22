"""Fixture-only UI bridge. Binds loopback, uses an isolated private database."""
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import csv
from datetime import date,timedelta
import json
import os
import tempfile
from toujing_core_runtime.product import ProductRuntime
from toujing_core_runtime.protocol import _product_methods

root=Path(tempfile.mkdtemp(prefix='toujing-ledger-ui-'));os.chmod(root,0o700)
methods,product=_product_methods(str(root/'facts.sqlite3'))
scope={'subject_id':'qa-fixture','account_id':'qa-fixture'}
opening={**scope,'mode':'opening','opening':{'opening_date':'2025-01-01','currency':'CNY','initial_cash':'10000','display_name':'合成验收账户','source_ref':'SYNTHETIC QA'},'records':[{'event_id':'opening','event_type':'opening_position','effective_date':'2025-01-01','currency':'CNY','source_ref':'SYNTHETIC QA','symbol':'600000','market':'XSHG','security_type':'equity','quantity':'100','cost_basis':'1000','opening_price':'12'}]}
preview=product.ledger_runtime().preview(opening);product.ledger_runtime().commit({**opening,'expected_preview_fingerprint':preview['preview_fingerprint']})
path=root/'bars.csv'
with path.open('w') as f:
 f.write('row_type,symbol,market,security_type,date,open,high,low,close,volume\n')
 for i in range(90):
  day=date(2025,1,1)+timedelta(days=i);price=12+i*0.01
  f.write(f'bar,600000,XSHG,equity,{day},{price},{price+1},{price-1},{price},1000\n')
allowed={'ledger.get','ledger.preview','ledger.commit','ledger.research','backup.create','backup.preview_restore','backup.restore','backup.pending_preferences','backup.ack_preferences','account.list'}
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_POST(self):
  try:
   if self.path!='/rpc' or self.headers.get('Origin')!='http://127.0.0.1:1448':raise ValueError('fixture origin only')
   size=int(self.headers.get('Content-Length','0'))
   if size>512000:raise ValueError('size')
   req=json.loads(self.rfile.read(size));method=req['method'];params=req.get('params',{})
   if method=='qa.files':result={'bars':str(path),'backup':str(root/'fixture.tjbackup')}
   else:
    if method not in allowed:raise ValueError('fixture method only')
    if 'file_path' in params and Path(params['file_path']).parent!=root:raise ValueError('fixture paths only')
    if method.startswith('ledger.'):params={**params,**scope}
    result=methods[method](params)
   payload={'ok':True,'result':result}
  except Exception as exc:payload={'ok':False,'error':str(exc)}
  raw=json.dumps(payload,ensure_ascii=False,allow_nan=False).encode();self.send_response(200);self.send_header('Access-Control-Allow-Origin','http://127.0.0.1:1448');self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(raw)
 def do_OPTIONS(self):
  self.send_response(204);self.send_header('Access-Control-Allow-Origin','http://127.0.0.1:1448');self.send_header('Access-Control-Allow-Headers','Content-Type');self.end_headers()
print('Fixture-only ledger bridge: 127.0.0.1:1449',flush=True)
try:HTTPServer(('127.0.0.1',1449),Handler).serve_forever()
finally:product.close()
