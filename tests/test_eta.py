"""Deterministic ETA tests: weighted work, clock isolation, pause and buffering."""
import pathlib
import unittest

from backend.eta import TaskETA, path_work
from tests.test_service import test_temp


class ETATests(unittest.TestCase):
    def setUp(self):
        self.temp = test_temp()
        self.root = pathlib.Path(self.temp.name)
        self.job = 'a' * 32
        folder = self.root / self.job
        folder.mkdir()
        self.code = ''.join(f'G1 X{i} Y0 F600\n' for i in range(1,201))
        (folder / 'job.gcode').write_text(self.code,encoding='ascii')
        self.tracker = TaskETA(self.root)
        self.state = dict(job_id=self.job,total=200,acknowledged=16,phase='running',connected=True,feed_override=100)

    def tearDown(self):
        self.temp.cleanup()

    def estimate(self, now, **updates):
        self.state.update(updates)
        return self.tracker.decorate(self.state,now=now,wall=100000+now)['eta']

    def test_initial_path_estimate_calibrates_by_actual_progress(self):
        initial = self.estimate(0)
        self.assertEqual(initial['source'],'path')
        self.assertAlmostEqual(initial['remaining_seconds'],20,delta=1)
        observed = self.estimate(10,acknowledged=116)
        self.assertEqual(observed['source'],'observed')
        self.assertAlmostEqual(observed['remaining_seconds'],10,delta=1)
        self.assertGreater(observed['estimated_finish_at'],100010)

    def test_speed_change_updates_eta_only_when_applied(self):
        self.estimate(0)
        fast = self.estimate(10,acknowledged=116)
        requested = self.estimate(10,feed_override_requested=50)
        self.assertEqual(fast['remaining_seconds'],requested['remaining_seconds'])
        slow = self.estimate(10,feed_override=50)
        self.assertAlmostEqual(slow['remaining_seconds'],fast['remaining_seconds']*2,delta=1)

    def test_duplicate_clock_ticks_and_stale_progress_do_not_reset_calibration(self):
        self.estimate(0)
        for tick in range(1,11):
            self.estimate(tick,acknowledged=16+tick*5)
            self.estimate(tick,acknowledged=17+tick*5)
            result = self.estimate(tick,acknowledged=15+tick*5)
        self.assertEqual(result['source'],'observed')
        self.assertGreater(result['remaining_seconds'],0)

    def test_pause_does_not_include_paused_time_in_rate(self):
        self.estimate(0)
        self.estimate(10,acknowledged=116)
        paused = self.estimate(11,phase='paused')
        self.assertIsNone(paused['estimated_finish_at'])
        later = self.estimate(111)
        self.assertEqual(paused['remaining_seconds'],later['remaining_seconds'])
        self.estimate(112,phase='running')
        resumed = self.estimate(122,acknowledged=166)
        self.assertLess(resumed['remaining_seconds'],10)

    def test_acknowledged_full_job_waits_for_physical_completion(self):
        self.estimate(0)
        tail = self.estimate(1,acknowledged=200,phase='draining')
        self.assertGreater(tail['remaining_seconds'],0)
        overdue = self.estimate(100)
        self.assertEqual(overdue['status'],'draining')
        self.assertIsNone(overdue['estimated_finish_at'])
        self.assertIsNone(overdue['remaining_seconds'])
        complete = self.estimate(101,phase='complete')
        self.assertEqual(complete['remaining_seconds'],0)

    def test_draining_pause_freezes_tail_countdown(self):
        self.estimate(0,acknowledged=200,phase='draining')
        paused = self.estimate(.5,phase='paused')
        later = self.estimate(100,phase='paused')
        self.assertEqual(paused['remaining_seconds'],later['remaining_seconds'])
        resumed = self.estimate(101,phase='running')
        self.assertEqual(resumed['status'],'draining')
        self.assertGreater(resumed['remaining_seconds'],0)

    def test_backend_can_attach_to_an_existing_job_after_restart(self):
        existing = self.estimate(5000,acknowledged=116)
        self.assertEqual(existing['source'],'path')
        self.assertLess(existing['remaining_seconds'],20)
        self.assertEqual(self.estimate(5010,acknowledged=166)['source'],'observed')

    def test_missing_or_mismatched_file_uses_measured_command_rate(self):
        (self.root / self.job / 'job.gcode').unlink()
        self.assertIsNone(self.estimate(0)['remaining_seconds'])
        measured = self.estimate(10,acknowledged=116)
        self.assertEqual(measured['source'],'observed')
        self.assertGreater(measured['remaining_seconds'],0)
        wrong = self.root / 'wrong.gcode'
        wrong.write_text('G1 X1 Y0 F600\n',encoding='ascii')
        self.assertIsNone(path_work(wrong,200))

    def test_terminal_disconnect_and_new_job_clear_old_estimates(self):
        self.estimate(0)
        for phase in ('stopping','stopped','returning','failed'):
            eta = self.estimate(10,phase=phase)
            self.assertIsNone(eta['remaining_seconds'])
            self.assertIsNone(eta['estimated_finish_at'])
        self.assertEqual(self.estimate(11,connected=False)['status'],'unavailable')
        new_job = 'b'*32
        (self.root/new_job).mkdir()
        (self.root/new_job/'job.gcode').write_text(self.code,encoding='ascii')
        eta = self.estimate(12,job_id=new_job,phase='running',connected=True,acknowledged=0)
        self.assertEqual(eta['source'],'path')
        self.assertAlmostEqual(eta['remaining_seconds'],20,delta=1)
        self.assertIsNone(self.estimate(13,job_id='../other')['remaining_seconds'])

    def test_long_z_travel_is_weighted_more_than_short_drawing_segments(self):
        path = self.root/'profile.gcode'
        path.write_text('G1 Z10 F3000\nG1 X0.1 Y0 F10000\nG1 Z0 F3000\n',encoding='ascii')
        work = path_work(path,3)
        self.assertAlmostEqual(work[1],.2)
        self.assertLess(work[2]-work[1],.01)
        self.assertGreater(work[3]-work[2],.19)


if __name__ == '__main__':
    unittest.main()
