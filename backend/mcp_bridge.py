"""MCP-facing document operations over the existing business HTTP API.

No controller transport, serial access or model credentials live in this module.
"""
import copy
import json
import math
import os
import pathlib
import re
import threading
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler

from backend.document import configuration
from backend.humanization import LIMITS, settings as human_settings


# Canonical API name -> browser field and default. Machine settings deliberately
# aren't editable through this document interface.
NUMBERS = {
    'width': ('width', 210), 'height': ('height', 297),
    'margin_top': ('marginTop', 30), 'margin_bottom': ('marginBottom', 30),
    'margin_left': ('marginLeft', 30), 'margin_right': ('marginRight', 30),
    'rows': ('rows', 20), 'size': ('size', 5), 'latin_size': ('latinSize', 5),
    'spacing': ('spacing', .9), 'punctuation_width': ('punctuationWidth', .8),
    'line_looseness': ('lineLooseness', 2.37),
    'letter_scale': ('letterScale', 100), 'digit_scale': ('digitScale', 100),
}
GRID = {'columns': ('gridColumns', 20), 'row_gap': ('gridRowGap', 2.9),
        'column_gap': ('gridColumnGap', 0), 'size_percent': ('gridSizePercent', 80),
        'padding': ('gridPadding', .3)}
ENUMS = {'pagination': ('pagination', ('auto', 'fixed'), 'auto'),
         'input_format': ('inputFormat', ('plain', 'markdown'), 'plain'),
         'line_sizing': ('lineSizing', ('rows', 'size'), 'rows')}
HUMAN = {key: 'human' + key.title() for key in LIMITS}
HUMAN.update(enabled='humanEnabled', cursive_style='humanCursiveStyle',
             stroke_mode='humanStrokeMode', stroke_probability='humanStrokeProbability')
HUMAN.update({key + '_enabled': 'human' + key.title() + 'Enabled' for key in LIMITS})


def check_pages(pages):
    if (not isinstance(pages, list) or not 1 <= len(pages) <= 100
            or any(not isinstance(p, str) for p in pages)
            or sum(map(len, pages)) > 30000
            or any(ord(c) < 32 and c not in '\n\r\t' for p in pages for c in p)):
        raise ValueError('文档需要 1–100 个字符串页面，全文最多 30000 字，不得包含控制字符')


