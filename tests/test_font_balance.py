"""Actual-ink calibration, manual controls, scoped mixes and final plotted paths."""
import contextlib
import pathlib
import struct
import unittest
import zipfile

from backend.document import Glyphs, configuration, generate_document
from backend.font_balance import SAMPLES
from scripts.generate_demo_font import glyph_record
from tests.test_service import test_temp


class FontBalanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = test_temp()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        # Typical Chinese ink is half its envelope; digits exceed capitals by 25%.
        self.font = self.make_font('mixed', chinese=True)
        self.data = dict(layout_mode='notebook', line_placement='ink', width=100, height=100,
                         margin=10, size=5, rows=5, seed='balance', text='你A1a')

    def make_font(self, name, chinese=False, latin=True, envelope=200):
        path = self.root / (name + '.gfont')
        chars = (SAMPLES['zh'] if chinese else '') + ((SAMPLES['letters'] + SAMPLES['digits'] + 'aB') if latin else '')
        with path.open('wb') as stream:
            stream.write(struct.pack('>I', 5))
            with zipfile.ZipFile(stream, 'w') as archive:
                for char in dict.fromkeys(chars):
                    height = envelope if char == '国' else 125 if char.isdigit() else 50 if char == 'a' else 100
                    archive.writestr(str(ord(char)), glyph_record(char, [[(0, 0), (40, height), (0, height)]]))
        return path

    def glyphs(self, **settings):
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        choices = settings.pop('choices', [dict(font_id='mixed', path=self.font, weight=1)])
        return Glyphs(choices, stack, configuration(dict(self.data, **settings)), 'balance')

    def height(self, box):
        ys = [y for stroke in box.paths for x, y in stroke]
        return max(ys) - min(ys)

    def test_calibrates_capitals_and_digits_separately_without_changing_lowercase_ratio(self):
        glyphs = self.glyphs(smart_balance=True)
        heights = {char: self.height(glyphs.box(char, 5)) for char in '你A1a'}
        self.assertAlmostEqual(heights['A'] / heights['你'], .9)
        self.assertAlmostEqual(heights['1'] / heights['你'], .9)
        self.assertAlmostEqual(heights['a'] / heights['A'], .5)
        self.assertAlmostEqual(glyphs.balance.records['mixed']['letters']['scale'], .45)
        self.assertAlmostEqual(glyphs.balance.records['mixed']['digits']['scale'], .36)

    def test_manual_controls_are_independent_and_preserve_aspect(self):
        auto = self.glyphs(smart_balance=True)
        manual = self.glyphs(smart_balance=True, letter_scale=120, digit_scale=80)
        for char, ratio in [('A', 1.2), ('a', 1.2), ('1', .8), ('你', 1)]:
            a, b = auto.box(char, 5), manual.box(char, 5)
            self.assertAlmostEqual(b.width / a.width, ratio)
            self.assertAlmostEqual(self.height(b) / self.height(a), ratio)

    def test_disabled_option_is_byte_identical_to_original_even_with_manual_values(self):
        old = generate_document(self.font, self.data)[0]
        disabled = generate_document(self.font, dict(self.data, smart_balance=False, letter_scale=50, digit_scale=150))[0]
        self.assertEqual(old['gcode'], disabled['gcode'])
        self.assertFalse(disabled['metadata']['font_balance']['enabled'])

    def test_english_only_font_uses_selected_chinese_scope_as_reference(self):
        latin = self.make_font('latin')
        chinese = self.make_font('chinese', chinese=True, latin=False)
        choices = [dict(font_id='zh', path=chinese, scope='zh', weight=1),
                   dict(font_id='en', path=latin, scope='en', weight=1000)]
        glyphs = self.glyphs(smart_balance=True, choices=choices)
        self.assertAlmostEqual(self.height(glyphs.box('A', 5)) / self.height(glyphs.box('你', 5)), .9)
        self.assertEqual(glyphs.balance.reference, 'selected_chinese')

    def test_no_chinese_sample_has_explicit_nominal_reference(self):
        latin = self.make_font('latin')
        glyphs = self.glyphs(smart_balance=True, choices=[dict(font_id='en', path=latin, weight=1)])
        self.assertEqual(glyphs.balance.reference, 'nominal')
        self.assertAlmostEqual(self.height(glyphs.box('A', 5)), 4.5)

    def test_shared_reference_honors_chinese_weights(self):
        full = self.make_font('full', chinese=True, envelope=100)
        choices = [dict(font_id='half', path=self.font, weight=1), dict(font_id='full', path=full, weight=3)]
        glyphs = self.glyphs(smart_balance=True, choices=choices)
        self.assertAlmostEqual(glyphs.balance.target, .9 * (.5 + 3) / 4)

    def test_external_fallback_uses_replacement_calibration_and_keeps_highlight(self):
        from tests.test_glyph_fallback import GlyphFallbackTests
        fixture = GlyphFallbackTests()
        fixture.setUp()
        try:
            plain = fixture.render('notebook', text='B')[0]
            balanced = fixture.render('notebook', text='B', smart_balance=True)[0]
            info = balanced['metadata']['font_balance']['fonts'][0]
            self.assertEqual(info['font_id'], 'closest')
            self.assertEqual(balanced['metadata']['glyph_fallbacks'][0]['font_id'], 'closest')
            self.assertIn('data-fallback="true"', balanced['svg'])
            width = lambda p: p['metadata']['bounds'][2] - p['metadata']['bounds'][0]
            self.assertAlmostEqual(width(balanced) / width(plain), info['letters']['scale'], places=3)
        finally:
            fixture.tearDown()

    def test_grid_fit_does_not_cancel_reduction_and_keeps_cells_safe(self):
        data = dict(self.data, layout_mode='grid', text='A', rows=5, grid=dict(columns=5))
        old = generate_document(self.font, data)[0]
        small = generate_document(self.font, dict(data, smart_balance=True))[0]
        def height(page):
            b = page['metadata']['bounds']
            return b[3] - b[1]
        # Grid CJK uses the Latin reference, so its measured target is .9.
        self.assertAlmostEqual(height(small) / height(old), .9, places=3)
        large = generate_document(self.font, dict(data, smart_balance=True, letter_scale=150))[0]
        self.assertLessEqual(height(large), large['metadata']['grid']['cell_height'])

    def test_formulas_use_balanced_glyphs_and_keep_safe_spacing(self):
        data = dict(self.data, smart_balance=True, text='你A1\n$A+\\frac{1}{2}+a^2$\n你A1',
                    line_sizing='size', line_looseness=1)
        result = generate_document(self.font, data)[0]
        self.assertEqual(result['gcode'], generate_document(self.font, data)[0]['gcode'])
        metadata = result['metadata']
        self.assertEqual(metadata['font_balance']['fonts'][0]['digits']['samples'], 10)
        for a, b in zip(metadata['line_layout'], metadata['line_layout'][1:]):
            self.assertGreaterEqual(b['top_mm'] - a['bottom_mm'], b['safety_gap_mm'] - .001)

    def test_invalid_settings_fail_instead_of_silently_changing_scale(self):
        for key, value in [('smart_balance', 1), ('letter_scale', 49), ('digit_scale', 151), ('digit_scale', True)]:
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                configuration(dict(self.data, **{key: value}))


if __name__ == '__main__':
    unittest.main()
