import datetime as dt
import unittest
from curator import cluster, parse_feed, is_opinion

class SourcePreference(unittest.TestCase):
    def item(self, host, **kwargs):
        return dict(title='Η Μπαρτσελόνα ανακοίνωσε μεγάλη μεταγραφή επιθετικού',link='https://'+host+'/news/one',date=dt.datetime(2026,10,31,tzinfo=dt.timezone.utc),summary='',sources=[host],weight=1,image='https://example.org/a.jpg',**kwargs)

    def test_both_alternatives_over_athletiko_in_any_order(self):
        for host in ['www.gazzetta.gr','www.sport-fm.gr']:
            a=self.item('www.athletiko.gr');a['weight']=2
            b=self.item(host)
            for batch in [[a,b],[b,a]]:
                result=cluster(batch)
                self.assertEqual(len(result),1)
                self.assertEqual(result[0]['link'],b['link'])
                self.assertEqual(len(result[0]['sources']),2)
            self.assertEqual(a['sources'],['www.athletiko.gr'])

    def test_unique_athletiko_retained(self):
        a=self.item('www.athletiko.gr')
        self.assertEqual(cluster([a])[0]['link'],a['link'])

    def test_no_preference_without_alternative_image(self):
        a=self.item('www.athletiko.gr');a['weight']=2
        b=self.item('www.gazzetta.gr');b['image']=''
        self.assertEqual(cluster([a,b])[0]['link'],a['link'])

    def test_opinions_from_each_source_remain_separate(self):
        a=self.item('www.athletiko.gr',categories=['Απόψεις'])
        b=self.item('www.gazzetta.gr',categories=['Opinion'])
        news=self.item('www.sport-fm.gr')
        self.assertEqual(len(cluster([a,b,news])),3)

    def test_opinion_url_and_title(self):
        a=self.item('www.athletiko.gr');a['link']='https://www.athletiko.gr/blogs/one'
        self.assertTrue(is_opinion(a))
        a['link']='https://www.athletiko.gr/news/one';a['title']='Γνώμη: Η ομάδα άλλαξε'
        self.assertTrue(is_opinion(a))

    def test_categories_retained(self):
        xml='<rss><channel><item><title>A</title><link>https://example.org/a</link><pubDate>Sat, 31 Oct 2026 10:00:00 GMT</pubDate><category>Απόψεις</category></item></channel></rss>'
        item=parse_feed(xml,'A',1)[0]
        self.assertEqual(item['categories'],['Απόψεις'])
        self.assertTrue(is_opinion(item))

    def test_same_opinion_url_not_duplicated(self):
        a=self.item('www.athletiko.gr',categories=['Απόψεις'])
        self.assertEqual(len(cluster([a,a])),1)
