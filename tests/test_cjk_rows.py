"""Chinese glyphs must not inherit the size of smaller Latin capitals."""
import pathlib
import struct
import unittest
import zipfile

from backend.document import generate_document
from backend.gfont import GFont
from scripts.generate_demo_font import glyph_record
from tests.test_service import test_temp


class ChineseRowTests(unittest.TestCase):
    def font(self, folder):
        path=pathlib.Path(folder)/'mixed-proportions.gfont'
        with path.open('wb') as stream:
            stream.write(struct.pack('>I',5))
            with zipfile.ZipFile(stream,'w') as archive:
                for char in 'AEFHIKLMNTUVWXZ':
                    archive.writestr(str(ord(char)),glyph_record(char,[[(0,0),(4,6)]]))
                for char in dict.fromkeys('国田日目中永你好字体写字机'):
                    archive.writestr(str(ord(char)),glyph_record(char,[[(0,-4),(8,8)]]))
                archive.writestr(str(ord('大')),glyph_record('大',[[(0,-12),(20,28)]]))
        return path

    def data(self, **extra):
        return dict(layout_mode='notebook',width=100,height=100,margin=10,rows=20,
                    size=4,line_sizing='rows',line_looseness=1,text='\n'.join(['你好A；']*20),seed='cjk-row-test',**extra)

    def test_chinese_reference_is_independent_and_latin_api_stays_compatible(self):
        with test_temp() as folder, GFont(self.font(folder)) as font:
            self.assertEqual(font.metrics['reference_height'],6)
            self.assertEqual(font.cjk_metrics['reference_height'],12)
            old=font.text('你',5)
            corrected=font.text('你',5,reference_metrics=font.cjk_metrics)
            height=lambda paths:max(y for stroke in paths for _,y in stroke)-min(y for stroke in paths for _,y in stroke)
            self.assertAlmostEqual(height(old),10)
            self.assertAlmostEqual(height(corrected),5)
            self.assertEqual(font.text('A',5),font.text('A',5,reference_metrics=None))

    def test_twenty_chinese_lines_fill_one_page_in_both_linked_modes(self):
        with test_temp() as folder:
            font=self.font(folder)
            for mode in ('rows','size'):
                for ratio in (1,1.5,2):
                    data=self.data();data.update(line_sizing=mode,line_looseness=ratio,size=4/ratio)
                    pages=generate_document(font,data)
                    self.assertEqual(len(pages),1,(mode,ratio))
                    self.assertEqual(len(pages[0]['metadata']['lines']),20)
                    self.assertEqual(pages[0]['metadata']['rows'],20)
                    self.assertEqual(len(pages[0]['metadata']['row_guides']),20)
                    self.assertLessEqual(pages[0]['metadata']['bounds'][3],90.001)

    def test_tall_outliers_and_variation_fit_one_row_without_distortion(self):
        with test_temp() as folder:
            font=self.font(folder)
            data=self.data();data.update(text='\n'.join(['大你好A；']*20),
                humanization=dict(enabled=True,vertical=.3,scale=5,rotation=2,spacing=.2,baseline=.4))
            page=generate_document(font,data)[0]
            self.assertEqual(len(page['metadata']['lines']),20)
            self.assertEqual(len(page['metadata']['row_guides']),20)
            self.assertLessEqual(page['metadata']['bounds'][3],90.001)
            for row,lower in enumerate(page['metadata']['row_guides']):
                self.assertLessEqual(lower,10+(row+1)*4+.001)
            for stroke in page['paths']:
                # No stroke crosses from its assigned row into the next row.
                top=min(y for _,y in stroke);bottom=max(y for _,y in stroke)
                start=min(19,int((top-10+.001)//4))
                self.assertLessEqual(bottom,10+(start+1)*4+.001)

    def test_tall_formula_still_reserves_additional_rows(self):
        with test_temp() as folder:
            data=self.data();data['text']=r'$\frac{1}{\frac{2}{3}}$'
            page=generate_document(self.font(folder),data)[0]
            self.assertEqual(page['metadata']['formula_count'],1)
            self.assertLess(len(page['metadata']['row_guides']),20)

    def test_current_installed_font_does_not_double_chinese_rows(self):
        font=pathlib.Path(__file__).resolve().parents[2]/'gcodeFonts'/'blood8-2_kvenjoy_blood8.gfont'
        if not font.is_file():self.skipTest('Installed proprietary font is not distributed with the project')
        for ratio in (1,1.5,2.37):
            data=dict(layout_mode='notebook',width=210,height=297,margin=30,rows=20,
                      line_sizing='rows',line_looseness=ratio,text='\n'.join(['固定行数，自动计算字高。']*20),seed='real-cjk')
            pages=generate_document(font,data)
            self.assertEqual(len(pages),1,ratio)
            self.assertEqual(len(pages[0]['metadata']['lines']),20)
            self.assertEqual(len(pages[0]['metadata']['row_guides']),20)
