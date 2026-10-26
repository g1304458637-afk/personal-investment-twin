"""SQLite community with server-owned identity, sessions and object authorization."""
from __future__ import annotations
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from .validation import card_for_members, narrative, validate, obj, string

SCHEMA = '''
CREATE TABLE users(id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, name TEXT NOT NULL, password TEXT NOT NULL, disabled INTEGER NOT NULL DEFAULT 0);
CREATE TABLE sessions(token TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), csrf TEXT NOT NULL, expires INTEGER NOT NULL);
CREATE TABLE posts(id INTEGER PRIMARY KEY AUTOINCREMENT, author_id TEXT NOT NULL REFERENCES users(id), request_id TEXT NOT NULL, digest TEXT NOT NULL, content TEXT NOT NULL, created INTEGER NOT NULL, withdrawn INTEGER NOT NULL DEFAULT 0, UNIQUE(author_id,request_id));
CREATE TABLE comments(id INTEGER PRIMARY KEY AUTOINCREMENT, post_id INTEGER NOT NULL REFERENCES posts(id), author_id TEXT NOT NULL REFERENCES users(id), request_id TEXT NOT NULL, body TEXT NOT NULL, created INTEGER NOT NULL, removed INTEGER NOT NULL DEFAULT 0, UNIQUE(author_id,request_id));
CREATE TABLE updates(id INTEGER PRIMARY KEY AUTOINCREMENT, post_id INTEGER NOT NULL REFERENCES posts(id), author_id TEXT NOT NULL REFERENCES users(id), request_id TEXT NOT NULL, body TEXT NOT NULL, created INTEGER NOT NULL, UNIQUE(author_id,request_id));
CREATE TABLE follows(user_id TEXT NOT NULL REFERENCES users(id), post_id INTEGER NOT NULL REFERENCES posts(id), PRIMARY KEY(user_id,post_id));
CREATE TABLE events(id INTEGER PRIMARY KEY AUTOINCREMENT, post_id INTEGER NOT NULL REFERENCES posts(id), actor_id TEXT NOT NULL REFERENCES users(id), kind TEXT NOT NULL, created INTEGER NOT NULL);
CREATE TABLE limits(key TEXT PRIMARY KEY, count INTEGER NOT NULL, expires INTEGER NOT NULL);
CREATE INDEX post_feed ON posts(withdrawn,id DESC);
CREATE INDEX comment_post ON comments(post_id,id);
CREATE INDEX update_post ON updates(post_id,id);
CREATE INDEX session_expiry ON sessions(expires);
CREATE INDEX event_post ON events(post_id,id);
PRAGMA user_version=1;
'''
COOKIE = 'toujing_member'
TTL = 7 * 86400


class ApiError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    # OWASP scrypt alternative: N=2^15, r=8, p=3 (32 MiB).
    key = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=32768, r=8, p=3, maxmem=64*1024*1024).hex()
    return salt + ':' + key


