"""Exclusive AI slot with revocable grants; documents stay machine-shared."""
import hashlib
import json
import os
import pathlib
import secrets
import threading
import time
import uuid


class AccessDenied(ValueError):
    pass


def digest(value):
    return hashlib.sha256(value.encode('utf8')).hexdigest()


def empty_draft(font_id):
    from backend.mcp_bridge import NUMBERS, GRID, HUMAN, ENUMS
    from backend.humanization import settings
    fields = {field: str(default) for field, default in (*NUMBERS.values(), *GRID.values())}
    fields.update({field: default for field, _, default in ENUMS.values()})
    fields.update(lineSizing='size', smartBalance=False, allowOverlap=False, gridDrawLines=False,
                  humanStrength='custom')
    for key, field in HUMAN.items():
        value = settings({})[key]
        fields[field] = value if type(value) is bool else str(value)
    return dict(layoutMode='notebook', pages=[''], fields=fields, font_mix=[dict(font_id=font_id, weight=100, scope='all')],
        modeDrafts={}, sourceIndex=0, outputIndex=0, selectedPreset='', selectedFontPreset='',
        previewValid=False, previewStale=False)


class Workbench:
    def __init__(self, jobs):
        self.root = pathlib.Path(jobs) / '.workbench'
        self.root.mkdir(exist_ok=True)
        self.file = self.root / 'access.json'
        self.lock = threading.RLock()
        self.attempts = []
        if self.file.exists():
            self.data = json.loads(self.file.read_text(encoding='utf8'))
        else:
            self.data = dict(profiles={}, owner=None, grants={}, pairing=None)

    def save(self):
        temp = self.file.with_suffix('.tmp')
        with temp.open('w', encoding='utf8') as stream:
            json.dump(self.data, stream, ensure_ascii=False, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, self.file)

    def grant(self, key):
        return self.data['grants'].get(digest(key)) if key and self.data['owner'] else None

    def web_allowed(self, profile_key):
        profile = self.data['profiles'].get(digest(profile_key)) if profile_key else None
        return bool(profile and profile.get('web_access'))

    def require(self, key, browser=False):
        grant = self.grant(key)
        if not grant or grant['user'] != self.data['owner']['user']:
            raise AccessDenied('请先领取 AI 档口或使用本轮配对码连接；原占用可能已结束')
        if browser and grant['role'] != 'browser':
            raise AccessDenied('此操作需在已配对的网页中执行')
        return grant

    def status(self, key=''):
        grant = self.grant(key)
        owner = self.data['owner']
        return dict(required=True, occupied=bool(owner), mine=bool(grant),
                    owner_name=owner['name'] if owner else None,
                    session_id=owner['session'] if owner else None,
                    role=grant['role'] if grant else None,
                    user_id=grant['user'] if grant else None)

    def new_grant(self, user, role):
        key = secrets.token_urlsafe(32)
        self.data['grants'][digest(key)] = dict(user=user, role=role)
        return key

    def claim(self, name, profile_key='', role='browser'):
        if self.data['owner']:
            raise AccessDenied('AI 档口正在由 ' + self.data['owner']['name'] + ' 使用，请等待对方退出 AI 占用')
        if role not in ('browser', 'ai'):
            raise ValueError('客户端类型无效')
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 40 or any(ord(c) < 32 for c in name):
            raise ValueError('请填写 1–40 字的使用者名称')
        profile = self.data['profiles'].get(digest(profile_key)) if profile_key else None
        if profile_key and not profile:
            raise AccessDenied('个人凭证无效，请使用原浏览器或重新领取新身份')
        if not profile:
            profile_key = secrets.token_urlsafe(32)
            profile = dict(user=uuid.uuid4().hex, name=name.strip(), web_access=role == 'browser')
            self.data['profiles'][digest(profile_key)] = profile
        elif role == 'browser':
            profile['web_access'] = True
        self.data['owner'] = dict(user=profile['user'], name=name.strip(), session=uuid.uuid4().hex)
        self.data['grants'] = {}
        self.data['pairing'] = None
        key = self.new_grant(profile['user'], role)
        self.save()
        return dict(key=key, profile_key=profile_key, **self.status(key))

    def pair(self, key, kind='ai'):
        self.require(key)
        if kind not in ('ai', 'browser'):
            raise ValueError('配对类型无效')
        code = secrets.token_hex(6).upper()
        self.data['pairing'] = dict(hash=digest(code), expires=time.time() + 300, kind=kind)
        self.save()
        return dict(code=code, expires_at=self.data['pairing']['expires'], kind=kind)

    def redeem(self, code, expected_kind=None):
        now = time.time()
        self.attempts = [t for t in self.attempts if t > now - 60]
        if len(self.attempts) >= 20:
            raise AccessDenied('配对尝试过多，请一分钟后重试')
        self.attempts.append(now)
        pair = self.data['pairing']
        if (not isinstance(code, str) or not pair or not self.data['owner']
                or pair['expires'] < now or digest(code.strip().upper()) != pair['hash']):
            raise AccessDenied('配对码无效、已使用或已过期，请重新生成')
        kind = pair['kind']
        if expected_kind and kind != expected_kind:
            raise AccessDenied('配对码用途不符，请生成用于 ' + expected_kind + ' 的配对码')
        user = self.data['owner']['user']
        key = self.new_grant(user, kind)
        self.data['pairing'] = None
        result = dict(key=key, **self.status(key))
        profile_key = secrets.token_urlsafe(32)
        self.data['profiles'][digest(profile_key)] = dict(user=user, name=self.data['owner']['name'], web_access=kind == 'browser')
        result['profile_key'] = profile_key
        self.save()
        return result

    def release(self, key):
        self.require(key)
        self.data.update(owner=None, grants={}, pairing=None)
        self.save()
        return self.status()

    def library(self, key):
        directory = self.root / 'library'
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def list_documents(self, key):
        records = [json.loads(p.read_text(encoding='utf8')) for p in self.library(key).glob('*.json')]
        return dict(documents=[dict(id=r['id'], title=r['title'], saved_at=r['saved_at'],
                                    source_pages=len(r['workspace']['draft']['pages']))
                               for r in sorted(records, key=lambda r: r['saved_at'], reverse=True)])

    def snapshot(self, key, workspace, title=''):
        if not isinstance(title, str) or len(title) > 80:
            raise ValueError('文档名称最多 80 字')
        record = dict(id=uuid.uuid4().hex, title=title.strip() or '未命名文档',
                      saved_at=time.time(), workspace=workspace)
        path = self.library(key) / (record['id'] + '.json')
        temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps(record, ensure_ascii=False, allow_nan=False), encoding='utf8')
        os.replace(temp, path)
        return dict(id=record['id'], title=record['title'], saved_at=record['saved_at'])

    def read_document(self, key, document_id):
        if not isinstance(document_id, str) or len(document_id) != 32 or any(c not in '0123456789abcdef' for c in document_id):
            raise ValueError('文档编号无效')
        path = self.library(key) / (document_id + '.json')
        if not path.exists():
            raise AccessDenied('找不到本机共享文档，请刷新文档列表')
        return json.loads(path.read_text(encoding='utf8'))

