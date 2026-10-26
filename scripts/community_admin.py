"""Offline community administration; no public admin endpoint or embedded admin password."""
import argparse
import getpass
import os
import sqlite3
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def snapshot(source: Path, target: Path, *, invalidate_sessions=False):
    """Consistent SQLite backup/restore into a new file, never overwrite a live DB."""
    if not source.is_file():raise ValueError('Source database does not exist')
    with sqlite3.connect(f'{source.resolve().as_uri()}?mode=ro',uri=True) as src:
        if src.execute('PRAGMA user_version').fetchone()[0]!=1 or src.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
            raise ValueError('Invalid community database')
        fd=os.open(target,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
        with sqlite3.connect(target) as dest:
            src.backup(dest)
            if invalidate_sessions:dest.execute('DELETE FROM sessions')
            if dest.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Snapshot validation failed')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--database',type=Path,required=True)
    commands=p.add_subparsers(dest='command',required=True)
    for name in ('backup','restore-to-new-file'):
        c=commands.add_parser(name);c.add_argument('target',type=Path)
    c=commands.add_parser('disable-user');c.add_argument('username')
    c=commands.add_parser('reset-password');c.add_argument('username')
    c=commands.add_parser('withdraw-post');c.add_argument('post_id',type=int)
    args=p.parse_args()
    if args.command in ('backup','restore-to-new-file'):
        snapshot(args.database,args.target,invalidate_sessions=args.command=='restore-to-new-file');print('Snapshot verified:',args.target);return
    if not args.database.is_file():p.error('Community database is missing')
    with sqlite3.connect(args.database) as db:
        if db.execute('PRAGMA user_version').fetchone()[0]!=1:p.error('Unsupported database version')
        if args.command=='withdraw-post':
            changed=db.execute('UPDATE posts SET withdrawn=1 WHERE id=?',(args.post_id,)).rowcount
        else:
            user=db.execute('SELECT id FROM users WHERE username=?',(args.username.lower(),)).fetchone()
            if not user:p.error('Unknown username')
            if args.command=='disable-user':db.execute('UPDATE users SET disabled=1 WHERE id=?',(user[0],))
            else:
                password=getpass.getpass('New password (12–128 characters): ')
                if not 12<=len(password)<=128 or password!=getpass.getpass('Confirm new password: '):p.error('Password invalid or not matching')
                from toujing_community.service import password_hash
                db.execute('UPDATE users SET password=? WHERE id=?',(password_hash(password),user[0]))
            db.execute('DELETE FROM sessions WHERE user_id=?',(user[0],));changed=1
        if not changed:p.error('Object not found')
    print('Updated. Account sessions revoked when applicable.')

if __name__=='__main__':main()
