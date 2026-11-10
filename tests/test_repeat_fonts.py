"""Page-local diversity, geometric separation, reflow and output provenance."""
import collections
import itertools
import pathlib
import struct
import unittest
import zipfile

from backend.document import generate_document
from backend.repeat_fonts import Neighbors, color_points, separation
from scripts.generate_demo_font import glyph_record
from tests.test_service import test_temp


class RepeatFontTests(unittest.TestCase):
    def setUp(self):
        self.temp = test_temp()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.paths = []
        for i in range(4):
            path = self.root / f'font{i}.gfont'
            with path.open('wb') as stream:
                stream.write(struct.pack('>I', 5))
                with zipfile.ZipFile(stream, 'w') as archive:
                    for char in '人国你好ABab123':
                        archive.writestr(str(ord(char)), glyph_record(char, [[(0, 0), (4 + i, 6), (0, 6)]]))
            self.paths.append(path)

    def generate(self, text, count=3, weights=None, **extra):
        choices = [dict(font_id=str(i), path=self.paths[i], weight=(weights or [1]*count)[i], scope='all') for i in range(count)]
        data = dict(layout_mode='notebook', line_placement='ink', width=100, height=100,
                    margin=10, size=5, rows=5, spacing=.5, seed='repeats', text=text)
        data.update(extra)
        return generate_document(self.paths[0], data, choices)

    def check_diversity(self, pages):
        for page in pages:
            for group in page['metadata']['repeat_distribution']['groups']:
                self.assertEqual(group['used_fonts'], min(group['occurrences'], group['available_fonts']), group)

    def test_repeated_character_uses_unique_fonts_despite_extreme_weights(self):
        page = self.generate('人人人', weights=[1000000, 1, 1])[0]
        items = page['metadata']['glyph_occurrences']
        self.assertEqual(len({item['font_id'] for item in items}), 3)
        self.assertEqual(len(items), 3)
        self.assertEqual(page['metadata']['repeat_distribution']['groups'][0]['nearest_same_font_mm'], None)

    def test_three_positions_reuse_only_the_farthest_pair(self):
        page = self.generate('人 人 人', count=2)[0]
        items = page['metadata']['glyph_occurrences']
        self.assertEqual(items[0]['font_id'], items[2]['font_id'])
        self.assertNotEqual(items[0]['font_id'], items[1]['font_id'])

    def test_two_dimensional_rectangle_uses_diagonals_not_reading_order_cycle(self):
        points = [(0,0),(10,0),(0,10),(10,10)]
        colors = color_points(points, 2, 'rectangle')
        self.assertEqual(colors[0], colors[3]); self.assertEqual(colors[1], colors[2])
        self.assertNotEqual(colors[0], colors[1])
        self.assertEqual(separation(points, colors)[0], 200)

    def test_small_group_matches_exhaustive_maximin(self):
        points = [(0,0),(5,1),(11,0),(1,9),(7,8),(15,11)]
        for count in (2,3,4):
            optimal = max(separation(points, colors) for colors in itertools.product(range(count), repeat=len(points))
                          if len(set(colors)) == count)
            self.assertEqual(separation(points, color_points(points, count, 'exact')), optimal)

    def test_actual_output_pages_reset_diversity(self):
        pages = self.generate('人'*9, count=3, layout_mode='grid', rows=1, grid=dict(columns=3))
        self.assertEqual(len(pages), 3)
        self.assertEqual([len(p['metadata']['glyph_occurrences']) for p in pages], [3]*3)
        self.check_diversity(pages)
        for page in pages:
            self.assertEqual(len({item['font_id'] for item in page['metadata']['glyph_occurrences']}), 3)

    def test_reflow_formulas_humanization_and_smart_size_are_repeatable(self):
        data = dict(width=55,height=55,margin=5,rows=6,line_sizing='size',line_looseness=1,
                    smart_balance=True,humanization=dict(enabled=True,vertical=.1,scale=3,rotation=1,spacing=.1,baseline=.1))
        text = ('人人AB\n'+r'$A+\frac{A}{1}+A^2$'+'\n人AB人\n')*5
        pages = self.generate(text, **data)
        self.assertGreater(len(pages),1); self.check_diversity(pages)
        again = self.generate(text, **data)
        self.assertEqual([p['gcode'] for p in pages], [p['gcode'] for p in again])
        self.assertEqual([p['metadata']['glyph_occurrences'] for p in pages], [p['metadata']['glyph_occurrences'] for p in again])
        for page in pages:
            rows = page['metadata']['line_layout']
            for a,b in zip(rows, rows[1:]):
                self.assertGreaterEqual(b['top_mm']-a['bottom_mm'],b['safety_gap_mm']-.001)
            selected = collections.Counter(item['font_id'] for item in page['metadata']['glyph_occurrences'])
            summary = {item['font_id']:item['used'] for item in page['metadata']['font_mix']}
            self.assertTrue(all(summary[key] == uses for key,uses in selected.items()))

    def test_formulas_and_plain_text_share_the_same_page_character_pool(self):
        page = self.generate('A $A+\\frac{A}{1}$')[0]
        items = [item for item in page['metadata']['glyph_occurrences'] if item['character']=='A']
        self.assertEqual(len(items),3); self.assertEqual(len({item['font_id'] for item in items}),3)

    def test_explicit_source_and_page_breaks_remain_intact(self):
        pages = self.generate('', pages=[dict(text='人人'),dict(text=''),dict(text='人\\newpage 人人')])
        self.assertEqual(len(pages),4); self.assertTrue(pages[1]['metadata']['empty'])
        self.assertEqual([p['metadata']['source_page'] for p in pages],[1,2,3,3]); self.check_diversity(pages)

    def test_zero_weight_and_script_scope_exclude_fonts(self):
        choices = [dict(font_id=str(i),path=self.paths[i],weight=weight,scope=scope)
                   for i,weight,scope in [(0,1,'zh'),(1,1,'en'),(2,0,'all')]]
        page = generate_document(self.paths[0],dict(text='人A人A',layout_mode='notebook',width=100,height=100,margin=10,rows=4),choices)[0]
        for item in page['metadata']['glyph_occurrences']:
            self.assertEqual(item['font_id'],'0' if item['character']=='人' else '1')

    def test_missing_glyphs_use_only_drawable_selected_fonts_then_nearest_fallback(self):
        from tests.test_glyph_fallback import GlyphFallbackTests
        fixture = GlyphFallbackTests()
        fixture.setUp()
        try:
            page = fixture.render('notebook', text='你A你A你A')[0]
            self.check_diversity([page])
            selected = [item for item in page['metadata']['glyph_occurrences'] if item['character']=='A']
            replacements = [item for item in page['metadata']['glyph_occurrences'] if item['character']=='你']
            self.assertEqual({item['font_id'] for item in selected},{'a','b'})
            self.assertTrue(all(item['font_id']=='next' and item['options']==['next'] for item in replacements))
            self.assertEqual(page['metadata']['external_fallback_characters'],3)
            self.assertEqual(page['svg'].count('data-fallback="true"'),3)
        finally:
            fixture.tearDown()

    def test_many_page_sizes_keep_diversity_after_geometry_changes(self):
        import random
        for mode in ('notebook','grid'):
            for seed in range(20):
                rng = random.Random(seed)
                count, n = rng.randint(2,4), rng.randint(2,35)
                data = dict(seed=str(seed),layout_mode=mode,width=rng.randint(35,80),height=rng.randint(35,80),
                            margin=5,rows=rng.randint(2,5))
                if mode == 'grid':
                    data['grid'] = dict(columns=rng.randint(2,8))
                else:
                    data.update(line_sizing='size',line_looseness=1)
                text = ''.join('人'+('\n' if rng.random()<.2 else ' ') for i in range(n))
                with self.subTest(mode=mode,seed=seed):
                    self.check_diversity(self.generate(text,count=count,**data))

    def test_large_group_is_spatial_and_uses_all_fonts(self):
        points = [(float(i%20),float(i//20)) for i in range(400)]
        colors = color_points(points,4,'large')
        self.assertEqual(len(set(colors)),4)
        self.assertGreater(separation(points,colors)[0],separation(points,[i%4 for i in range(400)])[0])
        tree = Neighbors(points)
        self.assertEqual(tree.nearest(0,1)[0][0],1)


if __name__ == '__main__':
    unittest.main()
