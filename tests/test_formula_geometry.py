"""Regression tests for the hand-drawn formula geometry controls."""
import math
import unittest

from backend.document import configuration
from backend.glyph_fallback import Stroke
from backend.mathtext import Box, render, symbol
from backend.math_symbols import fence


def glyph(char, size):
    # Lowercase ink spans 1..size, so its centre sits at 0.6 em like handwriting.
    top = 1. if char.islower() else 0.
    return Box(size*.6, size-top, size-top,
               [Stroke([(0, 0), (size*.6, size-top)], {'character':char,'font_id':'fallback'},
                       {'character':char,'occurrence':char})])


def ink_center(box):
    ys = [y for stroke in box.paths for _, y in stroke]
    return (min(ys) + max(ys)) / 2


class FormulaGeometryTests(unittest.TestCase):
    def test_symbols_shrink_and_sit_on_the_measured_axis(self):
        plus = symbol('+', 5, scale=.8, axis=.6)
        ys = [y for stroke in plus.paths for _, y in stroke]
        self.assertAlmostEqual(max(ys) - min(ys), 3.2)
        self.assertAlmostEqual(ink_center(plus), 3.0)
        mixed = render('a+b', 5, glyph, symbol_scale=.8, math_axis=.6,
                       font_glyph=lambda c, s: glyph(c, s) if c.isalpha() else None)
        plus_paths = [s for s in mixed.paths if not getattr(s, 'glyph', None)]
        plus_y = [y for s in plus_paths for _, y in s]
        letter_y = [y for s in mixed.paths if getattr(s, 'glyph', None)
                    and s.glyph['character'] == 'a' for _, y in s]
        self.assertAlmostEqual((min(plus_y)+max(plus_y))/2, (min(letter_y)+max(letter_y))/2)

    def test_round_fences_are_narrow_and_smooth(self):
        width, paths = fence('(', 5, 5)
        self.assertLess(width, 2.)
        self.assertGreater(len(paths[0]), 16)
        # No single straight segment may dominate the arc.
        self.assertGreater(min(math.dist(a, b) for a, b in zip(paths[0], paths[0][1:])), .1)
        _, coarse = fence('(', 5, 5, smooth=False)
        self.assertEqual(len(coarse[0]), 6)

    def test_fraction_rule_has_deterministic_tapered_wobble(self):
        first = render(r'\frac{a}{b}', 5, glyph, jitter=.12, seed='formula-seed')
        second = render(r'\frac{a}{b}', 5, glyph, jitter=.12, seed='formula-seed')
        other = render(r'\frac{a}{b}', 5, glyph, jitter=.12, seed='other-seed')
        rule = lambda box: [s for s in box.paths if not getattr(s, 'glyph', None)][0]
        first_rule, second_rule, other_rule = rule(first), rule(second), rule(other)
        self.assertGreater(len(first_rule), 2)
        ys = [y for _, y in first_rule]
        self.assertLessEqual(max(ys) - min(ys), .241)
        self.assertAlmostEqual(first_rule[0][1], first_rule[-1][1])
        self.assertEqual(list(first_rule), list(second_rule))
        self.assertNotEqual(list(first_rule), list(other_rule))

    def test_radical_and_integral_are_curved(self):
        radical = render(r'\sqrt{x}', 5, glyph, font_glyph=lambda c, s: glyph(c, s) if c == 'x' else None)
        curves = [s for s in radical.paths if not getattr(s, 'glyph', None)]
        self.assertGreater(sum(len(s) for s in curves), 12)
        integral = symbol('∫', 5)
        self.assertGreaterEqual(len(integral.paths[0]), 15)

    def test_formula_prefers_font_then_falls_back_or_blanks(self):
        font_greek = lambda c, s: glyph(c, s) if c == 'α' else None
        preferred = render('α', 5, glyph, font_glyph=font_greek)
        self.assertTrue(all(getattr(s, 'glyph', None) for s in preferred.paths))
        self.assertEqual(preferred.paths[0].glyph['character'], 'α')

        drawn = render('α', 5, glyph, font_glyph=lambda c, s: None, draw_missing=True)
        self.assertTrue(drawn.paths)
        self.assertTrue(all(not getattr(s, 'glyph', None) for s in drawn.paths))

        blank = render('α', 5, glyph, font_glyph=lambda c, s: None, draw_missing=False)
        self.assertFalse(blank.paths)
        self.assertGreater(blank.width, 0.)

    def test_font_first_applies_to_operators_but_delimiters_need_symbol_font(self):
        font_all = lambda c, s: glyph(c, s)
        box = render('(a)+b', 5, glyph, font_glyph=font_all)
        plus = [s for s in box.paths if getattr(s, 'glyph', None) and s.glyph['character'] == '+']
        self.assertTrue(plus)
        self.assertFalse(any(getattr(s, 'glyph', None) and s.glyph['character'] in '()' for s in box.paths))
        symbol_box = render('(a)+b', 5, glyph, font_glyph=font_all, symbol_glyph=font_all)
        self.assertTrue(all(getattr(s, 'glyph', None) for s in symbol_box.paths if s))

    def test_delimiter_height_is_controlled_by_formula_layout(self):
        font_all = lambda c, s: glyph(c, s)
        box = render('(a+b)', 5, glyph, font_glyph=font_all)
        brackets = [s for s in box.paths if not getattr(s, 'glyph', None)]
        self.assertEqual(len(brackets), 2)
        for bracket in brackets:
            ys = [y for _, y in bracket]
            self.assertLessEqual(max(ys) - min(ys), 5.7)
            self.assertLessEqual(max(ys), box.height + .001)

    def test_symbol_font_delimiters_are_height_clamped(self):
        def tall_fence(char, size):
            return Box(2., 7., 7., [[(1.8, 0.), (0.2, 7.)]])
        box = render('(a)', 5, glyph, font_glyph=lambda c, s: glyph(c, s),
                     symbol_glyph=tall_fence)
        fences = [s for s in box.paths if getattr(s, 'glyph', None) is None]
        self.assertTrue(fences)
        for fence in fences:
            ys = [y for _, y in fence]
            self.assertLessEqual(max(ys) - min(ys), 5.61)

    def test_fallback_symbols_vary_with_seed_but_stay_bounded(self):
        first = symbol('α', 5, seed='hand-one')
        second = symbol('α', 5, seed='hand-two')
        self.assertNotEqual([tuple(s) for s in first.paths[0]], [tuple(s) for s in second.paths[0]])
        for box in (first, second):
            for stroke in box.paths:
                for x, y in stroke:
                    self.assertGreaterEqual(x, -.001)
                    self.assertLessEqual(x, box.width + .001)
                    self.assertGreaterEqual(y, -.001)
                    self.assertLessEqual(y, box.height + .001)

    def test_latex_greek_commands_use_unicode_reference(self):
        font_mu = lambda c, s: glyph(c, s) if c == 'μ' else None
        command = render(r'\mu', 5, glyph, font_glyph=font_mu)
        direct = render('μ', 5, glyph, font_glyph=font_mu)
        self.assertTrue(command.paths)
        self.assertEqual([getattr(s, 'glyph', {}).get('character') for s in command.paths],
                         [getattr(s, 'glyph', {}).get('character') for s in direct.paths])
        blank = render(r'\mu', 5, glyph, font_glyph=lambda c, s: None, draw_missing=False)
        self.assertFalse(blank.paths)
        drawn = render(r'\mu', 5, glyph, font_glyph=lambda c, s: None, draw_missing=True)
        self.assertTrue(drawn.paths)

    def test_symbol_scope_is_reserved_for_math_characters(self):
        from backend.mixing import font_choices, is_symbol_character, scoped
        self.assertTrue(is_symbol_character('α'))
        self.assertTrue(is_symbol_character('+'))
        self.assertTrue(is_symbol_character('('))
        self.assertFalse(is_symbol_character('A'))
        self.assertTrue(scoped('symbol', 'symbol'))
        self.assertFalse(scoped('symbol', 'en'))
        self.assertTrue(scoped('all', 'symbol'))
        choices, primary = font_choices(
            dict(font_mix=[dict(font_id='f', weight=100, scope='symbol')]),
            {'f': 'font.gfont'})
        self.assertEqual(choices[0]['scope'], 'symbol')

    def test_symbol_only_pool_contains_only_symbol_fonts(self):
        import contextlib
        from backend.document import Glyphs
        from tests.test_service import FONT
        choices = [dict(font_id='normal', path=FONT, weight=100, scope='all'),
                   dict(font_id='symbol', path=FONT, weight=100, scope='symbol')]
        config = configuration(dict(layout_mode='notebook', width=100, height=100, margin=5,
                                    rows=10, size=5, spacing=.5))
        with contextlib.ExitStack() as stack:
            glyphs = Glyphs(choices, stack, config, 'symbol-scope')
            self.assertEqual(glyphs.pool('α', symbol_only=True), [1])
            self.assertEqual(set(glyphs.pool('α')), {0})

    def test_formula_settings_are_parsed_and_bounded(self):
        config = configuration(dict(layout_mode='notebook', width=210, height=297, margin=30,
                                    rows=20, size=5, latin_size=5, spacing=.9))
        self.assertEqual(config['formula'], dict(symbol_scale=.8, smooth=True, jitter=.12, draw_missing=True))
        with self.assertRaises(ValueError):
            configuration(dict(layout_mode='notebook', width=210, height=297, margin=30,
                               rows=20, size=5, formula=dict(symbol_scale=200)))
        with self.assertRaises(ValueError):
            configuration(dict(layout_mode='notebook', width=210, height=297, margin=30,
                               rows=20, size=5, formula=dict(jitter=-.1)))


if __name__ == '__main__':
    unittest.main()
