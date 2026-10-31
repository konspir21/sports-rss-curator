import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import curator as c

class Profiles(unittest.TestCase):
    def item(self,title,host='one.example',**extra):
        return {'title':title,'link':'https://'+host+'/story','date':dt.datetime(2026,10,31,10,tzinfo=c.UTC),'summary':'summary','sources':[host],'weight':1,'image':'https://example.org/image.jpg',**extra}

    def test_bilingual_release(self):
        with patch.dict(c.CONFIG,profile='apple'):
            a=self.item('Apple releases iOS 26.1 update')
            b=self.item('Διαθέσιμη η ενημέρωση iOS 26.1',host='two.example')
            self.assertTrue(c.same_story(a,b))
            self.assertEqual(len(c.cluster([a,b])),1)

    def test_different_versions_products_and_stage_remain_separate(self):
        with patch.dict(c.CONFIG,profile='apple'):
            a=self.item('Apple releases iOS 26.1 update')
            for title in ['Apple releases iOS 26.2 update','Apple releases iPadOS 26.1 update','Apple releases iOS 26.1 beta','iOS 26.1 review']:
                self.assertFalse(c.same_story(a,self.item(title,host='two.example')))

    def test_independent_reviews_retained(self):
        with patch.dict(c.CONFIG,profile='apple'):
            a=self.item('iPhone 18 Pro review')
            b=self.item('iPhone 18 Pro review',host='two.example')
            self.assertEqual(len(c.cluster([a,b])),2)

    def test_news_numbers_differ(self):
        with patch.dict(c.CONFIG,profile='news'):
            a=self.item('Σεισμός 5 Ρίχτερ στην Κρήτη')
            b=self.item('Σεισμός 6 Ρίχτερ στην Κρήτη',host='two.example')
            self.assertFalse(c.same_story(a,b))

    def test_news_quality_and_no_sports_keywords(self):
        with patch.dict(c.CONFIG,profile='news'):
            self.assertGreater(c.score(self.item('Νέο νομοσχέδιο για τη φορολογία')),c.score(self.item('Ζώδια: δεν θα πιστεύετε τι έγινε')))
            self.assertEqual(c.score(self.item('Champions League τελικός')),2)

    def test_source_scope(self):
        news=json.loads((c.ROOT/'config-news.json').read_text())
        apple=json.loads((c.ROOT/'config-apple.json').read_text())
        self.assertEqual(len(news['sources']),3)
        self.assertEqual(len(apple['sources']),6)
        self.assertNotIn('https://www.skai.gr/rss/opinions',[x['url'] for x in news['sources']])

    def test_isolated_files_and_reruns(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'docs').mkdir()
            for name in ['sports','news','apple']:
                config={'feed_title':name,'timezone':'Europe/Athens','target_per_day':None,'hard_cap_per_day':None,'lookback_hours':36,'display_days':3,'sources':[],'profile':name}
                (root/('config.json' if name=='sports' else f'config-{name}.json')).write_text(json.dumps(config))
            with patch.object(c,'ROOT',root),patch.object(c,'CONFIG',c.CONFIG),patch.object(c,'STATE_PATH',c.STATE_PATH),patch.object(c,'OUTPUT',c.OUTPUT):
                for name in ['sports','news','apple']:
                    c.activate_profile(name)
                    item=self.item('Distinct article '+name)
                    now=item['date']+dt.timedelta(hours=1)
                    a=c.run(now,source_items=[item]);before=c.STATE_PATH.read_bytes()
                    b=c.run(now,source_items=[item]);self.assertEqual(len(b),1)
                    self.assertEqual(c.STATE_PATH.read_bytes(),before)
                    self.assertTrue(c.OUTPUT.exists())
                self.assertEqual(len(list(root.glob('state*.json'))),3)
                self.assertEqual(len(list((root/'docs').glob('*.xml'))),3)

    def test_existing_history_not_reclustered_into_replacements(self):
        with patch.dict(c.CONFIG,profile='sports'):
            a=self.item('Η Μπαρτσελόνα ανακοίνωσε μεγάλη μεταγραφή επιθετικού','www.athletiko.gr')
            b={**a,'link':'https://www.gazzetta.gr/other','sources':['Gazzetta']}
            self.assertTrue(c.same_story(a,b))
            self.assertEqual(c.cluster([a,b])[0]['link'],b['link'])
