from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import curator as c
import run_all

class Runner(unittest.TestCase):
    def test_other_groups_still_run_when_one_fails(self):
        with patch.object(run_all.subprocess,'run',side_effect=[SimpleNamespace(returncode=1),SimpleNamespace(returncode=0),SimpleNamespace(returncode=0)]) as call:
            self.assertTrue(run_all.run_profiles())
            self.assertEqual([x.args[0][-1] for x in call.call_args_list],['sports','news','apple'])

    def test_all_succeed(self):
        with patch.object(run_all.subprocess,'run',return_value=SimpleNamespace(returncode=0)):
            self.assertFalse(run_all.run_profiles())

    def test_corrupt_history_does_not_reset(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'state.json';output=Path(d)/'feed.xml'
            path.write_text('broken');output.write_text('original feed')
            with patch.object(c,'STATE_PATH',path),patch.object(c,'OUTPUT',output):
                with self.assertRaises(RuntimeError):c.run(source_items=[])
            self.assertEqual(path.read_text(),'broken')
            self.assertEqual(output.read_text(),'original feed')
