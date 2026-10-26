"""ASGI host exposing community APIs and frontend assets only."""
import asyncio
import json
import mimetypes
from pathlib import Path
from urllib.parse import unquote
from .service import CommunityService

HEADERS = {'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer','X-Frame-Options':'DENY',
           'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' blob:; worker-src 'self' blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"}


class CommunityApp:
    def __init__(self, service: CommunityService, dist: Path):
        self.service, self.dist = service, dist.resolve()

    async def __call__(self, scope, receive, send):
        if scope['type']=='lifespan':
            while True:
                event=await receive()
                if event['type']=='lifespan.startup':await send({'type':'lifespan.startup.complete'})
                elif event['type']=='lifespan.shutdown':await send({'type':'lifespan.shutdown.complete'});return
        if scope['type']!='http':return
        headers={k.decode().lower():v.decode() for k,v in scope['headers']}
        status=200; extra={}; content_type='application/json'; body=b''
        method=scope['method'];path=scope['path']
        if headers.get('host') not in self.service.hosts:
            status=403;response={'error':'请求来源不受信任。'}
        elif path.startswith('/api/community/'):
            while True:
                event=await receive()
                if event['type']=='http.disconnect':return
                body+=event.get('body',b'')
                if len(body)>128*1024:
                    status=413;response={'error':'分享内容过大。'};break
                if not event.get('more_body'):
                    target=path+('?' + scope.get('query_string',b'').decode() if scope.get('query_string') else '')
                    status,response,extra=await asyncio.to_thread(self.service.request,method,target,headers,body,scope.get('client',('local',0))[0])
                    break
        elif path.startswith('/api/'):
            status=404;response={'error':'接口不存在。'}
        elif method not in ('GET','HEAD'):
            status=405;response={'error':'请求方法不支持。'}
        else:
            target=(self.dist/unquote(path).lstrip('/')).resolve()
            if not target.is_relative_to(self.dist):
                status=403;response={'error':'无效路径。'}
            else:
                if not target.is_file() and not target.suffix:target=self.dist/'index.html'
                try:
                    response=await asyncio.to_thread(target.read_bytes)
                    content_type=mimetypes.guess_type(target.name)[0] or 'application/octet-stream'
                except OSError:status=404;response={'error':'文件不存在。'}
        payload=response if isinstance(response,bytes) else json.dumps(response,ensure_ascii=False,allow_nan=False).encode()
        outgoing={**HEADERS,'Content-Type':content_type,'Content-Length':str(len(payload)),**extra}
        if self.service.secure:outgoing['Strict-Transport-Security']='max-age=31536000'
        await send({'type':'http.response.start','status':status,'headers':[(k.lower().encode(),v.encode()) for k,v in outgoing.items()]})
        await send({'type':'http.response.body','body':b'' if method=='HEAD' else payload})
