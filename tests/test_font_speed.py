import json
import math
import pathlib
import unittest
from backend.font_speed import BENCHMARK, assign_scores, motion_cost, travel_seconds
from backend.font_library import FontLibrary
from tests.test_service import FONT, test_temp


class FontSpeedTests(unittest.TestCase):
    def test_triangular_and_cruising_motion(self):
        self.assertAlmostEqual(travel_seconds(10,3000,8000),.20625)
        self.assertAlmostEqual(travel_seconds(.01,3000,3000),2*math.sqrt(.01/3000))
        self.assertEqual(travel_seconds(0,3000,3000),0)

    def test_more_pen_lifts_or_longer_paths_cost_more(self):
        joined=motion_cost([[(0,0),(1,0),(2,0)]],6)
        split=motion_cost([[(0,0),(1,0)],[(1,0),(2,0)]],6)
        longer=motion_cost([[(0,0),(10,0),(2,0)]],6)
        self.assertEqual(joined['draw_mm'],split['draw_mm'])
        self.assertGreater(split['seconds'],joined['seconds'])
        self.assertGreater(longer['seconds'],joined['seconds'])
        self.assertAlmostEqual(split['pen_seconds'],2*joined['pen_seconds'])
        self.assertIsNone(motion_cost([],6))

    def test_collinear_vector_segmentation_does_not_change_score_cost(self):
        a=motion_cost([[(0,0),(2,0)]],6)
        b=motion_cost([[(0,0),(.5,0),(1,0),(1.5,0),(2,0)]],6)
        self.assertEqual(a['seconds'],b['seconds'])

    def test_missing_complex_characters_are_not_scored_as_time_saved(self):
        def cost(seconds):
            return dict(seconds=seconds,draw_mm=1,move_mm=1,strokes=1,pen_seconds=.5)
        normal={'一':cost(1),'繁':cost(10)}
        scores=assign_scores(dict(a=normal,b=normal,c=normal,missing={'一':cost(1)},slow={'一':cost(2),'繁':cost(20)},none={}))
        self.assertEqual(scores['a']['score'],100)
        self.assertEqual(scores['missing']['score'],100)
        self.assertEqual(scores['slow']['score'],50)
        self.assertEqual(scores['missing']['confidence'],'limited')
        self.assertIsNone(scores['none']['score'])

    def test_only_matching_font_files_receive_scores_even_without_similarity_report(self):
        with test_temp() as temp:
            report=pathlib.Path(temp)/'speed.json'
            item=dict(id='font',file=FONT.name,bytes=FONT.stat().st_size,speed=dict(score=123))
            report.write_text(json.dumps(dict(fonts=[item],benchmark=BENCHMARK)),encoding='utf8')
            library=FontLibrary({'font':FONT},pathlib.Path(temp)/'missing.json',report)
            result=library.recommendations()
            self.assertEqual(result['fonts']['font']['speed']['score'],123)
            self.assertEqual(result['summary']['speed_fonts'],1)
            item['bytes']+=1
            report.write_text(json.dumps(dict(fonts=[item])),encoding='utf8')
            self.assertEqual(library.recommendations()['summary']['speed_fonts'],0)


if __name__=='__main__':unittest.main()
