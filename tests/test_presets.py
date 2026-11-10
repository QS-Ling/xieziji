import concurrent.futures
import copy
import json
import pathlib
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from backend.presets import Presets
from backend.server import Application, create_server
from tests.test_service import FONT_DIR, test_temp
from tests.test_preview_store import NoMachine


def example(name='日常', id='custom-1'):
    return dict(id=id, name=name, values=dict(width=210, height=297, rows=20, size=5),
                lineSizing='rows', lineLooseness=2.37, smartBalance=True,
                humanization=dict(enabled=True, scale=5, vertical=.3, rotation=2, spacing=.2, baseline=.4,
                                  scale_enabled=True, vertical_enabled=True, rotation_enabled=True,
                                  spacing_enabled=True, baseline_enabled=True))


class PresetTests(unittest.TestCase):
    def setUp(self):
        self.temp = test_temp()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.store = Presets(self.root)

    def test_restart_and_isolated_categories(self):
        p = example()
        self.store.save(dict(kind='layout', revision=0, presets=[p]))
        restored = Presets(self.root)
        self.assertEqual(restored.all()['layout']['presets'], [p])
        self.assertEqual(restored.all()['grid']['revision'], 0)
        self.store.save(dict(kind='layout', revision=1, presets=[]))
        self.assertEqual(Presets(self.root).all()['layout']['presets'], [])

    def test_concurrent_writes_cannot_overwrite(self):
        def save(index):
            try:
                self.store.save(dict(kind='layout', revision=0, presets=[example(str(index))]))
                return True
            except ValueError:
                return False
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sum(pool.map(save, range(2))), 1)

    def test_migration_collisions_and_retry_after_delete(self):
        original = example()
        existing = example(); existing['values']['size'] = 6
        self.store.save(dict(kind='layout', revision=0, presets=[existing]))
        data = dict(groups=dict(layout=dict(presets=[original], selected=original['id'])))
        migrated = self.store.migrate(data)
        entries = migrated['groups']['layout']['presets']
        self.assertEqual(migrated['imported'], 1)
        self.assertEqual(entries[0], existing)
        self.assertNotEqual(entries[0]['id'], entries[1]['id'])
        self.assertNotEqual(entries[0]['name'], entries[1]['name'])
        self.assertEqual(migrated['selected']['layout'], entries[1]['id'])
        self.assertEqual(self.store.migrate(data)['imported'], 0)
        self.store.save(dict(kind='layout', revision=2, presets=[existing]))
        self.assertEqual(Presets(self.root).migrate(data)['imported'], 0)
        self.assertEqual(len(self.store.all()['layout']['presets']), 1)

    def test_invalid_import_is_transactional(self):
        bad = dict(id='f', name='坏字体', mix=[dict(font_id='x', weight=0)])
        with self.assertRaises(ValueError):
            self.store.migrate(dict(groups=dict(layout=dict(presets=[example()]), font=dict(presets=[bad]))))
        self.assertEqual(self.store.all()['layout']['presets'], [])
        for p in [example(id='a4-portrait'), {**example(), 'values': {'width': float('nan')}},
                  {**example(), 'name': 'x'*41}]:
            with self.assertRaises(ValueError):
                self.store.save(dict(kind='layout', revision=0, presets=[p]))

    def test_disk_failure_never_acknowledges_or_changes_state(self):
        self.store.save(dict(kind='layout', revision=0, presets=[example()]))
        before = self.store.path.read_bytes()
        with patch('backend.presets.os.replace', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.store.save(dict(kind='layout', revision=1, presets=[]))
        self.assertEqual(self.store.path.read_bytes(), before)
        self.assertEqual(self.store.all()['layout']['revision'], 1)

    def test_http_auth_routes_and_restart_without_machine_access(self):
        app = Application(FONT_DIR, self.root, token='test', controller=NoMachine())
        server = create_server(app, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        base = f'http://127.0.0.1:{server.server_port}'
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(base+'/api/presets')
        self.assertEqual(error.exception.code, 401)
        def request(path, data=None):
            req = urllib.request.Request(base+path, data=None if data is None else json.dumps(data).encode(),
                headers={'Authorization': 'Bearer test', 'Content-Type': 'application/json'})
            return json.load(urllib.request.urlopen(req))
        result = request('/api/presets/migrate', dict(groups=dict(layout=dict(presets=[example()]))))
        self.assertEqual(result['imported'], 1)
        self.assertEqual(request('/api/presets')['groups']['layout']['presets'], [example()])
        request('/api/presets', dict(kind='font', revision=0, presets=[dict(id='f', name='缺字库也保留', mix=[dict(font_id='unavailable',weight=10,scope='zh')])]))
        self.assertEqual(len(Application(FONT_DIR, self.root, controller=NoMachine()).presets.all()['font']['presets']), 1)
        with urllib.request.urlopen(base+'/preset-store.js') as response:
            self.assertIn(b'window.PresetStore', response.read())


if __name__ == '__main__':
    unittest.main()
