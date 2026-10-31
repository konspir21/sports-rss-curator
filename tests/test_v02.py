import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import curator as c

class V02(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name)/'state.json'
        self.output = Path(self.temp.name)/'feed.xml'
        self.patches = [patch.object(c, 'STATE_PATH', self.state), patch.object(c, 'OUTPUT', self.output)]
        for p in self.patches:
            p.start(); self.addCleanup(p.stop)
        self.now = dt.datetime(2026, 10, 31, 18, 17, tzinfo=c.UTC)

    def items(self, n=70):
        return [dict(title=f'Story {i:04d} unique{i} event{i} club{i}', link=f'https://example.org/{i}', date=self.now-dt.timedelta(minutes=i), summary='summary & text', sources=['A'], weight=1) for i in range(n)]

    def test_initial_target_and_rerun_ids(self):
        with patch.object(c, 'cluster', side_effect=lambda x:x):
            first = c.run(self.now, self.items())
            second = c.run(self.now, self.items())
        self.assertEqual(len(first), 40)
        self.assertEqual([i['id'] for i in first], [i['id'] for i in second])
        self.assertTrue(all(i['id']==hashlib.sha256(i['link'].encode()).hexdigest()[:24] for i in first))

    def test_pacing_and_boundaries(self):
        tz=c.ZoneInfo('Europe/Athens')
        self.assertEqual(c.admission_limit(self.now.date(), self.now, tz, False),40)
        morning=self.now.replace(hour=6)
        self.assertEqual(c.admission_limit(morning.date(),morning,tz,False),10)
        self.assertEqual(c.admission_limit(self.now.date()-dt.timedelta(days=1),self.now,tz,False),40)
        self.assertEqual(c.admission_limit(self.now.date()+dt.timedelta(days=1),self.now,tz,True),0)
        with patch.dict(c.CONFIG, target_per_day=100):
            self.assertEqual(c.admission_limit(self.now.date(),self.now,tz,True),50)

    def test_legacy_migration(self):
        old=self.items(1)[0];old['id']='legacy-guid'
        self.state.write_text(json.dumps({'selected':[{**old,'date':old['date'].isoformat()}]}))
        result=c.run(self.now,self.items(1))
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['id'],'legacy-guid')
        self.assertEqual(result[0]['link'],old['link'])

    def test_image_formats_and_atom_alternate(self):
        for image in ['<media:content url="/photo.jpg" medium="image"/>','<enclosure url="/photo.jpg" type="image/jpeg"/>','<description>&lt;img src="/photo.jpg"/&gt;</description>']:
            feed=f'<rss xmlns:media="http://search.yahoo.com/mrss/"><channel><item><title>A</title><link>https://example.org/a</link><pubDate>Sat, 31 Oct 2026 10:00:00 GMT</pubDate>{image}</item></channel></rss>'
            self.assertEqual(c.parse_feed(feed,'A',1)[0]['image'],'https://example.org/photo.jpg')
        feed='<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>A</title><link rel="self" href="https://example.org/feed"/><link rel="alternate" href="https://example.org/a"/><updated>2026-10-31T10:00:00Z</updated></entry></feed>'
        self.assertEqual(c.parse_feed(feed,'A',1)[0]['link'],'https://example.org/a')

    def test_metadata_and_xml(self):
        parser=c.ImageParser('https://example.org/a')
        parser.feed('<meta content="/hero.jpg?a=1&amp;b=2" property="og:image">')
        image=parser.result()
        self.assertEqual(image,'https://example.org/hero.jpg?a=1&b=2')
        item=self.items(1)[0];item.update(id='stable',image=image)
        c.xml_output([item],self.now)
        root=ET.parse(self.output)
        node=root.find('./channel/item')
        self.assertEqual(node.find('guid').text,'stable')
        self.assertTrue(all('}' not in child.tag for child in node))
        body=ET.fromstring('<body>'+node.find('description').text+'</body>')
        self.assertEqual(body.find('./p/img').get('src'),image)
        self.assertEqual(len(node.findall('pubDate')),1)
        self.assertIn('<img src=',node.find('description').text)

    def test_source_failure_preserves_files(self):
        self.state.write_text('{"selected": []}')
        self.output.write_text('original')
        with patch.object(c,'fetch',side_effect=RuntimeError('offline')):
            with self.assertRaises(RuntimeError):c.run(self.now)
        self.assertEqual(self.state.read_text(),'{"selected": []}')
        self.assertEqual(self.output.read_text(),'original')
