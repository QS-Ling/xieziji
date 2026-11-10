"""Saved previews survive eviction and restart without layout or machine actions."""
import concurrent.futures
import hashlib
import io
import json
import pathlib
import unittest
from unittest.mock import patch
import zipfile

from backend.server import Application
from tests.test_service import FONT_DIR, test_temp


class NoMachine:
    def __getattr__(self, name):
        raise AssertionError('Reading a saved preview contacted the machine: ' + name)


class PreviewStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = test_temp()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.app = Application(FONT_DIR, self.root, controller=NoMachine())
        self.data = dict(font_id=next(iter(self.app.fonts)), layout_mode='grid', rows=2, grid=dict(columns=5),
                         width=100,height=100,margin=10,seed='saved-preview',pages=[dict(text='AB'),dict(text='BA')])

    def restarted(self):
        return Application(FONT_DIR,self.root,controller=NoMachine())

    def test_restart_keeps_all_page_bytes_and_archive_order_without_generating_again(self):
        preview = self.app.preview(self.data)
        original = self.app.archive(preview['document_id'])
        restored = self.restarted()
        self.assertFalse(restored.cache)
        with patch('backend.server.generate_document',side_effect=AssertionError('Regenerated layout')):
            for page in preview['pages']:
                folder,result = restored.job(page['job_id'])
                self.assertEqual(result['metadata'],page['metadata'])
                self.assertEqual(result['svg'],page['svg'])
                self.assertEqual(result['gcode'].encode(),(folder/'job.gcode').read_bytes())
                self.assertEqual(hashlib.sha256(result['gcode'].encode()).hexdigest(),page['metadata']['sha256'])
            before = zipfile.ZipFile(io.BytesIO(original))
            after = zipfile.ZipFile(io.BytesIO(restored.archive(preview['document_id'])))
            self.assertEqual(before.namelist(),after.namelist())
            for name in before.namelist():
                self.assertEqual(before.read(name),after.read(name))

    def test_repeated_eviction_only_limits_ram(self):
        previews = [self.app.preview(self.data) for i in range(12)]
        for item in previews:
            for page in item['pages']:
                self.app.job(page['job_id'])
            self.app.archive(item['document_id'])
            self.assertLessEqual(len(self.app.groups),8)
            self.assertLessEqual(len(self.app.documents),8)
        for item in previews:
            self.assertTrue((self.root/'.documents'/(item['document_id']+'.json')).is_file())

    def test_old_pre_index_pages_are_recoverable(self):
        preview = self.app.preview(self.data)
        page = preview['pages'][1]
        path = self.root/page['job_id']/'metadata.json'
        old = json.loads(path.read_text(encoding='utf8'))
        old.pop('preview_group_id')
        path.write_text(json.dumps(old),encoding='utf8')
        (self.root/'.documents'/(preview['document_id']+'.json')).unlink()
        folder,result = self.restarted().job(page['job_id'])
        self.assertEqual(result['metadata'],old)
        self.assertEqual(result['gcode'].encode(),(folder/'job.gcode').read_bytes())
        self.assertEqual(result['svg'],page['svg'])

    def test_missing_or_corrupt_saved_page_fails_clearly(self):
        preview = self.app.preview(self.data)
        folder = self.root/preview['job_id']
        with (folder/'job.gcode').open('ab') as stream:
            stream.write(b'G1 X999 Y999 F10000\n')
        with self.assertRaisesRegex(ValueError,'损坏'):
            self.restarted().job(preview['job_id'])
        with self.assertRaisesRegex(ValueError,'找不到已保存'):
            self.restarted().job('a'*32)

    def test_invalid_ids_and_manifest_entries_are_rejected(self):
        for bad in ('../metadata','',None,'A'*32):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):self.app.job(bad)
                with self.assertRaises(ValueError):self.app.archive(bad)
        preview = self.app.preview(self.data)
        path = self.root/'.documents'/(preview['document_id']+'.json')
        manifest = json.loads(path.read_text(encoding='utf8'))
        manifest['job_ids'][0] = '../outside'
        path.write_text(json.dumps(manifest),encoding='utf8')
        with self.assertRaisesRegex(ValueError,'索引损坏'):
            self.restarted().archive(preview['document_id'])

    def test_concurrent_page_and_archive_reads_preserve_the_same_output(self):
        preview = self.app.preview(self.data)
        restored = self.restarted()
        def read(index):
            if index%2:
                return restored.job(preview['pages'][1]['job_id'])[1]['metadata']['sha256']
            archive = zipfile.ZipFile(io.BytesIO(restored.archive(preview['document_id'])))
            return hashlib.sha256(archive.read('page-002.gcode')).hexdigest()
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(read,range(18)))
        self.assertEqual(set(results),{preview['pages'][1]['metadata']['sha256']})


if __name__=='__main__':
    unittest.main()
