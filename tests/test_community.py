import asyncio
import json
import sqlite3
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
from toujing_community.service import CommunityService, COOKIE
from toujing_community.web import CommunityApp

ORIGIN='http://127.0.0.1:18026'
PASSWORD='fictional-test-password-2026'

def card():
    return {'schema':'toujing-investment-share','version':1,'kind':'holdings','source':'local_account','currency':'CNY','asOf':'2026-10-23','holdings':[{'name':'持仓 1','weight':.6},{'name':'持仓 2','weight':.4}],'metrics':{'holdingCount':2},'returnBasis':'unavailable','pnlBasis':'period','definitions':['PRIVATE_SOURCE_PATH'],'disclosure':{'names':False,'amounts':False,'weights':True,'performance':True,'dates':True,'counts':True}}

def payload():
    return {'card':card(),'narrative':{'title':'测试投资复盘','thesis':'全部为虚构测试数据','risk':'尚未验证的判断','watch':'观察现金流；核对后续披露'},'request_id':str(uuid.uuid4())}

class Client:
    def __init__(self,service,name='alice'):
        self.service=service;self.headers={'Host':'127.0.0.1:18026','Origin':ORIGIN,'Content-Type':'application/json'}
        status,result,headers=self.call('register',{'username':name,'name':name.title(),'password':PASSWORD})
        assert status==200,result
        self.headers['Cookie']=headers['Set-Cookie'].split(';')[0];self.headers['X-CSRF-Token']=result['csrf'];self.user=result['user']
    def call(self,path,body=None,**headers):
        return self.service.request('GET' if body is None else 'POST','/api/community/'+path,{**self.headers,**headers},b'' if body is None else json.dumps(body).encode())
    def post(self,p=None):
        status,result,_=self.call('posts',p or payload());assert status==200,result;return result['id']

@pytest.fixture
def service(tmp_path):
    return CommunityService(tmp_path/'community.sqlite3',[ORIGIN])


def test_two_members_share_comment_follow_and_persist(service):
    alice,bob=Client(service),Client(service,'bob')
    pid=alice.post()
    assert bob.call('posts')[1]['items'][0]['author']['id']==alice.user['id']
    assert bob.call(f'posts/{pid}/follow',{'following':True})[0]==200
    assert not alice.call('posts?filter=following')[1]['items']
    assert len(bob.call('posts?filter=following')[1]['items'])==1
    assert bob.call(f'posts/{pid}/comments',{'body':'另一位成员的反证','request_id':str(uuid.uuid4())})[0]==200
    assert alice.call(f'posts/{pid}/updates',{'body':'作者追加了验证结果','request_id':str(uuid.uuid4())})[0]==200
    activities=bob.call('activity')[1]['items']
    assert [a['kind'] for a in activities]==['updates','comments']
    service2=CommunityService(service.database,[ORIGIN])
    bob.service=service2
    assert bob.call(f'posts/{pid}')[1]['commentsCount']==1
    assert bob.call(f'posts/{pid}')[1]['updatesCount']==1


def test_server_owns_identity_and_blocks_cross_user_mutations(service):
    a,b=Client(service),Client(service,'bob');pid=a.post()
    assert b.call(f'posts/{pid}/withdraw',{})[0]==403
    assert b.call(f'posts/{pid}/updates',{'body':'fake','request_id':str(uuid.uuid4())})[0]==403
    forged=payload();forged['author_id']=a.user['id'];assert b.call('posts',forged)[0]==422
    comment=b.call(f'posts/{pid}/comments',{'body':'bob comment','request_id':str(uuid.uuid4())})[1]['id']
    assert a.call(f'comments/{comment}/remove',{})[0]==403
    assert b.call(f'comments/{comment}/remove',{})[0]==200
    assert a.call(f'posts/{pid}/comments')[1]['items']==[]
    assert a.call(f'posts/{pid}/withdraw',{})[0]==200
    for client in (a,b):
        for path in (f'posts/{pid}',f'posts/{pid}/comments',f'posts/{pid}/updates'):
            assert client.call(path)[0]==404
        assert client.call(f'posts/{pid}/comments',{'body':'late comment','request_id':str(uuid.uuid4())})[0]==404
        assert client.call('posts')[1]['items']==[]
        assert client.call('activity')[1]['items']==[]


