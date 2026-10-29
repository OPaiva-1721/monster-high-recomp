import unittest
import io
from unittest.mock import Mock, patch
from installer.game_process import ClosedWindow, wait_owned


class WindowLifecycleTests(unittest.TestCase):
    def test_startup_without_window_never_expires(self):
        watch=ClosedWindow()
        self.assertFalse(watch.expired(False,0))
        self.assertFalse(watch.expired(False,10000))

    def test_visible_or_minimized_window_never_expires(self):
        watch=ClosedWindow()
        self.assertFalse(watch.expired(True,0))
        self.assertFalse(watch.expired(True,10000))

    def test_only_closed_observed_window_expires_after_grace(self):
        watch=ClosedWindow();watch.expired(True,0)
        self.assertFalse(watch.expired(False,1))
        self.assertFalse(watch.expired(False,30.99))
        self.assertTrue(watch.expired(False,31))

    def test_returning_window_resets_grace(self):
        watch=ClosedWindow();watch.expired(True,0);watch.expired(False,1)
        self.assertFalse(watch.expired(True,31))
        self.assertFalse(watch.expired(False,100))
        self.assertTrue(watch.expired(False,130))

    def test_observation_error_cannot_expire_window(self):
        watch=ClosedWindow();watch.expired(True,0);watch.expired(False,1)
        self.assertFalse(watch.expired(None,100))
        self.assertFalse(watch.expired(False,101))
        self.assertTrue(watch.expired(False,131))

    def test_taskkill_failure_falls_back_to_owned_handle(self):
        process=Mock(pid=123);process.poll.return_value=None;process.wait.return_value=1
        with patch('installer.game_process.time.monotonic',side_effect=[0,0,31]),patch('installer.game_process.time.sleep'),patch('installer.game_process.subprocess.run',return_value=Mock(returncode=1)) as kill:
            self.assertEqual(wait_owned(process,io.BytesIO(),observe=Mock(side_effect=[True,False,False])),1)
        process.terminate.assert_called_once();process.wait.assert_called_once_with(timeout=10)
        self.assertEqual(kill.call_args.args[0],['taskkill','/PID','123','/T','/F'])
