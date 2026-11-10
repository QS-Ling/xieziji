"""Parser/geometry regressions for real pen paths, not rendered TeX images."""
import math
import unittest

from backend.mathtext import Box, COMMANDS, items, render
from backend.glyph_fallback import Stroke
from backend.document import generate_document
from tests.test_service import FONT


def glyph(char,size):
    # Deliberately retain provenance to detect transformations that lose fallback marks.
    return Box(size*.6,size,size,[Stroke([(0,0),(size*.6,size)],
        {'character':char,'font_id':'fallback'}, {'character':char,'occurrence':char})])


class LatexTests(unittest.TestCase):
    def box(self,source,display=False):
        box=render(source,5,glyph,display=display)
        self.assertTrue(box.paths,source)
        for stroke in box.paths:
            self.assertGreaterEqual(len(stroke),2)
            for x,y in stroke:
                self.assertTrue(math.isfinite(x) and math.isfinite(y),source)
                self.assertGreaterEqual(x,-1e-8,source)
                self.assertGreaterEqual(y,-1e-8,source)
                self.assertLessEqual(x,box.width+1e-8,source)
                self.assertLessEqual(y,box.height+1e-8,source)
        self.assertGreaterEqual(box.baseline,0)
        self.assertLessEqual(box.baseline,box.height+1e-8)
        return box

    def test_all_symbol_commands_produce_finite_bounded_paths(self):
        for command in COMMANDS:
            with self.subTest(command=command): self.box('\\'+command)

    def test_nested_stretchy_fences_and_invisible_side(self):
        source=r'\left\{\left[\frac{a}{\frac{b}{c}}\right]\right.'
        box=self.box(source)
        fixed=self.box(r'\{[a]')
        self.assertGreater(box.height,fixed.height*2)
        fences=[s for s in box.paths if not getattr(s,'glyph',None)]
        outer=max(fences,key=lambda s:max(y for x,y in s))
        self.assertAlmostEqual(max(y for x,y in outer),box.height)
        for delim in (r'\langle',r'\lfloor',r'\lceil',r'\lVert','(',r'\{'):
            self.box(r'\left'+delim+r'\frac{x}{y}\right.')

    def test_root_index_and_accents_preserve_original_glyph_identity(self):
        for source in (r'\sqrt[3]{\frac{x}{y}}',r'\vec{x}',r'\hat{x}',r'\widetilde{x}',
                       r'\dot{x}',r'\ddot{x}',r'\overline{x}',r'\underline{x}',
                       r'\overbrace{x+y}^{n}',r'\underbrace{x+y}_{n}',r'\overset{a}{x}',r'\underset{a}{x}'):
            with self.subTest(source=source):
                box=self.box(source)
                marked=[s for s in box.paths if getattr(s,'glyph',{}).get('character')=='x']
                self.assertEqual(len(marked),1)
                self.assertEqual(marked[0].fallback['font_id'],'fallback')

    def test_fraction_styles_and_operator_limits(self):
        inline=self.box(r'\frac{a}{b}')
        display=self.box(r'\frac{a}{b}',True)
        self.assertGreater(display.height,inline.height)
        self.assertAlmostEqual(self.box(r'\dfrac{a}{b}').height,display.height)
        self.assertAlmostEqual(self.box(r'\tfrac{a}{b}',True).height,inline.height)
        self.assertAlmostEqual(self.box(r'\displaystyle\frac{a}{b}').height,display.height)
        a=self.box(r'\sum_{i=1}^{n}')
        b=self.box(r'\sum_{i=1}^{n}',True)
        c=self.box(r'\sum\nolimits_{i=1}^{n}',True)
        self.assertGreater(b.height,c.height)
        self.assertGreater(b.height,a.height)
        self.box(r'\int\limits_0^1 x dx',True)
        self.box(r'\binom{n}{k}')

    def test_super_and_subscript_do_not_collide(self):
        box=self.box(r'x^{ab}_{cd}')
        ys={s.glyph['character']:[y for x,y in s] for s in box.paths if getattr(s,'glyph',None)}
        self.assertGreater(min(ys['c'])-max(ys['b']),.5)

    def test_annotations_substack_and_operatorname(self):
        for source in (r'\sum_{\substack{i=1\\j>0}}^n x',r'\boxed{\frac{x}{y}}',
                       r'\operatorname*{argmax}_{x} f(x)',r'\not\equiv',
                       r'a\phantom{x}b',r'a\hphantom{x}b',r'a\vphantom{\frac{x}{y}}b'):
            self.box(source,True)
        self.assertGreater(self.box(r'a\phantom{x}b').width,self.box('ab').width)

    def test_matrix_families_and_multiline_environments(self):
        for name in ('matrix','pmatrix','bmatrix','Bmatrix','vmatrix','Vmatrix','smallmatrix','aligned','split'):
            with self.subTest(name=name):
                self.box(r'\begin{'+name+r'}a&\frac{b}{c}\\[2pt]d&e\end{'+name+'}',True)
        for source in (r'\begin{cases}x^2&x\ge0\\-x&x<0\end{cases}',
                       r'\begin{gathered}a=b\\c=d\end{gathered}',
                       r'\begin{array}{rl}a&b\\c&d\end{array}',
                       r'\begin{pmatrix}\begin{matrix}a&b\\c&d\end{matrix}&e\\f&g\end{pmatrix}',
                       r'\begin{equation}x^2=1\end{equation}'):
            self.box(source,True)

    def test_alignment_and_row_spacing_follow_actual_cell_bounds(self):
        source=r'\begin{aligned}a&b\\ccc&d\end{aligned}'
        box=self.box(source)
        points={}
        for s in box.paths:
            if getattr(s,'glyph',None): points.setdefault(s.glyph['character'],[]).extend(s)
        self.assertAlmostEqual(max(x for x,y in points['a']),max(x for x,y in points['c']))
        self.assertAlmostEqual(min(x for x,y in points['b']),min(x for x,y in points['d']))
        extra=self.box(source.replace(r'\\',r'\\[1em]'))
        self.assertAlmostEqual(extra.height-box.height,5.)
        # A final \\ adds no phantom empty row.
        self.assertAlmostEqual(self.box(source.replace(r'\end',r'\\\end')).height,box.height)

    def test_spacing_commands_and_escaped_delimiters(self):
        plain=self.box('ab').width
        self.assertLess(self.box(r'a\!b').width,plain)
        self.assertGreater(self.box(r'a\quad b').width,plain)
        self.assertEqual(list(items(r'A $\text{\$5}+x$ B')),[('text','A '),('formula',r'\text{\$5}+x'),('text',' B')])
        self.assertEqual(list(items('$$x % ignore $ and $$\n+y$$')),[('display','x % ignore $ and $$\n+y')])
        self.box('x % ignore \\unknown\n + y')

    def test_invalid_input_remains_actionable_and_bounded(self):
        invalid=[r'\sqrt[]{x}',r'\sqrt[3{x}',r'\left(x',r'\right)',r'\left(x\right',r'\unknown{x}',
                 r'\begin{evil}x\end{evil}',r'\begin{matrix}a&b',r'\begin{matrix}x\end{cases}',
                 r'\begin{array}{p{2cm}}x\end{array}',r'\begin{cases}a&b&c\end{cases}',
                 r'\begin{matrix}a\\[99em]b\end{matrix}',r'\begin{matrix}a\\[-1em]b\end{matrix}',
                 r'\begin{gathered}a&b\end{gathered}',r'a&b',r'a\\b',r'x^^2',
                 r'\begin{matrix}'+ '&'.join('x' for _ in range(13))+r'\end{matrix}',
                 r'\begin{matrix}'+r'\\'.join('x' for _ in range(25))+r'\end{matrix}',
                 '{'*20+'x'+'}'*20,'x'*1001]
        for source in invalid:
            with self.subTest(source=source),self.assertRaises(ValueError): render(source,5,glyph)

    def test_documents_repeat_exactly_and_formulas_remain_inside_page(self):
        text=('A\n$$'+r'\begin{cases}\sqrt[3]{x}&x\ge0\\\frac{x}{2}&x<0\end{cases}'+'$$\nB\n$$'+
              r'\begin{pmatrix}a&b\\c&d\end{pmatrix}'+'$$\nA\n$$'+r'\sum_{i=1}^{n}i=\frac{n(n+1)}{2}'+'$$')
        data=dict(layout_mode='notebook',text=text,width=100,height=110,margin=10,size=4,latin_size=4,
                  rows=20,line_placement='ink',line_sizing='size',seed='extended-latex')
        first=generate_document(FONT,data)
        self.assertEqual([p['gcode'] for p in first],[p['gcode'] for p in generate_document(FONT,data)])
        self.assertEqual(sum(p['metadata']['formula_count'] for p in first),3)
        for p in first:
            x0,y0,x1,y1=p['metadata']['bounds']
            self.assertGreaterEqual(min(x0,y0),9.999)
            self.assertLessEqual(x1,90.001);self.assertLessEqual(y1,100.001)
            layout=p['metadata']['line_layout']
            for a,b in zip(layout,layout[1:]):
                self.assertGreaterEqual(b['top_mm']-a['bottom_mm'],b['safety_gap_mm']-.001)


if __name__=='__main__': unittest.main()
