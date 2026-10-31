import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from curator import normalize, cluster, parse_feed, score
import datetime as dt

class TestCurator(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(normalize('Η ΑΕΚ κατέκτησε ΤΟ Κύπελλο!'),'η αεκ κατεκτησε το κυπελλο')
    def test_atom(self):
        s=b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Champions League final</title><link href="https://example.com/abc"/><updated>2026-10-30T10:00:00Z</updated></entry></feed>'
        self.assertEqual(len(parse_feed(s,'demo',1)),1)
    def test_rss(self):
        s=b'<rss><channel><item><title>Big final</title><link>https://example.com/abc</link><pubDate>Fri, 30 Oct 2026 10:00:00 GMT</pubDate></item></channel></rss>'
        self.assertEqual(len(parse_feed(s,'demo',1)),1)
    def test_similar_titles(self):
        d=dt.datetime(2026,10,30,tzinfo=dt.timezone.utc)
        a={'title':'Μεγάλη μεταγραφή της Μπαρτσελόνα στην Ισπανία','link':'https://a.com/1','date':d,'summary':'','sources':['A'],'weight':1}
        b={**a,'title':'Μεγάλη μεταγραφή της Μπαρτσελόνα στην Ισπανία!','link':'https://b.com/1','sources':['B']}
        self.assertEqual(len(cluster([a,b])),1)
    def test_score(self):
        i={'title':'Τελικός Champions League','weight':1,'sources':['A']}
        j={'title':'Δηλώσεις στην εκπομπή','weight':1,'sources':['A']}
        self.assertGreater(score(i),score(j))

if __name__=='__main__':unittest.main()

