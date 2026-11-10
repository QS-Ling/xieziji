"""Mixed-script wrapping must not turn a list label into an empty row."""
import unittest

from backend.document import Token, notebook_rows, text_width, generate_document, prepare_notebook_tokens
from backend.layout import generate
from backend.mathtext import Box
from tests.test_service import FONT


def rows(text, width=12):
    tokens = ['\n' if c == '\n' else Token(c, Box(.5 if c == ' ' else 1, 1, 1, []),
                                        .5 if c == ' ' else 1) for c in text]
    result = notebook_rows(tokens, {'usable':width})
    assert all(text_width(row) <= width for row in result)
    return [''.join(t.source for t in row) for row in result]


class WrappingTests(unittest.TestCase):
    def test_fit_happens_before_wrapping_so_rows_fill_the_available_width(self):
        tokens=[Token('汉',Box(1,2,2,[[(0,0),(1,2)]]),1) for _ in range(40)]
        config=dict(usable=10,line_sizing='rows',pitch=1,size=1)
        wrapped=notebook_rows(tokens,config)
        self.assertEqual([len(line) for line in wrapped],[20,20])
        self.assertEqual([text_width(line) for line in wrapped],[10,10])
        self.assertTrue(all(t.box.height==1 for line in wrapped for t in line))

    def test_scale_is_consistent_across_manual_lines_and_formulas_are_not_shrunk(self):
        normal=Token('汉',Box(1,2,2,[[(0,0),(1,2)]]),1)
        tall=Token('大',Box(2,4,4,[[(0,0),(2,4)]]),2)
        formula=Token('$x^2$',Box(2,6,4,[[(0,0),(2,6)]]),2,formula=True)
        prepared=prepare_notebook_tokens([normal,formula,tall,'\n',normal],dict(line_sizing='size',pitch=1,size=1))
        self.assertEqual(prepared[0].box.width,.25)
        self.assertEqual(prepared[2].box.width,.5)
        self.assertIs(prepared[1],formula)
        self.assertEqual(prepared[-1].box.width,.25)

    def test_latin_words_beside_chinese_and_numbers_with_units_stay_intact(self):
        self.assertEqual(rows('测量OTDR曲线',5),['测量','OTDR曲','线'])
        self.assertEqual(rows('测量time-domain曲线',12),['测量','time-domain曲','线'])
        self.assertEqual(rows('记录10 mm长度',6),['记录','10 mm长','度'])
        self.assertEqual(rows('记录10纳米长度',5),['记录','10纳米长','度'])
        self.assertEqual(rows('测量（OTDR）曲线',7),['测量','（OTDR）曲','线'])

    def test_installed_font_uses_the_final_sizes_for_optical_reflectometer_text(self):
        import contextlib
        import pathlib
        from backend.document import Glyphs, configuration, tokenize
        font=pathlib.Path(__file__).resolve().parents[2]/'gcodeFonts'/'blood8-2_kvenjoy_blood8.gfont'
        if not font.is_file():self.skipTest('Installed proprietary font is not distributed')
        config=configuration(dict(layout_mode='notebook',width=210,height=297,margin=30,
                                  rows=40,line_sizing='rows',line_looseness=1.3))
        text=('光时域反射仪（英文名称：optical time-domain reflectometer，OTDR）是通过对测量曲线的分析，'
              '了解光纤的均匀性、缺陷、断裂、接头耦合等若干性能的仪器。它根据光的后向散射与菲涅耳反向反射制作，'
              '利用在光纤中传输时产生的后向散射光来获取衰减的信息。')
        with contextlib.ExitStack() as stack:
            glyphs=Glyphs([dict(font_id='fixture',path=font,weight=1)],stack,config,'wrap')
            wrapped=notebook_rows(tokenize(text,glyphs,config),config)
            self.assertEqual(''.join(t.source for line in wrapped for t in line),text)
            for line in wrapped[:-1]:
                self.assertGreater(text_width(line)/config['usable'],.9)
                self.assertLessEqual(text_width(line),config['usable']+.0001)

    def test_chinese_list_items_fill_the_first_row(self):
        for prefix in ('3. ', '4. ', '2. ', '12. ', '（3） ', '三、 '):
            source = prefix + '控制温控箱温度升高从室温开始每上升五度记录一次'
            wrapped = rows(source)
            self.assertTrue(wrapped[0].startswith(prefix + '控制'), wrapped)
            self.assertGreater(len(wrapped[0]), 10)
            self.assertEqual(''.join(wrapped), source)

    def test_chinese_prose_after_other_spaces_also_wraps_by_character(self):
        source = '记录 数据后控制温控箱降温并记录同上'
        wrapped = rows(source)
        self.assertTrue(wrapped[0].startswith('记录 数据后控制温控箱'))
        self.assertEqual(''.join(wrapped), source)

    def test_latin_words_stay_together_but_not_at_cost_of_a_lone_label(self):
        self.assertEqual(rows('Hello world', 8), ['Hello', 'world'])
        for prefix in ('3. ', '12) ', '(4) ', '三、 ', '- '):
            wrapped = rows(prefix + 'ABCDEFGHIJK', 8)
            self.assertTrue(wrapped[0].startswith(prefix + 'ABC'), wrapped)
            self.assertEqual(''.join(wrapped), prefix + 'ABCDEFGHIJK')
        self.assertEqual(rows('ABCDEFGHIJK', 8), ['ABCDEFGH', 'IJK'])

    def test_explicit_line_breaks_and_blank_lines_are_retained(self):
        self.assertEqual(rows('3.\n\n控制温控箱'), ['3.', '', '控制温控箱'])
        self.assertEqual(rows('  控制温控箱'), ['  控制温控箱'])

    def test_punctuation_and_formula_wrapping_remain_atomic(self):
        wrapped = rows('控制温度（记录）', 7)
        self.assertEqual(''.join(wrapped), '控制温度（记录）')
        self.assertTrue(all(not line.startswith('）') and not line.endswith('（') for line in wrapped))
        formula = Token('$x+1$', Box(4, 1, 1, []), 4, formula=True)
        tokens = [Token(c,Box(1,1,1,[]),1) for c in 'A '] + [formula] + [Token(c,Box(1,1,1,[]),1) for c in 'BBB']
        output = notebook_rows(tokens, {'usable':7})
        self.assertEqual(sum(t is formula for line in output for t in line), 1)
        text = '3. 你好世界你好世界你好世界你好世界'
        data = dict(text=text, width=60, height=297, margin=10, size=5, spacing=.5, rows=20)
        single = generate(FONT, data)
        mixed = generate(FONT, data, [dict(font_id='fixture',path=FONT,weight=1)])
        for input_format in ('plain','markdown'):
            document = generate_document(FONT, {**data, 'layout_mode':'notebook','input_format':input_format})
            for result in (single, mixed, document[0]):
                self.assertTrue(result['metadata']['lines'][0].startswith('3. 你好'), result['metadata']['lines'])
                self.assertEqual(''.join(result['metadata']['lines']), text)


if __name__ == '__main__':
    unittest.main()
