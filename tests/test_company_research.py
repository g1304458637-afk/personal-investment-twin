"""Company integration boundaries: no account forwarding or arbitrary HTTP targets."""
import io
import json
import threading
from http.client import HTTPConnection
from urllib.error import HTTPError, URLError

import pytest

from toujing_core_runtime.company_research import CompanyResearchClient, CompanyResearchError
from scripts.company_research_web import make_server


class Response(io.BytesIO):
    pass


class Transport:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.requests = []

    def open(self, request, timeout):
        self.requests.append(request)
        value = next(self.replies)
        if isinstance(value, Exception):
            raise value
        return Response(value if isinstance(value, bytes) else json.dumps(value).encode())


@pytest.mark.parametrize('url', ['https://127.0.0.1:18024','http://localhost:18024','http://evil.test:18024','http://127.0.0.1:1/private','http://user:secret@127.0.0.1:1','http://127.0.0.1:1?url=evil'])
def test_only_explicit_loopback_service_can_receive_requests(url):
    with pytest.raises(ValueError):
        CompanyResearchClient(url)


@pytest.mark.parametrize('method,params', [
    ('account.list',{}), ('company_research.list',{'account_id':'private'}),
    ('company_research.load',{'build_id':'../account.db'}),
    ('company_research.chat',{'build_id':'build_a','messages':[{'role':'user','content':'x','api_key':'secret'}]}),
    ('company_research.chat',{'build_id':'build_a','messages':[{'role':'assistant','content':'x'}]}),
    ('company_research.build',{'query':'x','url':'https://evil.test'}),
])
def test_client_rejects_private_or_unbounded_parameters_before_transport(method,params):
    transport=Transport([])
    with pytest.raises(ValueError):
        CompanyResearchClient(opener=transport).call(method,params)
    assert transport.requests==[]


def test_model_views_are_version_bound_and_preserve_raw_values():
    transport=Transport([{'version_id':'v1','facts':[{'value':'423701834','unit':'CNY_thousand'}]}, {'modelVersion':{'id':'v1'},'nodes':{}}])
    result=CompanyResearchClient(opener=transport).call('company_research.load',{'build_id':'build_a'})
    assert result['analysis']['facts'][0]['value']=='423701834'
    assert [r.full_url for r in transport.requests]==['http://127.0.0.1:18024/api/builds/build_a/analysis','http://127.0.0.1:18024/api/builds/build_a/graph']
    transport=Transport([{'version_id':'v1'}, {'modelVersion':{'id':'v2'}}])
    with pytest.raises(CompanyResearchError,match='版本'):
        CompanyResearchClient(opener=transport).call('company_research.load',{'build_id':'build_a'})


@pytest.mark.parametrize('error,code',[(URLError('/private/secret'),'company_engine_unavailable'),(HTTPError('x',503,'key unavailable',{},None),'company_model_unavailable'),(HTTPError('x',502,'secret provider payload',{},None),'company_provider_failed')])
def test_service_errors_are_structured_and_redacted(error,code):
    with pytest.raises(CompanyResearchError) as caught:
        CompanyResearchClient(opener=Transport([error])).call('company_research.list',{})
    assert caught.value.code==code
    assert 'secret' not in str(caught.value)


def test_resolution_escapes_query_and_chat_keeps_current_build_only():
    transport=Transport([{'status':'NOT_FOUND'},{'status':'UNKNOWN'}])
    client=CompanyResearchClient(opener=transport)
    client.call('company_research.resolve',{'query':'A&B? x'})
    client.call('company_research.ask',{'build_id':'build_ab','question':'营业收入'})
    assert transport.requests[0].full_url.endswith('query=A%26B%3F+x')
    assert transport.requests[1].full_url.endswith('/build_ab/ask')
    assert json.loads(transport.requests[1].data)=={'question':'营业收入'}


@pytest.fixture
def gateway(tmp_path):
    (tmp_path/'index.html').write_text('<main>integration</main>')
    calls=[]
    class Client:
        def call(self,method,params):
            calls.append((method,params))
            return {'public_company':True}
    server=make_server(0,tmp_path,client=Client())
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    yield server,calls
    server.shutdown();server.server_close();thread.join(5)


def send(server,path=' /api/company-research',*,method='POST',body=None,headers=None):
    conn=HTTPConnection('127.0.0.1',server.server_port,timeout=5)
    conn.request(method,path.strip(),body=json.dumps(body or {'method':'company_research.list','params':{}}),headers={'Content-Type':'application/json',**(headers or {})})
    response=conn.getresponse();raw=response.read();conn.close()
    return response.status,raw


def test_web_bridge_never_exposes_account_rpc_and_blocks_cross_site(gateway):
    server,calls=gateway
    assert send(server,headers={'Origin':'https://evil.test'})[0]==403
    assert send(server,headers={'Origin':'null'})[0]==403
    assert send(server,headers={'Sec-Fetch-Site':'cross-site'})[0]==403
    assert send(server,headers={'Host':f'evil.test:{server.server_port}'})[0]==403
    assert send(server,body={'method':'ledger.get','params':{}})[0]==422
    assert calls==[]
    status,raw=send(server,headers={'Origin':f'http://127.0.0.1:{server.server_port}'})
    assert status==200 and json.loads(raw)['result']=={'public_company':True}
    assert calls==[('company_research.list',{})]


def test_web_static_files_do_not_turn_missing_api_into_a_fake_success(gateway):
    server,_=gateway
    assert send(server,'/api/missing',method='GET')[0]==404
    assert send(server,'/missing.js',method='GET')[0]==404
    assert send(server,'/../../private',method='GET')[0]==403
    status,raw=send(server,'/',method='GET')
    assert status==200 and b'integration' in raw


def test_reopen_status_identifies_the_workspace_without_proxying_or_data(gateway):
    server,calls=gateway
    status,raw=send(server,'/api/workspace-status',method='GET')
    payload=json.loads(raw)
    assert status==200 and payload['application']=='toujing-company-integration'
    assert set(payload)=={'application','source_id'}
    assert calls==[]
