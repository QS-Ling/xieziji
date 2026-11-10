"""Font discovery updates without restarting or touching machine control."""
import json
import pathlib
import shutil
import threading
import time
import unittest
from unittest.mock import patch

from backend.font_updates import FontUpdates
from backend.server import Application
from tests.test_service import FONT, test_temp


class FontUpdateTests(unittest.TestCase):
    def wait(self, updates):
        updates.worker.join(30)
        self.assertFalse(updates.worker.is_alive(), 'font check did not finish')
        return updates.status()

    def setup_app(self, temp):
        root=pathlib.Path(temp)
        fonts=root/'fonts';fonts.mkdir()
        shutil.copyfile(FONT, fonts/'first.gfont')
        class NoMachine:
            def __getattr__(self, name):
                raise AssertionError('Font discovery contacted controller: '+name)
        return Application(fonts, root/'jobs', controller=NoMachine())

    def test_real_analysis_discovery_restart_and_unchanged_skip(self):
        with test_temp() as temp:
            app=self.setup_app(temp)
            app.api('/api/font-refresh', {})
            self.assertIsNone(self.wait(app.font_updates)['error'])
            self.assertEqual(len(app.api('/api/fonts')['fonts']), 1)
            self.assertEqual(app.api('/api/font-recommendations')['summary']['analyzed_fonts'], 1)
            original=app.font_updates.status()['analyzed_at']
            with patch.object(app.font_updates, '_command', side_effect=AssertionError('Unchanged fonts reanalyzed')):
                app.font_updates.request();self.assertIsNone(self.wait(app.font_updates)['error'])
            self.assertEqual(app.font_updates.status()['analyzed_at'], original)
            # Persisted fingerprints / report generation survive a service restart.
            restarted=Application(app.fonts_dir, app.jobs_dir, controller=app.machine)
            with patch.object(restarted.font_updates, '_command', side_effect=AssertionError('Restart reanalyzed')):
                restarted.font_updates.request();self.assertIsNone(self.wait(restarted.font_updates)['error'])
            self.assertEqual(restarted.font_updates.status()['analyzed_at'], original)
            shutil.copyfile(FONT, app.fonts_dir/'added.gfont')
            app.font_updates.request();self.assertIsNone(self.wait(app.font_updates)['error'])
            self.assertEqual(len(app.api('/api/fonts')['fonts']), 2)
            self.assertEqual(app.api('/api/font-recommendations')['summary']['analyzed_fonts'], 2)
            (app.fonts_dir/'first.gfont').unlink()
            app.font_updates.request();self.assertIsNone(self.wait(app.font_updates)['error'])
            self.assertEqual([f['name'] for f in app.api('/api/fonts')['fonts']], ['added'])

    def test_same_size_replacement_invalid_font_failure_retry_and_empty_directory(self):
        with test_temp() as temp:
            app=self.setup_app(temp)
            app.font_updates.request();self.assertIsNone(self.wait(app.font_updates)['error'])
            initial=(app.font_updates.storage/'current.json').read_bytes()
            path=app.fonts_dir/'first.gfont'
            # ZIP accepts trailing data; replace a byte there so size stays identical.
            path.write_bytes(path.read_bytes()+b'A')
            app.font_updates.request();self.assertIsNone(self.wait(app.font_updates)['error'])
            initial=(app.font_updates.storage/'current.json').read_bytes()
            path.write_bytes(path.read_bytes()[:-1]+b'B')
            with patch.object(app.font_updates, '_command', side_effect=RuntimeError('test analysis failure')):
                app.font_updates.request();status=self.wait(app.font_updates)
            self.assertIn('test analysis failure', status['error'])
            self.assertEqual((app.font_updates.storage/'current.json').read_bytes(), initial)
            self.assertEqual(app.api('/api/font-recommendations')['summary']['analyzed_fonts'], 0)
            app.font_updates.request();self.assertIsNone(self.wait(app.font_updates)['error'])
            self.assertEqual(app.api('/api/font-recommendations')['summary']['analyzed_fonts'], 1)
            (app.fonts_dir/'broken.gfont').write_bytes(b'bad font')
            app.font_updates.request();status=self.wait(app.font_updates)
            self.assertIsNone(status['error']);self.assertEqual(len(status['invalid_fonts']), 1)
            self.assertEqual(len(app.api('/api/fonts')['fonts']), 1)
            path.unlink();(app.fonts_dir/'broken.gfont').unlink()
            app.font_updates.request();self.assertIsNone(self.wait(app.font_updates)['error'])
            self.assertEqual(app.api('/api/fonts')['fonts'], [])
            self.assertEqual(app.api('/api/font-recommendations')['recommendations'], [])

    def test_daily_scheduler_and_concurrent_refresh_share_worker(self):
        with test_temp() as temp:
            app=self.setup_app(temp)
            gate=threading.Event();entered=threading.Event()
            def delayed_scan():
                entered.set();gate.wait(5);return []
            with patch.object(app.font_updates, '_scan', side_effect=delayed_scan):
                app.font_updates.request();self.assertTrue(entered.wait(2))
                worker=app.font_updates.worker
                app.font_updates.request();self.assertIs(app.font_updates.worker, worker)
                gate.set();self.wait(app.font_updates)
            called=threading.Event()
            with patch('backend.font_updates.INTERVAL', .03), patch.object(app.font_updates, 'request', side_effect=called.set) as request:
                app.font_updates.start()
                called.clear();self.assertTrue(called.wait(2))
                app.font_updates.stop();app.font_updates.scheduler.join(2)
                self.assertGreaterEqual(request.call_count, 2)


if __name__=='__main__':unittest.main()