def finite(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError('排版参数必须为有限数字')
    return value


def render_data(draft, device):
    """Translate the existing browser draft without inventing a second format."""
    fields = draft['fields']
    result = {key: float(fields.get(field, default))
              for key, (field, default) in NUMBERS.items()}
    result.update({key: fields.get(field, default)
                   for key, (field, _, default) in ENUMS.items()})
    result.update(layout_mode=draft['layoutMode'], line_placement='ink',
                  smart_balance=fields.get('smartBalance', False), allow_overlap=False,
                  font_mix=copy.deepcopy(draft['font_mix']),
                  pages=[dict(text=p) for p in draft['pages']], device_port=device)
    result['grid'] = {key: float(fields.get(field, default))
                      for key, (field, default) in GRID.items()}
    result['grid']['draw_lines'] = fields.get('gridDrawLines', False)
    boolean_keys = {'enabled', *(key + '_enabled' for key in LIMITS)}
    result['humanization'] = {
        key: (fields[field] if key in boolean_keys or key in ('cursive_style', 'stroke_mode')
              else float(fields[field]))
        for key, field in HUMAN.items() if field in fields}
    # Preserve the user's current machine configuration only for preview output.
    result.update(feed=float(fields.get('feed', 10000)), move_feed=float(fields.get('moveFeed', 10000)),
                  coordinate_system=dict(reverse_x=fields.get('reverseX', False),
                      reverse_y=fields.get('reverseY', False), swap_xy=fields.get('swapXY', False),
                      origin=fields.get('originCorner', 'top-left')),
                  device_control=dict(controller_type=fields.get('controllerType', 'kenjoy-grbl'),
                      pen_up=float(fields.get('penUpZ', 0)), pen_down=float(fields.get('penDownZ', 10)),
                      pen_feed=float(fields.get('penFeed', 600))))
    check_pages(draft['pages'])
    configuration(result)
    return result


def edit_draft(original, pages=None, settings=None, font_mix=None):
    draft = copy.deepcopy(original)
    if not isinstance(settings if settings is not None else {}, dict):
        raise ValueError('settings 必须为对象')
    settings = settings or {}
    unknown = set(settings) - set(NUMBERS) - set(ENUMS) - {
        'layout_mode', 'grid', 'humanization', 'smart_balance'}
    if unknown:
        raise ValueError('不支持的文档参数：' + ', '.join(sorted(unknown)))
    fields = draft['fields']
    for key in NUMBERS.keys() & settings.keys():
        value = finite(settings[key])
        if key == 'rows' and (value != int(value) or not 1 <= value <= 200):
            raise ValueError('rows 必须为 1–200 之间的整数')
        fields[NUMBERS[key][0]] = str(value)
    for key in ENUMS.keys() & settings.keys():
        field, choices, _ = ENUMS[key]
        if settings[key] not in choices:
            raise ValueError(f'{key} 必须为 {choices}')
        fields[field] = settings[key]
    if 'layout_mode' in settings:
        if settings['layout_mode'] not in ('notebook', 'grid'):
            raise ValueError('layout_mode 必须为 notebook 或 grid')
        draft['layoutMode'] = settings['layout_mode']
    if 'smart_balance' in settings:
        if type(settings['smart_balance']) is not bool:
            raise ValueError('smart_balance 必须为布尔值')
        fields['smartBalance'] = settings['smart_balance']
    if 'grid' in settings:
        grid = settings['grid']
        if not isinstance(grid, dict) or set(grid) - set(GRID) - {'draw_lines'}:
            raise ValueError('grid 参数无效')
        for key in GRID.keys() & grid.keys():
            fields[GRID[key][0]] = str(finite(grid[key]))
        if 'draw_lines' in grid:
            if type(grid['draw_lines']) is not bool:
                raise ValueError('draw_lines 必须为布尔值')
            fields['gridDrawLines'] = grid['draw_lines']
    if 'humanization' in settings:
        patch = settings['humanization']
        if not isinstance(patch, dict) or set(patch) - set(HUMAN):
            raise ValueError('humanization 参数无效')
        current = render_data(draft, 'default')['humanization']
        validated = human_settings(dict(humanization=dict(current, **patch)))
        for key, field in HUMAN.items():
            fields[field] = validated[key] if type(validated[key]) is bool else str(validated[key])
    if pages is not None:
        check_pages(pages)
        draft['pages'] = list(pages)
    if font_mix is not None:
        if (not isinstance(font_mix, list) or not 1 <= len(font_mix) <= 16
                or any(not isinstance(f, dict) or not isinstance(f.get('font_id'), str)
                       or set(f) - {'font_id', 'weight', 'scope', 'name'}
                       or f.get('scope', 'all') not in ('all', 'zh', 'en')
                       for f in font_mix)):
            raise ValueError('字体组合需要 1–16 种有效字体')
        for f in font_mix:
            if not 0 <= finite(f.get('weight', 100)) <= 1000000:
                raise ValueError('字体权重须为 0–1000000')
        if not any(f.get('weight', 100) > 0 for f in font_mix):
            raise ValueError('至少一种字体权重须大于零')
        draft['font_mix'] = copy.deepcopy(font_mix)
    if draft['layoutMode'] not in ('notebook', 'grid'):
        raise ValueError('请先选择排版模式，或在 settings 中指定 layout_mode')
    draft.update(sourceIndex=min(draft.get('sourceIndex', 0), len(draft['pages']) - 1),
                 outputIndex=0, previewValid=True, previewStale=False)
    if settings:
        draft['selectedPreset'] = ''
    if font_mix is not None:
        draft['selectedFontPreset'] = ''
    # Old per-mode snapshots must not restore settings from before the AI edit.
    draft['modeDrafts'] = {}
    return draft


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class PlotterBridge:
    def __init__(self, base_url=None, token=None, timeout=120, state_file=None):
        self.base_url = (base_url or os.environ.get('PLOTTER_API_URL', 'http://127.0.0.1:8080')).rstrip('/')
        parsed = urlsplit(self.base_url)
        if (parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username
                or parsed.password or parsed.path or parsed.query or parsed.fragment):
            raise ValueError('PLOTTER_API_URL 必须为 http(s) 服务地址，不含路径或凭据')
        self.token = os.environ.get('PLOTTER_TOKEN', '') if token is None else token
        self.timeout = timeout
        self.opener = build_opener(ProxyHandler({}), NoRedirect())
        self.state_file = pathlib.Path(state_file) if state_file else None
        self.state_lock = threading.RLock()
        self.sessions = {}
        if self.state_file and self.state_file.exists():
            self.sessions = json.loads(self.state_file.read_text(encoding='utf8')).get(self.base_url, {})

    def save_session(self, controller, result):
        with self.state_lock:
            self.sessions[controller] = dict(self.sessions.get(controller, {}), **result)
            if self.state_file:
                self.state_file.parent.mkdir(parents=True, exist_ok=True)
                stored = json.loads(self.state_file.read_text(encoding='utf8')) if self.state_file.exists() else {}
                stored[self.base_url] = self.sessions
                temp = self.state_file.with_name(self.state_file.name + '.' + uuid.uuid4().hex + '.tmp')
                temp.write_text(json.dumps(stored, ensure_ascii=False), encoding='utf8')
                if os.name != 'nt':
                    temp.chmod(0o600)
                temp.replace(self.state_file)

    def request(self, path, controller=None, data=None):
        headers = {'Accept': 'application/json', 'X-Workbench-Client': 'ai'}
        if controller is not None:
            if not isinstance(controller, str) or not controller or len(controller) > 200:
                raise ValueError('需要明确指定 controller')
            headers['X-Plotter-Controller'] = controller
            key = self.sessions.get(controller, {}).get('key')
            if key:
                headers['X-Workbench-Key'] = key
        if self.token:
            headers['Authorization'] = 'Bearer ' + self.token
        body = None
        if data is not None:
            body = json.dumps(data, ensure_ascii=False, allow_nan=False).encode('utf8')
            if len(body) > 524288:
                raise ValueError('请求超过服务端 512 KiB 限制')
            headers['Content-Type'] = 'application/json'
        try:
            with self.opener.open(Request(self.base_url + path, data=body, headers=headers),
                                  timeout=self.timeout) as response:
                return json.load(response)
        except HTTPError as error:
            try:
                message = json.load(error).get('error', 'HTTP ' + str(error.code))
            except (ValueError, AttributeError):
                message = 'HTTP ' + str(error.code)
            raise ValueError('写字台服务：' + message) from None
        except (URLError, TimeoutError) as error:
            raise ValueError('无法连接写字台服务，请检查 PLOTTER_API_URL、服务状态和访问令牌') from error

    def controllers(self):
        return self.request('/api/controllers')

    def fonts(self, controller):
        return self.request('/api/fonts', controller)

    def workbench_status(self, controller):
        return self.request('/api/workbench/status', controller)

    def pair_workbench(self, controller, code):
        result = self.request('/api/workbench/redeem', controller, dict(code=code, kind='ai'))
        self.save_session(controller, result)
        return {key: value for key, value in result.items() if key not in ('key', 'profile_key')}

    def claim_workbench(self, controller, name):
        result = self.request('/api/workbench/claim', controller,
            dict(name=name, role='ai', profile_key=self.sessions.get(controller, {}).get('profile_key', '')))
        self.save_session(controller, result)
        code = self.request('/api/workbench/pair', controller, dict(kind='browser'))
        return dict(owner_name=result['owner_name'], session_id=result['session_id'], browser_pairing=code,
                    message='已领取，请在网页“已在 AI 中领取”处输入网页配对码，检查预览并操作机器。')

    def browser_pairing(self, controller):
        return self.request('/api/workbench/pair', controller, dict(kind='browser'))

    def release_workbench(self, controller):
        result = self.request('/api/workbench/release', controller, {})
        self.save_session(controller, dict(key=''))
        return result

    def list_documents(self, controller):
        return self.request('/api/library', controller)

    def save_document(self, controller, device, expected_revision, title):
        return self.request('/api/library/save', controller, dict(device=device, expected_revision=expected_revision, title=title))

    def load_document(self, controller, device, expected_revision, document_id):
        return self.request('/api/library/load', controller, dict(device=device, expected_revision=expected_revision, id=document_id))

    def create_document(self, controller, device, expected_revision, pages, title, settings=None, font_mix=None):
        if not isinstance(title, str) or len(title) > 80:
            raise ValueError('文档名称最多 80 字')
        before = self.read_workspace(controller, device)
        if before.get('draft') and any(p.strip() for p in before['draft']['pages']):
            self.save_document(controller, device, expected_revision, 'AI 创建前自动备份')
        result = self.update(controller, device, expected_revision, pages, settings, font_mix)
        result['saved_document'] = self.save_document(controller, device, result['revision'], title)
        return result

    @staticmethod
    def workspace_path(device):
        if not isinstance(device, str) or not device or len(device) > 200:
            raise ValueError('需要明确指定 device；未选端口的网页使用 default')
        return '/api/workspaces/' + quote(device, safe='')

    def read_workspace(self, controller, device):
        workspace = self.request(self.workspace_path(device), controller)
        if workspace.get('draft'):
            try:
                render = render_data(workspace['draft'], device)
                editable = set(NUMBERS) | set(ENUMS) | {'layout_mode', 'smart_balance', 'grid', 'humanization'}
                workspace['editable_settings'] = {key: value for key, value in render.items() if key in editable}
            except (ValueError, TypeError, KeyError):
                # Incomplete drafts remain readable so the host can repair them.
                workspace['layout_notice'] = '当前排版参数尚不完整，请在网页完成设置或通过 settings 修正'
        return workspace

    def candidate(self, controller, device, expected_revision, pages, settings, font_mix):
        workspace = self.read_workspace(controller, device)
        if type(expected_revision) is not int or expected_revision != workspace['revision']:
            raise ValueError('文档版本冲突；请重新读取，合并最新内容后再操作')
        if not workspace['draft']:
            raise ValueError('请先在网页选择设备并打开文档，再读取和编辑此工作区')
        draft = edit_draft(workspace['draft'], pages, settings, font_mix)
        return draft, render_data(draft, device)

    def summarize(self, result):
        pages = result.get('pages', [result])
        return dict(document_id=result.get('document_id'), page_count=len(pages),
                    pages=[dict(page=i + 1, job_id=p['job_id'], metadata=p['metadata'])
                           for i, p in enumerate(pages)])

    def preview(self, controller, device, expected_revision, pages=None, settings=None, font_mix=None):
        _, render = self.candidate(controller, device, expected_revision, pages, settings, font_mix)
        return self.summarize(self.request('/api/preview', controller, render))

    def update(self, controller, device, expected_revision, pages=None, settings=None, font_mix=None):
        draft, render = self.candidate(controller, device, expected_revision, pages, settings, font_mix)
        result = self.request(self.workspace_path(device), controller,
                              dict(revision=expected_revision, draft=draft, render=render))
        if result['conflict']:
            raise ValueError('文档版本冲突；本次修改未写入，请重新读取并合并')
        workspace = result['workspace']
        return dict(revision=workspace['revision'], document_id=workspace['document_id'],
                    message='内容与预览已同步到网页；请在网页检查输出页面。')

    def get_preview(self, controller, document_id, page=1, include_svg=False):
        if not isinstance(document_id, str) or not re.fullmatch('[a-f0-9]{32}', document_id):
            raise ValueError('document_id 无效')
        result = self.request('/api/documents/' + document_id + '/preview', controller)
        if type(page) is not int or not 1 <= page <= len(result['pages']):
            raise ValueError('预览页码超出范围')
        selected = result['pages'][page - 1]
        return dict(document_id=document_id, page_count=len(result['pages']), page=page,
                    job_id=selected['job_id'], metadata=selected['metadata'],
                    **({'svg': selected['svg']} if include_svg else {}))


def capabilities():
    return dict(settings=dict(numeric=list(NUMBERS), enums={k: list(v[1]) for k, v in ENUMS.items()},
                layout_mode=['notebook', 'grid'], smart_balance='boolean',
                grid=list(GRID) + ['draw_lines'],
                humanization=dict(limits=LIMITS, switches=['enabled'] + [k + '_enabled' for k in LIMITS],
                                  cursive_style=['short', 'thread', 'copybook'],
                                  stroke_mode=['single', 'multi'], stroke_probability='0–100')),
                limits=dict(source_pages=100, characters=30000, fonts=16),
                workflow=['list_controllers', 'pair_workbench', 'read_workspace', 'list_fonts',
                          'create_document', 'preview_document', 'get_preview_image',
                          'update_document', 'get_machine_state', 'release_workbench'],
                sharing='网页共同编辑本机文档、预览和进度；只独占 AI 档口。退出 AI 不停止运行中的页面。',
                example=dict(settings=dict(line_sizing='size', size=4, latin_size=4, line_looseness=2,
                    humanization=dict(enabled=True, scale=3, rotation=1, baseline=.2))),
                content_optimization='由宿主 AI 润色后传入 pages；保留事实、公式和显式分页，只有用户要求时才改写。')