def test_cookie_session_csrf_origin_host_and_expiry(service):
    a=Client(service)
    assert service.request('GET','/api/community/posts',{'Host':'127.0.0.1:18026'})[0]==401
    for headers in ({'X-CSRF-Token':''},{'Origin':'https://evil.invalid'},{'Host':'evil.invalid'},{'Sec-Fetch-Site':'cross-site'}):
        assert a.call('posts',payload(),**headers)[0]==403
    assert a.call('posts',payload(),**{'Content-Type':'text/plain'})[0]==415
    assert a.call('logout',{})[0]==200
    assert a.call('session')[0]==401
    b=Client(service,'bob');service.clock=lambda:10**12
    assert b.call('session')[0]==401


def test_password_session_storage_and_login_rotation(service):
    a=Client(service);old=a.headers['Cookie']
    with sqlite3.connect(service.database) as db:
        password=db.execute('SELECT password FROM users').fetchone()[0]
        token=db.execute('SELECT token FROM sessions').fetchone()[0]
    assert PASSWORD not in password and len(password)>100
    assert token not in old and old.split('=',1)[1] not in token
    status,result,headers=a.call('login',{'username':'alice','password':PASSWORD})
    assert status==200
    assert all(x in headers['Set-Cookie'] for x in ('HttpOnly','SameSite=Strict','Path=/api/community'))
    assert a.call('session')[0]==401 # old session rotated
    assert a.call('login',{'username':'alice','password':'incorrect-password'})[0]==401
    assert a.call('login',{'username':'nobody','password':'incorrect-password'})[0]==401


@pytest.mark.parametrize('change',[
    lambda c:c.update(account_id='SECRET'),lambda c:c['metrics'].update(pnl=0),
    lambda c:c['holdings'][0].update(name='SECRET'),lambda c:c['holdings'][0].update(marketValue=999),
    lambda c:c.update(asOf='2026-02-30'),lambda c:c['holdings'][0].update(weight=.9),
    lambda c:c['disclosure'].update(dates=False),lambda c:c['metrics'].update(returnValue=float('inf')),
    lambda c:c['holdings'][0].update(weight=True),lambda c:c['metrics'].update(closedCount=True),
])
def test_rejects_hidden_or_invalid_fields(service,change):
    a=Client(service);p=payload();change(p['card']);assert a.call('posts',p)[0]==422
    assert a.call('posts')[1]['items']==[]


def test_source_normalization_and_private_data_absent(service):
    a=Client(service);p=payload();pid=a.post(p);saved=a.call(f'posts/{pid}')[1]
    assert saved['card']['source']=='user_reported'
    assert saved['card']['pnlBasis']=='user_reported'
    assert saved['watchpoints']==['观察现金流','核对后续披露']
    assert 'PRIVATE_SOURCE_PATH' not in json.dumps(saved)
    with sqlite3.connect(service.database) as db:
        assert 'PRIVATE_SOURCE_PATH' not in db.execute('SELECT content FROM posts').fetchone()[0]


def test_idempotency_concurrency_and_cursor_pagination(service):
    a=Client(service);p=payload()
    with ThreadPoolExecutor(4) as pool: ids=list(pool.map(lambda _:a.post(p),range(4)))
    assert len(set(ids))==1
    p['narrative']['title']='changed'
    assert a.call('posts',p)[0]==409
    for _ in range(22):a.post()
    first=a.call('posts')[1];second=a.call('posts?before='+str(first['next']))[1]
    assert len(first['items'])==20 and len(second['items'])==3 and second['next'] is None
    assert not set(p['id'] for p in first['items']) & set(p['id'] for p in second['items'])
    assert a.call('posts?before=-1')[0]==422


