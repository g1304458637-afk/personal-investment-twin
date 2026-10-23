"""Explicit offline browser fixture for the integrated build/empty/error flow.

No provider calls, account records or original company databases are used.
"""
import copy
import sys
import tempfile
import shutil
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.company_research_web import make_server
from toujing_core_runtime.company_research import CompanyResearchError


class Fixture:
    def __init__(self):
        self.builds=[]
        self.polls=0

    def model(self,build):
        name=build['company'];eid='qa_evidence';vid=build['version_id']
        fact={'key':'revenue','name':'营业收入','unit':'CNY','kind':'fact','values':[{'period':f'{y}年','value':str(1_000_000+i*100_000),'unit':'CNY','knowledge_status':'OBSERVED','validation_status':'UNVALIDATED','evidence_ids':[eid]} for i,y in enumerate([2023,2024,2025])]}
        return {'build_id':build['build_id'],'analysis':{'version_id':vid,'fingerprint':'SYNTHETIC-QA','facts':[fact],'ratios':[],'quality':{'numeric_observations':3,'historical_validation_status':'NOT_RUN','observation_validation_counts':{'UNVALIDATED':3}}},'graph':{'modelVersion':{'id':vid,'twinId':'qa_twin'},'nodes':{'qa_root':{'id':'qa_root','label':name,'kind':'company'}},'sources':{eid:{'id':eid,'title':'SYNTHETIC QA 测试报告','locator':'SYNTHETIC QA · 无真实报告','note':'Source excerpt: 这是离线联调资料，不是真实公司数据。 Raw artifact SHA-256: QA'}},'coverage':{'entities':1,'metrics':1}}}

    def row(self,index,status='COMPLETED'):
        return {'build_id':f'build_qa{index}','company':f'SYNTHETIC 公司 {index}','query':f'QATEST{index}','status':status,'identity':{'company_id':f'qa_issuer_{index}','short_name':f'SYNTHETIC 公司 {index}','listings':[{'ticker':f'QA{index}','exchange':'TEST'}]},'version_id':f'qa_version_{index}','started_at':'2026-10-23T00:00:00Z','event_count':4}

    def call(self,method,params):
        action=method.split('.')[-1]
        if action=='status':return {'application':'company-operating-twin','protocol_version':1,'generic_builds':True,'deterministic_qa':True,'chat':{'configured':True,'provider':'SYNTHETIC','model':'offline-fixture','connectivity_verified':False}}
        if action=='list':return {'builds':copy.deepcopy(self.builds)}
        if action=='resolve':return {'query':params['query'],'status':'RESOLVED','candidates':[{'identity':self.row(1)['identity'],'score':100,'method':'EXACT_IDENTIFIER'}]}
        if action=='build':
            self.builds=[self.row(1,'RUNNING')];return {'build_id':'build_qa1','status':'STARTED'}
        if action=='snapshot':
            self.polls+=1
            if self.polls>=2:self.builds=[self.row(1),self.row(2)]
            status='COMPLETED' if self.polls>=2 else 'RUNNING'
            return {'build_id':'build_qa1','status':status,'company_node':{'id':'qa_issuer_1','label':'SYNTHETIC 公司 1'},'summary':None,'events':[{'seq':1,'type':'BuildStarted','message':'SYNTHETIC QA','payload':{}}]}
        build=next(b for b in self.builds if b['build_id']==params['build_id'])
        if action=='load':return self.model(build)
        if action=='report':return {'html':'<!doctype html><h1>SYNTHETIC QA REPORT</h1>'}
        if action=='chat':
            question=params['messages'][-1]['content']
            if '延迟' in question:time.sleep(10)
            if '失败' in question:raise CompanyResearchError('company_provider_failed','SYNTHETIC provider failure',502)
            return {'status':'ANSWERED','answer':f"SYNTHETIC {build['company']}回答 [1]。",'citations':[{'index':1,'label':'SYNTHETIC QA 证据','evidence_ids':['qa_evidence'],'detail':'offline fixture'}]}
        if action=='ask':return {'status':'UNKNOWN','answer':'SYNTHETIC 确定性资料查询：没有匹配项。','citations':[]}
        raise ValueError('Unsupported QA method')


if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='toujing-company-ui-') as temp:
        dist=Path(temp)/'dist';shutil.copytree(ROOT/'apps/desktop/dist',dist)
        index=dist/'index.html'
        index.write_text(index.read_text().replace('<body>','<body><div style="position:fixed;bottom:0;left:0;right:0;z-index:5000;background:#78501b;color:white;text-align:center;font-size:12px;padding:6px">SYNTHETIC COMPANY QA · 离线联调 · 不是真实公司或模型回答</div>'))
        server=make_server(18029,dist,client=Fixture())
        print('Offline UI fixture: http://127.0.0.1:18029/#/company-research',flush=True)
        try:server.serve_forever()
        except KeyboardInterrupt:pass
        finally:server.server_close()
