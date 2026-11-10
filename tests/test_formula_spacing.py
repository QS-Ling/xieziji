"""Compact prose with local formula protection, measured against actual plotted ink."""
import types
import unittest
from backend.document import Box, Token, compact_notebook_pages, generate_document
from tests.test_service import FONT


class FormulaSpacingTests(unittest.TestCase):
    def synthetic(self,rows,available=60):
        config=dict(pitch=4,available=available,margins=dict(left=0,top=0),size=4,latin_size=4,usable=100)
        return compact_notebook_pages(rows,config,types.SimpleNamespace(variation=None))

    def token(self,label,height,formula=False):
        return Token(label,Box(3,height,height,[[(0,0),(3,height)]]),3,formula=formula)

    def test_plain_text_keeps_tight_pitch_and_only_formula_neighbors_expand(self):
        plain=self.token('字',8);formula=self.token('$x$',7,True)
        page=self.synthetic([[plain],[plain],[formula],[plain],[plain]])[0]
        rows=page[4]
        self.assertEqual(rows[1]['offset_mm']-rows[0]['offset_mm'],4)
        self.assertGreater(rows[1]['bottom_mm'],rows[2]['offset_mm']-4)
        self.assertGreater(rows[2]['extra_gap_mm'],0)
        self.assertGreaterEqual(rows[2]['top_mm']-max(r['bottom_mm'] for r in rows[:2]),.3199)
        self.assertGreaterEqual(rows[3]['top_mm']-rows[2]['bottom_mm'],.3199)
        self.assertAlmostEqual(rows[4]['offset_mm']-rows[3]['offset_mm'],4)
        self.assertNotEqual(rows[2]['extra_gap_mm']%4,0)

    def test_exact_ink_avoids_needless_expansion_for_large_empty_box(self):
        plain=self.token('字',4)
        sparse=Token('$x$',Box(3,20,4,[[(0,0),(3,3)]]),3,formula=True)
        page=self.synthetic([[plain],[sparse],[plain]])[0]
        self.assertAlmostEqual(page[4][1]['offset_mm'],4.32)
        self.assertAlmostEqual(page[4][2]['offset_mm'],8.32)

    def test_formula_and_following_text_never_collide_across_page_boundary(self):
        plain=self.token('字',8);formula=self.token('$x$',10,True)
        pages=self.synthetic([[plain],[plain],[plain],[formula],[plain]],available=20)
        self.assertEqual(len(pages),2)
        self.assertEqual(pages[1][1],['$x$','字'])
        for page in pages:
            self.assertTrue(all(r['top_mm']>=0 and r['bottom_mm']<=20.001 for r in page[4]))
        self.assertGreaterEqual(pages[1][4][1]['top_mm']-pages[1][4][0]['bottom_mm'],.3199)

    def test_explicit_blank_line_retains_one_pitch_after_formula(self):
        pages=self.synthetic([[self.token('$x$',10,True)],[],[self.token('字',4)]])
        layout=pages[0][4]
        self.assertGreaterEqual(layout[2]['top_mm']-layout[0]['bottom_mm'],4.3199)

    def test_actual_nested_formulas_and_humanization_are_safe_and_repeatable(self):
        data=dict(layout_mode='notebook',text=r'A\n$\frac{1}{\frac{2}{3}}$\nA\n$x^2$\nA'.replace('\\n','\n'),
                  width=100,height=100,margin=10,size=5,latin_size=8,rows=20,line_sizing='size',line_looseness=1,
                  allow_overlap=True,seed='local-formula-spacing',humanization=dict(enabled=True,vertical=.2,scale=5,rotation=2,spacing=.2,baseline=.3))
        pages=generate_document(FONT,data)
        self.assertEqual([p['gcode'] for p in pages],[p['gcode'] for p in generate_document(FONT,data)])
        for page in pages:
            layout=page['metadata']['line_layout']
            for i,row in enumerate(layout):
                for j,previous in enumerate(layout[:i]):
                    if row['formula'] or previous['formula']:
                        self.assertGreaterEqual(row['top_mm']-previous['bottom_mm'],row['safety_gap_mm']-.001)
            self.assertLessEqual(page['metadata']['bounds'][3],90.001)

    def test_fixed_pagination_reports_overflow_instead_of_overlapping(self):
        data=dict(layout_mode='notebook',text=('A\n'+r'$\frac{1}{\frac{2}{3}}$'+'\nA\n')*3,
                  width=100,height=40,margin=5,size=5,rows=6,line_sizing='size',line_looseness=1,
                  allow_overlap=True,pagination='fixed')
        with self.assertRaisesRegex(ValueError,'溢出|高度超过'):generate_document(FONT,data)

    def test_ink_mode_protects_plain_text_and_ignores_nominal_empty_boxes(self):
        config=dict(pitch=4,available=60,margins=dict(left=0,top=0),size=4,latin_size=4,usable=100)
        sparse=Token('字',Box(3,20,20,[[(0,10),(3,13)]]),3)
        pages=compact_notebook_pages([[sparse],[sparse],[self.token('高',9)],[sparse]],config,types.SimpleNamespace(variation=None),protect_text=True)
        rows=pages[0][4]
        self.assertEqual(rows[0]['top_mm'],0)
        self.assertEqual(rows[0]['bottom_mm'],3)
        self.assertEqual(rows[1]['offset_mm']-rows[0]['offset_mm'],4)
        for a,b in zip(rows,rows[1:]):self.assertGreaterEqual(b['top_mm']-a['bottom_mm'],.1599)

    def test_new_ink_policy_preserves_size_and_is_safe_without_overlap_switch(self):
        from backend.document import predict_line_pitch
        data=dict(layout_mode='notebook',line_placement='ink',line_sizing='size',line_looseness=1,size=5,latin_size=6,
                  text='A\ng\n'+r'$\frac{1}{2}$'+'\nA\ng',width=100,height=100,margin=10,seed='smart')
        for old in (False,True):
            pages=generate_document(FONT,dict(data,allow_overlap=old))
            for page in pages:
                self.assertFalse(page['metadata']['allow_overlap'])
                self.assertEqual(page['metadata']['size'],5)
                layout=page['metadata']['line_layout']
                for a,b in zip(layout,layout[1:]):self.assertGreaterEqual(b['top_mm']-a['bottom_mm'],b['safety_gap_mm']-.001)
        prediction=predict_line_pitch(data,[dict(font_id='font',path=FONT,weight=1)])
        self.assertEqual(prediction['min_ratio'],1)
        self.assertEqual(prediction['line_placement'],'ink')

    def test_ink_policy_survives_fallback_scaling_and_pagination(self):
        data=dict(layout_mode='notebook',line_placement='ink',line_sizing='rows',line_looseness=1,size=5,
                  rows=10,width=100,height=100,margin=10,text=('A\n'+r'$\frac{1}{\frac{2}{3}}$'+'\ng\n')*8)
        pages=generate_document(FONT,data)
        self.assertGreater(len(pages),1)
        self.assertEqual(''.join(line for p in pages for line in p['metadata']['lines']),data['text'].replace('\n',''))
        for page in pages:
            layout=page['metadata']['line_layout']
            self.assertLessEqual(page['metadata']['bounds'][3],90.001)
            for a,b in zip(layout,layout[1:]):self.assertGreaterEqual(b['top_mm']-a['bottom_mm'],b['safety_gap_mm']-.001)


if __name__=='__main__':unittest.main()
