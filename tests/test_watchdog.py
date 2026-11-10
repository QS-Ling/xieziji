"""Controller watchdog: transport-fault detection and idle auto-recovery."""
import pathlib
import tempfile
import threading
import unittest
from backend.watchdog import ControllerWatchdog


class FakeClient:
    def __init__(self, state):
        self.state = state
        self.connected = []
        self.released = threading.Event()

    def snapshot(self):
        return dict(self.state)

    def connect(self, port, control=None):
        self.connected.append((port, control))
        self.released.set()
        return dict(self.state, connected=True, phase='idle', error=None)


class FakeProfiles:
    def all(self):
        return {'COM5': {'device_control': {'pen_up': 0, 'pen_down': 10, 'pen_feed': 600}}}


def fault(error='Controller status timeout', **fields):
    state = {'phase': 'failed', 'connected': True, 'operation_type': None,
             'port': 'COM5', 'error': error}
    state.update(fields)
    return state


class WatchdogDetectionTests(unittest.TestCase):
    def test_status_poll_timeout_is_a_serial_fault(self):
        self.assertTrue(ControllerWatchdog._is_serial_fault(fault()))
        self.assertTrue(ControllerWatchdog._is_serial_fault(fault('Command acknowledgement timeout')))
        self.assertTrue(ControllerWatchdog._is_serial_fault(fault('Serial read failed')))

    def test_operation_and_firmware_errors_are_not_serial_faults(self):
        for error in ('ALARM:1', 'error:9', 'Machine must be Idle',
                      'Task already claimed; never automatically replay'):
            self.assertFalse(ControllerWatchdog._is_serial_fault(fault(error)), error)

    def test_only_idle_failed_controllers_are_recovered(self):
        self.assertFalse(ControllerWatchdog._is_serial_fault(fault(phase='idle')))
        self.assertFalse(ControllerWatchdog._is_serial_fault(fault(connected=False)))
        self.assertFalse(ControllerWatchdog._is_serial_fault(fault(operation_type='writing')))
        self.assertFalse(ControllerWatchdog._is_serial_fault(fault(error=None)))


class WatchdogRecoveryTests(unittest.TestCase):
    def test_idle_fault_restarts_service_and_reconnects(self):
        with tempfile.TemporaryDirectory() as directory:
            client = FakeClient(fault())
            watchdog = ControllerWatchdog(client, FakeProfiles(), pathlib.Path(directory),
                                          interval=.01, stable_seconds=0., reconnect_interval=.01)
            restarted = []
            watchdog._restart_service = lambda: restarted.append(True)
            watchdog.start()
            try:
                self.assertTrue(client.released.wait(5), 'watchdog did not reconnect')
            finally:
                watchdog.stop()
            self.assertEqual(restarted, [True])
            self.assertEqual(client.connected, [('COM5', {'pen_up': 0, 'pen_down': 10, 'pen_feed': 600})])


if __name__ == '__main__':
    unittest.main()