def test_follow_is_idempotent_and_comment_retry_not_duplicated(service):
    a=Client(service);pid=a.post();data={'body':'one','request_id':str(uuid.uuid4())}
    first=a.call(f'posts/{pid}/comments',data);second=a.call(f'posts/{pid}/comments',data)
    assert first[1]['id']==second[1]['id']
    for _ in range(2):assert a.call(f'posts/{pid}/follow',{'following':True})[0]==200
    assert len(a.call('posts?filter=following')[1]['items'])==1
    assert a.call(f'posts/{pid}/follow',{'following':False})[0]==200
    assert a.call('posts?filter=following')[1]['items']==[]


def test_registration_policy_and_rate_limit(service):
    a=Client(service);service.registration=False
    assert a.call('register',{'username':'new','name':'New','password':PASSWORD})[0]==403
    for _ in range(12):status=a.call('login',{'username':'alice','password':'incorrect-password'})[0]
    assert status==429
    assert a.call('register',{'username':{},'name':False,'password':PASSWORD})[0]==422


def test_deployment_requires_https_and_cookie_secure(tmp_path):
    with pytest.raises(ValueError):CommunityService(tmp_path/'a.db',['http://community.example'])
    s=CommunityService(tmp_path/'b.db',['https://community.example'])
    assert '; Secure' in s.cookie('token',100)
    assert s.database.stat().st_mode&0o777==0o600


def test_asgi_boundary_assets_and_body_limit(service,tmp_path):
    dist=tmp_path/'dist';dist.mkdir();(dist/'index.html').write_text('<h1>Toujing</h1>')
    app=CommunityApp(service,dist)
    async def call(path,method='GET',body=b'',headers=None):
        outgoing=[]
        async def receive():return {'type':'http.request','body':body,'more_body':False}
        async def send(data):outgoing.append(data)
        await app({'type':'http','path':path,'method':method,'headers':[(b'host',b'127.0.0.1:18026'),*(headers or [])],'client':('test',0)},receive,send)
        return outgoing
    result=asyncio.run(call('/'));assert result[0]['status']==200
    headers=dict(result[0]['headers']);assert headers[b'x-frame-options']==b'DENY'
    for path in ('/api/company-research','/api/accounts','/../secret.txt'):
        assert asyncio.run(call(path))[0]['status'] in (403,404)
    assert asyncio.run(call('/api/community/posts','POST',b'x'*(128*1024+1)))[0]['status']==413
    assert asyncio.run(call('/api/community/posts'))[0]['status']==401


def test_backup_restore_preserves_posts_but_revokes_sessions(service,tmp_path):
    from scripts.community_admin import snapshot
    a=Client(service);pid=a.post()
    target=tmp_path/'backup.db';snapshot(service.database,target)
    with pytest.raises(FileExistsError):snapshot(service.database,target)
    restore=tmp_path/'restore.db';snapshot(target,restore,invalidate_sessions=True)
    restored=CommunityService(restore,[ORIGIN]);a.service=restored
    assert a.call('session')[0]==401
    status,result,headers=a.call('login',{'username':'alice','password':PASSWORD});assert status==200
    a.headers['Cookie']=headers['Set-Cookie'].split(';')[0];a.headers['X-CSRF-Token']=result['csrf']
    assert a.call(f'posts/{pid}')[1]['title']=='测试投资复盘'


def test_disabled_user_session_and_login_rejected(service):
    a=Client(service)
    with service.db() as db:db.execute('UPDATE users SET disabled=1 WHERE id=?',(a.user['id'],))
    assert a.call('session')[0]==401
    assert a.call('login',{'username':'alice','password':PASSWORD})[0]==401
