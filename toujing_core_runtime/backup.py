"""Password-encrypted consistent backups and crash-recoverable whole-store restore."""
from __future__ import annotations
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import uuid
import zipfile
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from src.persistence.repository import SCHEMA_VERSION
from src.ledger.contracts import fingerprint

MAGIC = b'TOUJING-BACKUP-1\n'
LIMIT = 256 * 1024 * 1024
PREFERENCES = {'toujing.userStrategies', 'toujing.strategy', 'toujing.theme', 'toujing.locale', 'toujing.welcome.skip.v1'}


def preferences(raw):
    if not isinstance(raw, dict) or set(raw) - PREFERENCES or any(not isinstance(v, str) for v in raw.values()):
        raise ValueError('invalid backup preferences')
    if len(json.dumps(raw).encode()) > 2_000_000:
        raise ValueError('preferences too large')
    return raw


def _key(password, salt):
    if not isinstance(password, str) or not 12 <= len(password) <= 1024:
        raise ValueError('备份密码须为12至1024个字符；请自行保管，软件无法找回。')
    return Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(password.encode())


def _sync(directory):
    fd = os.open(directory, os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)


def _write(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as out:
        out.write(data); out.flush(); os.fsync(out.fileno())


def _copy(source, target):
    with sqlite3.connect(source) as src, sqlite3.connect(target) as dst:
        src.backup(dst)
    os.chmod(target, 0o600)


def recover_pending(path):
    """Rollback an interrupted cross-file restore before opening any services."""
    path = Path(path)
    marker = path.with_name(path.name + '.restore-pending.json')
    if not marker.exists(): return
    data = json.loads(marker.read_text())
    directory = path.parent / data['recovery_directory']
    # Directory names originate only in this process, never in an archive.
    if directory.parent != path.parent or not directory.name.startswith('restore-recovery-'):
        raise ValueError('invalid restore recovery marker')
    _copy(directory / 'facts.sqlite3', path)
    _copy(directory / 'chat.sqlite3', path.with_name(path.name + '.agent-chat.sqlite3'))
    marker.unlink(); _sync(path.parent)


class BackupRuntime:
    def __init__(self, product):
        self.product, self.repo = product, product.repo
        self.chat = self.repo.path.with_name(self.repo.path.name + '.agent-chat.sqlite3')

    def _active(self):
        review = self.product._review_runtime
        if review is None: return
        service = review._account_service
        if service is not None and (service._starting or any(not job.get('future').done() for job in service.jobs.values() if job.get('future') is not None)):
            raise ValueError('请等待当前AI任务结束后再备份或恢复。')
        # Review jobs can still write from a background worker. Never restore
        # while a live future exists, even if its UI result has been discarded.
        executor = getattr(review, 'executor', None)
        if executor is not None and any(not j['future'].done() for j in getattr(review, 'jobs', {}).values()):
            raise ValueError('请等待当前复盘任务结束。')

    def _chat_snapshot(self, target):
        if self.chat.exists(): _copy(self.chat, target)
        else:
            with sqlite3.connect(target) as db:
                db.execute('CREATE TABLE validated_conversations_v1(scope_key TEXT PRIMARY KEY,payload TEXT NOT NULL)')
            os.chmod(target, 0o600)

    def create(self, params):
        self._active()
        dest = Path(params.get('file_path', ''))
        if dest.suffix != '.tjbackup': raise ValueError('请选择 .tjbackup 文件')
        prefs = preferences(params.get('preferences', {}))
        salt, nonce = os.urandom(16), os.urandom(12)
        key = _key(params.get('backup_password'), salt)
        with tempfile.TemporaryDirectory(prefix='toujing-backup-') as tmp:
            root = Path(tmp); facts = root / 'facts.sqlite3'; chat = root / 'chat.sqlite3'
            with sqlite3.connect(facts) as target: self.repo.connection.backup(target)
            self._chat_snapshot(chat)
            if facts.stat().st_size + chat.stat().st_size > LIMIT: raise ValueError('expanded backup exceeds 256 MiB')
            pieces = {'facts.sqlite3': facts.read_bytes(), 'chat.sqlite3': chat.read_bytes(),
                'preferences.json': json.dumps(prefs, ensure_ascii=False).encode()}
            meta = {'schema': 'toujing_backup.v1', 'database_schema': SCHEMA_VERSION,
                'sha256': {k: hashlib.sha256(v).hexdigest() for k,v in pieces.items()},
                'excludes': ['Keychain/API credentials', 'market cache', 'diagnostic logs'],
                'accounts': self.repo.list_accounts()}
            if sum(len(v) for v in pieces.values()) + len(json.dumps(meta).encode()) > LIMIT: raise ValueError('expanded backup exceeds 256 MiB')
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
                for name, value in {**pieces, 'manifest.json': json.dumps(meta).encode()}.items(): archive.writestr(name, value)
            data = stream.getvalue()
            if len(data) > LIMIT: raise ValueError('backup exceeds 256 MiB')
            encrypted = MAGIC + salt + nonce + AESGCM(key).encrypt(nonce, data, MAGIC)
            _write(dest, encrypted); _sync(dest.parent)
        return {'filename': dest.name, 'sha256': hashlib.sha256(encrypted).hexdigest(),
            'accounts': len(meta['accounts']), 'encrypted': True, 'excludes': meta['excludes']}

    def _read(self, params):
        path = Path(params.get('file_path', ''))
        if path.suffix != '.tjbackup' or path.stat().st_size > LIMIT + 1024:
            raise ValueError('invalid backup file or size')
        raw = path.read_bytes()
        if not raw.startswith(MAGIC): raise ValueError('unsupported backup format')
        offset = len(MAGIC); salt, nonce = raw[offset:offset+16], raw[offset+16:offset+28]
        try: data = AESGCM(_key(params.get('backup_password'), salt)).decrypt(nonce, raw[offset+28:], MAGIC)
        except Exception as exc: raise ValueError('密码不正确或备份已损坏') from exc
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = archive.namelist()
            expected = {'facts.sqlite3', 'chat.sqlite3', 'preferences.json', 'manifest.json'}
            if len(names) != 4 or set(names) != expected or sum(x.file_size for x in archive.infolist()) > LIMIT:
                raise ValueError('invalid backup members or expanded size')
            pieces = {name: archive.read(name) for name in names}
        meta = json.loads(pieces['manifest.json'])
        if meta.get('schema') != 'toujing_backup.v1' or meta.get('database_schema') != SCHEMA_VERSION:
            raise ValueError('unsupported backup schema')
        for name in expected - {'manifest.json'}:
            if meta.get('sha256', {}).get(name) != hashlib.sha256(pieces[name]).hexdigest(): raise ValueError('backup checksum mismatch')
        prefs = preferences(json.loads(pieces['preferences.json']))
        with tempfile.TemporaryDirectory(prefix='toujing-verify-') as tmp:
            for name in ('facts.sqlite3', 'chat.sqlite3'):
                target = Path(tmp) / name; _write(target, pieces[name])
                with sqlite3.connect(target) as db:
                    if db.execute("SELECT 1 FROM sqlite_master WHERE type IN ('trigger','view') LIMIT 1").fetchone(): raise ValueError('backup cannot contain executable schema objects')
                    if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok': raise ValueError('invalid SQLite backup')
                    if name == 'facts.sqlite3':
                        if db.execute('PRAGMA user_version').fetchone()[0] != SCHEMA_VERSION: raise ValueError('database version mismatch')
                        accounts = [dict(zip(('subject_id','account_id','display_name'), row)) for row in db.execute('SELECT subject_id,account_id,display_name FROM accounts')]
                        if db.execute('PRAGMA foreign_key_check').fetchone(): raise ValueError('backup foreign key violation')
                    else: db.execute('SELECT scope_key,payload FROM validated_conversations_v1').fetchall()
        return pieces, prefs, accounts, hashlib.sha256(raw).hexdigest()

    def _state(self):
        # Entire logical fact store, including notes/research; a new write
        # invalidates restore confirmation. No plaintext leaves the process.
        chat = []
        if self.chat.exists():
            with sqlite3.connect(self.chat) as db: chat = list(db.iterdump())
        return fingerprint([list(self.repo.connection.iterdump()), chat])

    def preview(self, params):
        _, prefs, accounts, sha = self._read(params)
        return {'accounts': accounts, 'preference_keys': sorted(prefs), 'archive_sha256': sha,
            'preview_fingerprint': fingerprint([sha, self._state()]),
            'warning': '恢复将替换本机全部账户、复盘、聊天、自建策略和所列偏好。现有数据先保存本机恢复副本；共享授权全部撤销；API密钥须另行配置。'}

    def restore(self, params):
        self._active()
        pieces, prefs, _, sha = self._read(params)
        if params.get('expected_preview_fingerprint') != fingerprint([sha, self._state()]): raise ValueError('恢复预览已失效，请重新预览')
        if params.get('confirm_replace_all') is not True: raise ValueError('whole-store replacement confirmation required')
        review = self.product._review_runtime
        if review is not None:
            review.close(); self.product._review_runtime = None
        parent = self.repo.path.parent
        recovery = parent / ('restore-recovery-' + uuid.uuid4().hex); recovery.mkdir(mode=0o700)
        with sqlite3.connect(recovery / 'facts.sqlite3') as db: self.repo.connection.backup(db)
        os.chmod(recovery / 'facts.sqlite3', 0o600)
        self._chat_snapshot(recovery / 'chat.sqlite3')
        _sync(recovery)
        marker = self.repo.path.with_name(self.repo.path.name + '.restore-pending.json')
        _write(marker, json.dumps({'recovery_directory': recovery.name}).encode()); _sync(parent)
        token = uuid.uuid4().hex
        try:
            with tempfile.TemporaryDirectory(prefix='toujing-restore-') as tmp:
                root = Path(tmp)
                for name in ('facts.sqlite3', 'chat.sqlite3'): _write(root / name, pieces[name])
                with sqlite3.connect(root / 'facts.sqlite3') as source: source.backup(self.repo.connection)
                _copy(root / 'chat.sqlite3', self.chat)
            with self.repo.connection as db:
                tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if 'review_shares_v1' in tables: db.execute('UPDATE review_shares_v1 SET revoked=1')
                db.execute('DELETE FROM desktop_restore_preferences')
                db.execute('INSERT INTO desktop_restore_preferences VALUES(?,?,0)', (token, json.dumps(prefs)))
            marker.unlink(); _sync(parent)
        except Exception:
            with sqlite3.connect(recovery / 'facts.sqlite3') as source: source.backup(self.repo.connection)
            _copy(recovery / 'chat.sqlite3', self.chat)
            marker.unlink(); _sync(parent)
            raise
        return {'restored': True, 'restore_id': token, 'preferences': prefs, 'recovery_directory': recovery.name}

    def pending(self, params):
        row = self.repo.connection.execute('SELECT restore_id,payload_json FROM desktop_restore_preferences WHERE applied=0 ORDER BY rowid DESC LIMIT 1').fetchone()
        return {'pending': None if row is None else {'restore_id': row[0], 'preferences': json.loads(row[1])}}

    def ack(self, params):
        with self.repo.connection as db: db.execute('UPDATE desktop_restore_preferences SET applied=1 WHERE restore_id=?', (params.get('restore_id'),))
        return {'acknowledged': True}
