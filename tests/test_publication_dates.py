import datetime as dt
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import curator as c

class PublicationDates(unittest.TestCase):
    def test_original_dates_and_order_even_when_admission_times_conflict(self):
        now=dt.datetime(2026,10,31,12,tzinfo=c.UTC)
        a=dict(title='Older article',link='https://example.org/old',id='stable-old',date=now-dt.timedelta(hours=4),selected_at=now.isoformat(),sources=['A'],summary='')
        b={**a,'title':'Newer article','link':'https://example.org/new','id':'stable-new','date':now-dt.timedelta(hours=1),'selected_at':(now-dt.timedelta(hours=2)).isoformat()}
        with tempfile.TemporaryDirectory() as d,patch.object(c,'OUTPUT',Path(d)/'feed.xml'):
            c.xml_output([a,b],now)
            root=ET.parse(c.OUTPUT);items=root.findall('./channel/item')
            self.assertEqual([x.findtext('guid') for x in items],['stable-new','stable-old'])
            self.assertEqual(c.date_parse(items[0].findtext('pubDate')),b['date'])
            self.assertEqual(c.date_parse(items[1].findtext('pubDate')),a['date'])
            self.assertEqual(root.findtext('./channel/lastBuildDate'),c.email.utils.format_datetime(now))
            self.assertTrue(all('}' not in child.tag for item in items for child in item))
