from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
import threading
from unittest.mock import patch
import curator as c
import run_all

class Runner(unittest.TestCase):
    def test_other_groups_still_run_when_one_fails(self):
        with patch.object(run_all.subprocess,'run',side_effect=lambda cmd, **kw: SimpleNamespace(returncode=int(cmd[-1] == 'sports'))) as call:
            self.assertTrue(run_all.run_profiles())
            self.assertCountEqual([x.args[0][-1] for x in call.call_args_list],['sports','news','apple'])

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

    def test_profiles_start_concurrently(self):
        barrier = threading.Barrier(3)
        def build(cmd, **kwargs):
            barrier.wait(timeout=3)
            return SimpleNamespace(returncode=0)
        with patch.object(run_all.subprocess, 'run', side_effect=build):
            self.assertFalse(run_all.run_profiles())

    def test_sources_overlap_but_keep_configuration_order(self):
        barrier = threading.Barrier(3)
        sources = [dict(name=name, url='https://example.org/' + name, weight=1)
                   for name in ('a', 'b', 'c')]
        seen = []
        def fetch(source):
            barrier.wait(timeout=3)
            if source['name'] == 'b':
                raise RuntimeError('one source offline')
            return [dict(title=source['name'], link=source['url'], date=c.dt.datetime.now(c.UTC),
                         sources=[source['name']], weight=1, summary='', image='')]
        def cluster(items):
            seen.extend(x['title'] for x in items)
            return []
        with tempfile.TemporaryDirectory() as d:
            with patch.dict(c.CONFIG, sources=sources), patch.object(c, 'fetch', side_effect=fetch), \
                 patch.object(c, 'cluster', side_effect=cluster), patch.object(c, 'enrich_images'), \
                 patch.object(c, 'STATE_PATH', Path(d)/'state.json'), patch.object(c, 'OUTPUT', Path(d)/'feed.xml'):
                c.run()
            self.assertEqual(seen, ['a', 'c'])
            self.assertTrue((Path(d)/'feed.xml').exists())
