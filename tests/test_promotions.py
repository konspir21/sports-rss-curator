import unittest
from pathlib import Path
from unittest.mock import patch
import tempfile
import datetime as dt
import xml.etree.ElementTree as E
import curator as c

class Promotions(unittest.TestCase):
    def item(self,title):
        return dict(title=title,link='https://example.org/a',id='original-guid',date=dt.datetime(2026,11,1,tzinfo=c.UTC),summary='',sources=['A'])
    def test_observed_promotions(self):
        for title in ['Παναθηναϊκός - ΑΕΚ με 0% γκανιότα και σούπερ Ενισχυμένα','One ad blocker protects 9 devices for life for just $15','Get Office 2024 with a lifetime license for $49']:
            self.assertTrue(c.is_promotional(self.item(title)),title)
    def test_ordinary_news_is_retained(self):
        for title in ['Apple announces iPhone 18 price of $799','How long will your iPhone battery last?','Ο Παναθηναϊκός υποδέχεται την ΑΕΚ','Lifetime achievement award presented to designer']:
            self.assertFalse(c.is_promotional(self.item(title)),title)
    def test_previously_selected_promotion_hidden_without_mutating_history(self):
        item=self.item('One ad blocker for life for just $15');news={**item,'title':'Apple releases iOS update','id':'news-guid'}
        with tempfile.TemporaryDirectory() as d,patch.object(c,'OUTPUT',Path(d)/'feed.xml'):
            c.xml_output([item,news],dt.datetime.now(c.UTC))
            nodes=E.parse(c.OUTPUT).findall('./channel/item')
            self.assertEqual([x.findtext('guid') for x in nodes],['news-guid'])
            self.assertEqual(item['id'],'original-guid')
            self.assertEqual(item['link'],'https://example.org/a')