class CommunityService:
    def __init__(self, database: Path, origins, *, registration=True, clock=time.time):
        self.database, self.origins, self.registration, self.clock = Path(database), set(origins), registration, clock
        if not self.origins:
            raise ValueError('At least one explicit origin is required')
        for origin in self.origins:
            u = urlsplit(origin)
            if u.path or u.query or u.fragment or u.username or u.password or not u.netloc or u.scheme not in ('http','https'):
                raise ValueError('Use an exact HTTP(S) origin without a path')
            if u.scheme != 'https' and u.hostname not in ('127.0.0.1', 'localhost', '::1'):
                raise ValueError('Non-loopback community origins require HTTPS')
        if len({urlsplit(x).scheme for x in self.origins}) != 1:
            raise ValueError('Do not mix HTTP and HTTPS origins')
        self.secure = all(x.startswith('https:') for x in self.origins)
        self.hosts = {urlsplit(x).netloc for x in self.origins}
        self.database.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.database, os.O_CREAT | os.O_WRONLY, 0o600); os.close(fd)
        self.database.chmod(0o600)
        with self.db() as db:
            db.execute('PRAGMA journal_mode=WAL')
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version == 0:
                db.executescript('BEGIN IMMEDIATE;'+SCHEMA+'COMMIT;')
            elif version != 1:
                raise ValueError('Unsupported community database version')
        self.dummy_password = password_hash('non-user-timing-placeholder')

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.database, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def limit(self, key, maximum, seconds):
        now = int(self.clock()); key = digest(key)
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM limits WHERE expires<=?', (now,))
            db.execute('INSERT INTO limits VALUES(?,1,?) ON CONFLICT(key) DO UPDATE SET count=count+1', (key, now+seconds))
            count = db.execute('SELECT count FROM limits WHERE key=?',(key,)).fetchone()[0]
        if count > maximum:
            raise ApiError(429, '操作太频繁，请稍后再试。')

    def identity(self, db, headers):
        cookie = SimpleCookie()
        try:
            cookie.load(headers.get('cookie',''))
            raw = cookie[COOKIE].value if COOKIE in cookie else ''
        except Exception:
            raw = ''
        row = db.execute('SELECT u.id,u.username,u.name,s.csrf,s.token FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=? AND s.expires>? AND u.disabled=0', (digest(raw),int(self.clock()))).fetchone()
        if not row:
            raise ApiError(401, '请登录社区账号。')
        return dict(row)

    def request(self, method, target, headers, body=b'', ip='local'):
        headers = {k.lower():v for k,v in headers.items()}
        try:
            if headers.get('host') not in self.hosts:
                raise ApiError(403, '请求来源不受信任。')
            path = urlsplit(target).path
            if not path.startswith('/api/community/'):
                raise ApiError(404, '接口不存在。')
            if method not in ('GET','POST'):
                raise ApiError(405, '请求方法不支持。')
            data = {}
            if method == 'POST':
                if headers.get('origin') not in self.origins or headers.get('sec-fetch-site') == 'cross-site':
                    raise ApiError(403, '请从社区页面提交。')
                if headers.get('content-type','').split(';')[0] != 'application/json':
                    raise ApiError(415, '请求需要 JSON 格式。')
                if len(body)>128*1024:
                    raise ApiError(413, '分享内容过大。')
                def invalid(_): raise ValueError('Invalid number')
                data = json.loads(body, parse_constant=invalid)
                json.dumps(data, allow_nan=False)
                if not isinstance(data,dict): raise ValueError('Invalid object')
            if path == '/api/community/status' and method == 'GET':
                return 200, {'registration':self.registration,'audience':'members'}, {}
            if path in ('/api/community/register','/api/community/login') and method == 'POST':
                return self.authenticate(path, data, headers, ip)
            with self.db() as db:
                user = self.identity(db,headers)
            if method == 'POST':
                if not hmac.compare_digest(headers.get('x-csrf-token',''),user['csrf']):
                    raise ApiError(403, '登录校验已变化，请刷新页面。')
                self.limit('write:'+user['id'],120,60)
            with self.db() as db:
                # Serialize authorization and mutations: withdrawal cannot race a comment/update.
                if method == 'POST': db.execute('BEGIN IMMEDIATE')
                self.identity(db,headers)
                result, extra = self.dispatch(db,user,method,path,parse_qs(urlsplit(target).query),data)
            return 200, result, extra
        except ApiError as e:
            return e.status, {'error':e.message}, {}
        except (ValueError,TypeError,KeyError,OverflowError,RecursionError):
            return 422, {'error':'内容格式或展示范围无效，请检查输入。'}, {}
        except sqlite3.OperationalError:
            return 503, {'error':'社区暂时繁忙，请稍后重试。'}, {}

    def authenticate(self,path,data,headers,ip):
        registration=path.endswith('register')
        expected={'username','password','name'} if registration else {'username','password'}
        if set(data)!=expected: raise ValueError('Invalid fields')
        if not isinstance(data['username'],str) or not isinstance(data['password'],str) or registration and not isinstance(data['name'],str): raise ValueError('Invalid types')
        username=data['username'].strip().lower()
        if not re.fullmatch(r'[a-z0-9_]{3,32}',username) or not isinstance(data['password'],str) or not 12<=len(data['password'])<=128:
            raise ApiError(422,'用户名需为 3–32 位英文、数字或下划线；密码需为 12–128 位。')
        self.limit('auth-ip:'+ip,30,60)
        self.limit('auth-name:'+username,10,60)
        if registration:
            if not self.registration: raise ApiError(403,'当前社区暂未开放注册。')
            self.limit('register:'+ip,10,3600)
            name=data['name'].strip()
            if not 1<=len(name)<=40: raise ValueError('Invalid name')
            hashed=password_hash(data['password'])
            uid=secrets.token_hex(16)
            try:
                with self.db() as db: db.execute('INSERT INTO users(id,username,name,password) VALUES(?,?,?,?)',(uid,username,name,hashed))
            except sqlite3.IntegrityError:
                raise ApiError(409,'该用户名不可用。')
        else:
            with self.db() as db: user=db.execute('SELECT * FROM users WHERE username=?',(username,)).fetchone()
            expected_hash=user['password'] if user else self.dummy_password
            valid=hmac.compare_digest(password_hash(data['password'],expected_hash.split(':')[0]),expected_hash)
            if not valid or not user or user['disabled']:
                raise ApiError(401,'用户名或密码不正确。')
            uid=user['id']; name=user['name']
        token,csrf=secrets.token_urlsafe(32),secrets.token_urlsafe(32)
        now=int(self.clock())
        with self.db() as db:
            db.execute('DELETE FROM sessions WHERE expires<=?',(now,))
            # Rotate this browser's old session while preserving other devices.
            try: old=self.identity(db,headers);db.execute('DELETE FROM sessions WHERE token=?',(old['token'],))
            except ApiError: pass
            db.execute('INSERT INTO sessions VALUES(?,?,?,?)',(digest(token),uid,csrf,now+TTL))
        return 200, {'user':{'id':uid,'username':username,'name':name},'csrf':csrf}, {'Set-Cookie':self.cookie(token,TTL)}

    def cookie(self, token, age):
        return f'{COOKIE}={token}; Path=/api/community; HttpOnly; SameSite=Strict; Max-Age={age}'+('; Secure' if self.secure else '')

    @staticmethod
    def rid(data):
        rid=data.get('request_id')
        if not isinstance(rid,str) or not re.fullmatch(r'[a-zA-Z0-9-]{16,80}',rid): raise ValueError('Invalid request ID')
        return rid

    @staticmethod
    def before(query):
        value=query.get('before',['9223372036854775807'])[0]
        if not value.isdigit() or not 0<int(value)<=9223372036854775807: raise ValueError('Invalid cursor')
        return int(value)

    @staticmethod
    def active_post(db,pid):
        row=db.execute('SELECT * FROM posts WHERE id=? AND withdrawn=0',(pid,)).fetchone()
        if not row: raise ApiError(404,'这篇分享已撤回或不存在。')
        return row

    def post_view(self,db,row,uid):
        content=json.loads(row['content'])
        user=db.execute('SELECT id,name,username FROM users WHERE id=?',(row['author_id'],)).fetchone()
        return {**content,'id':row['id'],'author':dict(user),'created':row['created'],'isOwn':uid==row['author_id'],
                'following':bool(db.execute('SELECT 1 FROM follows WHERE user_id=? AND post_id=?',(uid,row['id'])).fetchone()),
                'commentsCount':db.execute('SELECT COUNT(*) FROM comments WHERE post_id=? AND removed=0',(row['id'],)).fetchone()[0],
                'updatesCount':db.execute('SELECT COUNT(*) FROM updates WHERE post_id=?',(row['id'],)).fetchone()[0]}

    def dispatch(self,db,user,method,path,q,data):
        uid=user['id']; now=int(self.clock()); route=path.removeprefix('/api/community/')
        if method=='GET' and route=='session': return {'user':{k:user[k] for k in ('id','name','username')},'csrf':user['csrf']},{}
        if method=='POST' and route=='logout':
            if data: raise ValueError('Invalid fields')
            db.execute('DELETE FROM sessions WHERE token=?',(user['token'],));return {'ok':True},{'Set-Cookie':self.cookie('',0)}
        if method=='GET' and route=='posts':
            where='p.withdrawn=0 AND p.id<?'; args=[self.before(q)]; mode=q.get('filter',['all'])[0]
            if mode=='mine': where+=' AND p.author_id=?';args.append(uid)
            elif mode=='following': where+=' AND EXISTS(SELECT 1 FROM follows f WHERE f.user_id=? AND f.post_id=p.id)';args.append(uid)
            elif mode!='all': raise ValueError('Invalid filter')
            rows=db.execute(f'SELECT p.* FROM posts p WHERE {where} ORDER BY p.id DESC LIMIT 21',args).fetchall()
            return {'items':[self.post_view(db,r,uid) for r in rows[:20]],'next':rows[19]['id'] if len(rows)>20 else None},{}
        if method=='POST' and route=='posts':
            if set(data)!={'card','narrative','request_id'}: raise ValueError('Invalid fields')
            rid=self.rid(data);content={'card':card_for_members(data['card']),**narrative(data['narrative'])}
            encoded=json.dumps(content,ensure_ascii=False,sort_keys=True,allow_nan=False); hashed=digest(encoded)
            old=db.execute('SELECT id,digest,withdrawn FROM posts WHERE author_id=? AND request_id=?',(uid,rid)).fetchone()
            if old:
                if old['digest']!=hashed or old['withdrawn']: raise ApiError(409,'这次发布已处理，请重新预览。')
                return {'id':old['id']},{}
            cursor=db.execute('INSERT INTO posts(author_id,request_id,digest,content,created) VALUES(?,?,?,?,?)',(uid,rid,hashed,encoded,now))
            return {'id':cursor.lastrowid},{}
        if method=='GET' and route=='activity':
            rows=db.execute('''SELECT e.id,e.post_id,e.kind,e.created,u.name,u.username,p.content FROM events e JOIN follows f ON f.post_id=e.post_id AND f.user_id=? JOIN posts p ON p.id=e.post_id JOIN users u ON u.id=e.actor_id WHERE p.withdrawn=0 AND e.id<? ORDER BY e.id DESC LIMIT 51''',(uid,self.before(q))).fetchall()
            return {'items':[{'id':r['id'],'postId':r['post_id'],'kind':r['kind'],'created':r['created'],'name':r['name'],'username':r['username'],'title':json.loads(r['content'])['title']} for r in rows[:50]],'next':rows[49]['id'] if len(rows)>50 else None},{}
        match=re.fullmatch(r'posts/(\d+)(?:/(comments|updates|follow|withdraw))?',route)
        if match:
            pid=int(match[1]); action=match[2]; post=self.active_post(db,pid)
            if method=='GET' and not action: return self.post_view(db,post,uid),{}
            if action in ('comments','updates'):
                table=action
                if method=='GET':
                    predicate=' AND removed=0' if table=='comments' else ''
                    rows=db.execute(f'SELECT c.*,u.name,u.username FROM {table} c JOIN users u ON u.id=c.author_id WHERE c.post_id=? AND c.id<?{predicate} ORDER BY c.id DESC LIMIT 51',(pid,self.before(q))).fetchall()
                    return {'items':[{'id':r['id'],'body':r['body'],'created':r['created'],'author':{'id':r['author_id'],'name':r['name'],'username':r['username']},'isOwn':r['author_id']==uid} for r in rows[:50]],'next':rows[49]['id'] if len(rows)>50 else None},{}
                if method=='POST':
                    if table=='updates' and post['author_id']!=uid: raise ApiError(403,'只有作者可以追加跟踪。')
                    validate(data,obj({'body':string(2000),'request_id':string(80)}));rid=self.rid(data);body=data['body'].strip()
                    if not body: raise ValueError('Empty text')
                    old=db.execute(f'SELECT * FROM {table} WHERE author_id=? AND request_id=?',(uid,rid)).fetchone()
                    if old:
                        if old['body']!=body or old['post_id']!=pid: raise ApiError(409,'提交编号已使用。')
                        return {'id':old['id']},{}
                    cursor=db.execute(f'INSERT INTO {table}(post_id,author_id,request_id,body,created) VALUES(?,?,?,?,?)',(pid,uid,rid,body,now))
                    db.execute('INSERT INTO events(post_id,actor_id,kind,created) VALUES(?,?,?,?)',(pid,uid,table,now))
                    return {'id':cursor.lastrowid},{}
            if method=='POST' and action=='follow':
                validate(data,obj({'following':{'type':'boolean'}}))
                if data['following']:db.execute('INSERT OR IGNORE INTO follows VALUES(?,?)',(uid,pid))
                else:db.execute('DELETE FROM follows WHERE user_id=? AND post_id=?',(uid,pid))
                return {'following':data['following']},{}
            if method=='POST' and action=='withdraw':
                if data: raise ValueError('Invalid fields')
                if post['author_id']!=uid: raise ApiError(403,'只能撤回自己发布的分享。')
                db.execute('UPDATE posts SET withdrawn=1 WHERE id=?',(pid,));return {'ok':True},{}
        match=re.fullmatch(r'comments/(\d+)/remove',route)
        if match and method=='POST':
            if data: raise ValueError('Invalid fields')
            row=db.execute('SELECT * FROM comments WHERE id=? AND removed=0',(int(match[1]),)).fetchone()
            if not row: raise ApiError(404,'评论已撤回。')
            self.active_post(db,row['post_id'])
            if row['author_id']!=uid:raise ApiError(403,'只能撤回自己的评论。')
            db.execute('UPDATE comments SET removed=1 WHERE id=?',(row['id'],));return {'ok':True},{}
        raise ApiError(404,'接口不存在。')
