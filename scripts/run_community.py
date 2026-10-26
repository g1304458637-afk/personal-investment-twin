"""Run the standalone member community. Never exposes private account/research APIs."""
import argparse
import os
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=18026)
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--database',type=Path,default=ROOT/'.local/community/community.sqlite3')
    parser.add_argument('--origin',action='append')
    parser.add_argument('--closed-registration',action='store_true')
    args=parser.parse_args()
    if not 1<=args.port<=65535:parser.error('Invalid port')
    origins=args.origin or ([os.environ['COMMUNITY_ORIGIN']] if os.environ.get('COMMUNITY_ORIGIN') else [f'http://127.0.0.1:{args.port}',f'http://localhost:{args.port}'])
    if args.host not in ('127.0.0.1','localhost','::1') and not all(x.startswith('https://') for x in origins):
        parser.error('External bindings require an explicit HTTPS --origin behind a TLS reverse proxy')
    from toujing_community.service import CommunityService
    from toujing_community.web import CommunityApp
    import uvicorn
    dist=ROOT/'apps/desktop/dist'
    if not (dist/'index.html').is_file():parser.error('Build apps/desktop first')
    app=CommunityApp(CommunityService(args.database,origins,registration=not args.closed_registration),dist)
    print(f'投镜多人社区：{origins[0]}/#/community',flush=True)
    uvicorn.run(app,host=args.host,port=args.port,access_log=False,proxy_headers=False,limit_concurrency=32,timeout_keep_alive=5)

if __name__=='__main__':main()
