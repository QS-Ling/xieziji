"""Shared device drafts and rendered output survive browser/backend restarts."""
import concurrent.futures
import copy
import unittest
from unittest.mock import patch
from backend.server import Application
from tests.test_service import FONT_DIR, test_temp
from tests.test_preview_store import NoMachine


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = test_temp()
        self.addCleanup(self.temp.cleanup)
        self.app = Application(FONT_DIR, self.temp.name, controller=NoMachine())
        self.draft = dict(layoutMode='grid', pages=['AB'], fields={}, font_mix=[], modeDrafts={})

    def test_restart_and_device_isolation(self):
        saved = self.app.api('/api/workspaces/COM5', dict(revision=0, draft=self.draft))['workspace']
        restored = Application(FONT_DIR, self.temp.name, controller=NoMachine())
        self.assertEqual(restored.api('/api/workspaces/COM5'), saved)
        self.assertIsNone(restored.api('/api/workspaces/COM6')['draft'])
        reset = copy.deepcopy(self.draft)
        reset['pages'] = ['']
        self.app.api('/api/workspaces/COM6', dict(revision=0, draft=reset))
        self.assertEqual(restored.api('/api/workspaces/COM5'), saved)

    def test_concurrent_stale_writers_do_not_overwrite(self):
        def update(i):
            draft = dict(self.draft, pages=[str(i)])
            return self.app.api('/api/workspaces/COM5', dict(revision=0, draft=draft))
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(update, range(8)))
        self.assertEqual(sum(not r['conflict'] for r in results), 1)
        self.assertEqual(self.app.api('/api/workspaces/COM5')['revision'], 1)

    def test_generation_committed_once_and_reads_never_regenerate(self):
        render = dict(font_id=next(iter(self.app.fonts)), layout_mode='grid', rows=2,
                      grid=dict(columns=5), width=100, height=100, margin=10, pages=[dict(text='AB')])
        request = dict(revision=0, draft=self.draft, render=render)
        workspace = self.app.api('/api/workspaces/COM5', request)['workspace']
        page = self.app.previews.group(workspace['document_id'])['job_ids'][0]
        before = {k: self.app.job(page)[1][k] for k in ('metadata', 'svg', 'gcode')}
        restored = Application(FONT_DIR, self.temp.name, controller=NoMachine())
        with patch('backend.server.generate_document', side_effect=AssertionError('regenerated')):
            self.assertTrue(restored.api('/api/workspaces/COM5', request)['conflict'])
            self.assertEqual(restored.api('/api/workspaces/COM5'), workspace)
            self.assertEqual(restored.job(page)[1], before)
        reset = restored.api('/api/workspaces/COM5', dict(revision=1, draft=dict(self.draft, pages=['']), clear_preview=True))
        self.assertIsNone(reset['workspace']['document_id'])
        self.assertEqual(restored.job(page)[1], before)

    def test_failed_generation_keeps_last_committed_state(self):
        before = self.app.api('/api/workspaces/COM5')
        with self.assertRaises(ValueError):
            self.app.api('/api/workspaces/COM5', dict(revision=0, draft=self.draft, render=dict(pages=[])))
        self.assertEqual(self.app.api('/api/workspaces/COM5'), before)

    def test_device_path_cannot_escape_store(self):
        path = self.app.workspaces.path('../../outside')
        self.assertEqual(path.parent, self.app.workspaces.root)
        self.assertEqual(self.app.api('/api/workspaces/%2Fdev%2FttyUSB0')['device'], '/dev/ttyUSB0')


if __name__ == '__main__':
    unittest.main()
