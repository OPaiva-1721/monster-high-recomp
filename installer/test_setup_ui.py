import unittest
from installer.setup_ui import Model


class SetupModelTests(unittest.TestCase):
    def test_only_completed_install_enables_play(self):
        model=Model()
        for event in ({'stage':'build','status':'complete'},{'stage':'error','status':'error'},{'stage':'complete','status':'running'}):
            model.event(event);self.assertFalse(model.ready)
        model.event({'stage':'complete','status':'complete','message':'ok'})
        self.assertTrue(model.ready);self.assertEqual(model.message,'ok')
