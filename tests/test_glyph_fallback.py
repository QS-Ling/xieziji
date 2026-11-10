"""Nearest available font, accurate per-glyph highlights and immutable output paths."""
import hashlib
import json
import pathlib
import struct
import unittest
import xml.etree.ElementTree as ET
import zipfile

from backend.font_library import FontLibrary
from backend.document import generate_document
from backend.layout import generate
from backend.mixing import font_choices
from backend.server import Application
from scripts.generate_demo_font import glyph_record
from tests.test_service import test_temp


class GlyphFallbackTests(unittest.TestCase):
    def setUp(self):
        self.temp=test_temp();self.root=pathlib.Path(self.temp.name)
        self.fonts={}
        for key,chars,width in [('a','A',3),('b','A',4),('closest','AB',5),('next','A你',6),('far','A你B',7)]:
            path=self.root/(key+'.gfont')
            with path.open('wb') as stream:
                stream.write(struct.pack('>I',5))
                with zipfile.ZipFile(stream,'w') as archive:
                    for char in chars:archive.writestr(str(ord(char)),glyph_record(char,[[(0,0),(width,6),(0,6)]]))
            self.fonts[key]=path
        self.report=self.root/'similarity.json'
        records=[dict(id=key,file=path.name,bytes=path.stat().st_size,glyph_count=2,
                      fallback_rankings=[['closest',.1,93.],['next',.2,86.],['far',.3,80.]]) for key,path in self.fonts.items()]
        self.report.write_text(json.dumps(dict(version=2,fonts=records)),encoding='utf8')
        self.library=FontLibrary(self.fonts,self.report)
        self.data=dict(text='A你B你',font_mix=[dict(font_id='a',weight=70),dict(font_id='b',weight=30)],seed='fallback',
                       width=100,height=100,margin=10,size=5,rows=4)

    def tearDown(self):self.temp.cleanup()

    def render(self,mode=None,**extra):
        data=dict(self.data,**extra)
        choices,primary=font_choices(data,self.fonts)
        return generate_document(primary,dict(data,layout_mode=mode),choices,self.library) if mode else [generate(primary,data,choices,self.library)]

    def test_nearest_font_with_character_wins_and_repeated_char_is_recorded(self):
        for mode in (None,'notebook','grid'):
            with self.subTest(mode=mode):
                result=self.render(mode)[0];metadata=result['metadata']
                fallbacks=metadata['glyph_fallbacks']
                self.assertEqual([f['character'] for f in fallbacks],['你','B','你'])
                self.assertEqual([f['font_id'] for f in fallbacks],['next','closest','next'])
                self.assertEqual(metadata['external_fallback_characters'],3)
                self.assertEqual(len({f['occurrence'] for f in fallbacks}),3)
                self.assertEqual(sum(f['used'] for f in metadata['font_mix']),4)
                self.assertEqual(result['gcode'],self.render(mode)[0]['gcode'])
                svg=ET.fromstring(result['svg']);highlight=[n for n in svg.iter() if n.get('data-fallback')=='true']
                self.assertEqual(len(highlight),3)
                self.assertEqual([n.get('data-character') for n in highlight],['你','B','你'])
                self.assertTrue(all(n.get('stroke')=='#c25b13' for n in highlight))
                self.assertEqual(hashlib.sha256(result['gcode'].encode()).hexdigest(),metadata['sha256'])

    def test_selected_fonts_first_and_disabled_font_never_used(self):
        data=dict(font_mix=[dict(font_id='a',weight=1),dict(font_id='next',weight=1)])
        result=self.render('notebook',text='你',**data)[0]
        self.assertEqual(result['metadata']['external_fallback_characters'],0)
        result=self.render('notebook',text='你',font_mix=[dict(font_id='a',weight=1),dict(font_id='next',weight=0)])[0]
        self.assertEqual(result['metadata']['glyph_fallbacks'][0]['font_id'],'far')

    def test_stale_candidate_and_unavailable_char_rejected(self):
        with self.fonts['next'].open('ab') as stream:stream.write(b'changed')
        result=self.render('notebook',text='你')[0]
        self.assertEqual(result['metadata']['glyph_fallbacks'][0]['font_id'],'far')
        with self.assertRaisesRegex(ValueError,'缺少.*😀'):self.render('notebook',text='😀')

    def test_page_and_formula_highlights_keep_actual_glyph_boundaries(self):
        pages=self.render('grid',pages=[dict(text='你\nA\n你')],rows=1,grid=dict(columns=1))
        self.assertEqual([p['metadata']['external_fallback_characters'] for p in pages],[1,0,1])
        page=self.render('notebook',text=r'$A+\frac{你}{B}$')[0]
        highlighted=[n for n in ET.fromstring(page['svg']).iter() if n.get('data-fallback')]
        self.assertEqual([n.get('data-character') for n in highlighted],['你','B'])
        self.assertEqual(page['metadata']['external_fallback_characters'],2)

    def test_application_cache_and_archive_preserve_highlight_and_paths(self):
        class NoMachine:
            def __getattr__(self,name):raise AssertionError('Preview contacted machine: '+name)
        app=Application(self.root,self.root/'jobs',controller=NoMachine())
        ids={path.stem:key for key,path in app.fonts.items()}
        data=json.loads(self.report.read_text(encoding="utf8"))
        for item in data['fonts']:
            item['id']=ids[item['id']]
            item['fallback_rankings']=[[ids[key],distance,score] for key,distance,score in item['fallback_rankings']]
        self.report.write_text(json.dumps(data),encoding="utf8")
        app.font_library=FontLibrary(app.fonts,self.report)
        preview=app.preview(dict(self.data,layout_mode='notebook',font_mix=[dict(font_id=ids['a'],weight=1)]))
        archive=zipfile.ZipFile(__import__('io').BytesIO(app.archive(preview['document_id'])))
        self.assertEqual(archive.read('page-001.svg').decode(),preview['svg'])
        folder,result=app.job(preview['job_id'])
        self.assertEqual(archive.read('page-001.gcode'),(folder/'job.gcode').read_bytes())
        self.assertEqual(preview['metadata']['external_fallback_characters'],3)

    def test_placeholder_glyph_is_treated_as_missing(self):
        with self.fonts['a'].open('wb') as stream:
            stream.write(struct.pack('>I',5))
            with zipfile.ZipFile(stream,'w') as archive:
                archive.writestr(str(ord('你')),glyph_record('你',[]))
                archive.writestr(str(ord('A')),glyph_record('A',[[(0,0),(3,6),(0,6)]]))
        data=json.loads(self.report.read_text(encoding="utf8"))
        next(f for f in data['fonts'] if f['id']=='a')['bytes']=self.fonts['a'].stat().st_size
        self.report.write_text(json.dumps(data),encoding="utf8")
        self.assertEqual(self.render('notebook',text='你')[0]['metadata']['glyph_fallbacks'][0]['font_id'],'next')

    def test_similarity_references_respect_chinese_english_font_scopes(self):
        data=json.loads(self.report.read_text(encoding="utf8"))
        next(f for f in data['fonts'] if f['id']=='b')['fallback_rankings']=[['far',.01,99.],['next',.2,86.]]
        self.report.write_text(json.dumps(data),encoding="utf8")
        mix=[dict(font_id='a',weight=1,scope='en'),dict(font_id='b',weight=1,scope='zh')]
        result=self.render('notebook',text='你',font_mix=mix)[0]
        self.assertEqual(result['metadata']['glyph_fallbacks'][0]['font_id'],'far')
        self.assertEqual(result['metadata']['glyph_fallbacks'][0]['reference_font_id'],'b')
        with self.assertRaisesRegex(ValueError,'中文'):
            self.render('notebook',text='你',font_mix=[dict(font_id='a',weight=1,scope='en')])


if __name__=='__main__':unittest.main()
