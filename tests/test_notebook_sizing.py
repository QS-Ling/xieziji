"""Linked notebook sizing and guides aligned to rendered ink."""
import unittest
import xml.etree.ElementTree as ET

from backend.document import configuration, coordinate_preview, generate_document
from tests.test_service import FONT


class NotebookSizingTests(unittest.TestCase):
    def data(self, **extra):
        return dict(layout_mode='notebook', width=100, height=100, margin=10,
                    rows=4, size=5, text='A;', seed='line-sizing', **extra)

    def test_fixed_rows_derive_height_and_looseness_changes_only_height(self):
        tight = configuration(self.data(line_sizing='rows',line_looseness=1.5))
        loose = configuration(self.data(line_sizing='rows',line_looseness=2.5))
        self.assertEqual((tight['rows'],loose['rows']),(4,4))
        self.assertEqual((tight['pitch'],loose['pitch']),(20,20))
        self.assertAlmostEqual(tight['size'],20/1.5)
        self.assertLess(loose['size'],tight['size'])
        # The derived input is ignored; the server is authoritative.
        request=self.data(line_sizing='rows',line_looseness=2);request['size']=999
        self.assertEqual(configuration(request)['size'],10)

    def test_fixed_height_derives_rows_and_keeps_pitch_when_rounding_down(self):
        request=self.data(line_sizing='size',line_looseness=2);request['rows']=999
        tight=configuration(request)
        loose=configuration({**request,'line_looseness':3})
        self.assertEqual((tight['size'],loose['size']),(5,5))
        self.assertEqual((tight['rows'],loose['rows']),(8,5))
        self.assertEqual(loose['pitch'],15)
        self.assertLessEqual(loose['rows']*loose['pitch'],80)

    def test_guides_touch_actual_ink_in_both_modes_with_and_without_variation(self):
        for mode in ('rows','size'):
            for varied in (False,True):
                human=dict(enabled=varied,vertical=.2,scale=3,rotation=1,spacing=.1,baseline=.2)
                data=self.data(line_sizing=mode,line_looseness=2,humanization=human)
                result=generate_document(FONT,data)[0]
                guides=result['metadata']['row_guides']
                self.assertEqual(guides[0],result['metadata']['bounds'][3])
                root=ET.fromstring(result['svg']);ns={'s':'http://www.w3.org/2000/svg'}
                group=root.find('s:g[@id="row-guides"]',ns)
                self.assertNotIn('stroke-dasharray',group.attrib)
                self.assertEqual(float(group[0].get('y1')),guides[0])
                self.assertEqual(float(group[0].get('y2')),guides[0])
                self.assertNotIn('row-guides',result['gcode'])
                preview=coordinate_preview(data)
                self.assertEqual(preview['metadata']['rows'],result['metadata']['rows'])
                self.assertEqual(preview['metadata']['size'],result['metadata']['size'])

    def test_formula_guide_is_below_the_whole_formula(self):
        data=self.data(line_sizing='size',line_looseness=1.5)
        data['text']=r'$\frac{1}{\frac{2}{3}}$'
        result=generate_document(FONT,data)[0]
        self.assertEqual(result['metadata']['row_guides'][0],result['metadata']['bounds'][3])
        self.assertLess(len(result['metadata']['row_guides']),result['metadata']['rows'])

    def test_legacy_settings_and_grid_remain_independent(self):
        old=configuration(self.data())
        self.assertEqual((old['rows'],old['size'],old['pitch']),(4,5,20))
        grid=configuration({**self.data(),'layout_mode':'grid','line_sizing':'rows','line_looseness':4})
        self.assertEqual((grid['rows'],grid['size']),(4,5))

    def test_invalid_and_impossible_combinations_are_rejected(self):
        for extra in (dict(line_sizing='other'),dict(line_sizing='rows',line_looseness=.9),
                      dict(line_sizing='size',line_looseness=4.1),dict(line_sizing='size',line_looseness=float('nan')),
                      dict(line_sizing='rows',line_looseness=4,rows=200),dict(line_sizing='size',line_looseness=4,size=20,height=50)):
            with self.assertRaises(ValueError): configuration({**self.data(),**extra})
