#!/usr/bin/env python3
"""Small no-API-key RSS curation engine. Uses Python standard library only."""
import datetime as dt
import difflib
import email.utils
import hashlib
import html
import json
import re
import sys
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).parent
CONFIG = json.loads((ROOT / 'config.json').read_text(encoding='utf-8'))
STATE_PATH = ROOT / 'state.json'
OUTPUT = ROOT / 'docs' / 'feed.xml'
UTC = dt.timezone.utc
TITLE_STOP = set('και στην στον στην της των τον στο στη στης για από με του ένα μια μιας ότι τον την τα το οι ο η σε που ως θα δεν επί κατά στο μετά'.split())
HIGH = ['τελικ', 'πρωταθλη', 'κατεκτησ', 'κυπελλ', 'champions league', 'europa league', 'world cup', 'mundial', 'παγκοσμι', 'ρεκορ', 'μεταγραφ', 'απολυ', 'παραιτη', 'εθνικ', 'ολυμπιακ', 'derby', 'ντερμπι', 'grand prix', 'formula 1', 'nba', 'euroleague', 'τροπαι', 'τιτλο']
LOW = ['δηλωσ', 'ανάρτησ', 'αναρτησ', 'stories', 'instagram', 'video', 'βιντεο', 'viral', 'κουιζ', 'τι ειπε', 'ατακεσ', 'ατακες', 'παρασκην', 'φημεσ', 'φήμες', 'εκπομπ', 'παρακολουθηστε live']
OTHER_SPORT = ['μπασκετ', 'basket', 'nba', 'euroleague', 'f1', 'formula 1', 'tennis', 'τενισ', 'βολει', 'στιβ', 'ολυμπιακ', 'motogp']


def normalize(s):
    s = unicodedata.normalize('NFD', html.unescape(re.sub('<[^>]+>', ' ', s or '')))
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn').lower().replace('ς', 'σ')
    return re.sub(r'[^a-zα-ω0-9]+', ' ', s).strip()


def title_tokens(title):
    return {t for t in normalize(title).split() if len(t) > 2 and t not in TITLE_STOP}


def date_parse(value):
    if not value: return None
    try: return email.utils.parsedate_to_datetime(value).astimezone(UTC)
    except Exception: pass
    try: return dt.datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(UTC)
    except Exception: return None


def field(el, names):
    for child in el:
        key = child.tag.split('}')[-1]
        if key in names and child.text and child.text.strip(): return child.text.strip()
    return ''


def parse_feed(content, name, weight):
    root = ET.fromstring(content)
    out = []
    for elem in root.iter():
        if elem.tag.split('}')[-1] not in ('item', 'entry'): continue
        title = field(elem, {'title'})
        link = field(elem, {'link'})
        if not link:
            for c in elem:
                if c.tag.split('}')[-1] == 'link' and c.attrib.get('href'):
                    link = c.attrib['href']; break
        published = date_parse(field(elem, {'pubDate','published','updated','date'}))
        summary = field(elem, {'description','summary','content'})
        if title and link and link.startswith(('https://','http://')) and published:
            out.append({'title':title,'link':link,'date':published,'summary':re.sub('<[^>]*>',' ',summary)[:350], 'sources':[name], 'weight':weight})
    return out


def fetch(source):
    req = urllib.request.Request(source['url'],headers={'User-Agent':'SportsRSSCurator/1.0 (personal RSS aggregator; Python urllib)', 'Accept':'application/rss+xml,application/atom+xml,application/xml,text/xml,*/*'})
    with urllib.request.urlopen(req, timeout=18) as r: return parse_feed(r.read(4_000_000),source['name'],source['weight'])


def score(item):
    title = normalize(item['title'])
    total = item['weight'] * 2
    total += min(4, len(item['sources']) - 1) * 3.5
    total += sum(2.4 for term in HIGH if normalize(term) in title)
    total -= sum(1.8 for term in LOW if normalize(term) in title)
    if any(normalize(t) in title for t in OTHER_SPORT): total -= 0.7
    return round(total, 3)


def cluster(items):
    groups=[]
    for item in sorted(items,key=lambda x:x['date'],reverse=True):
        tok = title_tokens(item['title'])
        match=None
        for g in groups:
            if abs((item['date']-g['date']).total_seconds()) > 60*60*36: continue
            old = title_tokens(g['title'])
            jacc = len(tok & old) / max(1,len(tok | old))
            ratio = difflib.SequenceMatcher(None,normalize(item['title']),normalize(g['title'])).ratio()
            if (jacc >= .58 and len(tok & old)>=3) or ratio>=.78:
                match=g;break
        if match:
            if item['sources'][0] not in match['sources']: match['sources'].append(item['sources'][0])
            if item['weight']>match['weight']: match.update({k:item[k] for k in ['title','link','weight','summary']})
        else: groups.append(item.copy())
    return groups


def xml_output(records, now):
    from xml.sax.saxutils import escape
    def e(x): return escape(str(x or ''))
    parts=['<?xml version="1.0" encoding="UTF-8"?>','<rss version="2.0"><channel>',f'<title>{e(CONFIG["feed_title"])}</title>', '<link>https://github.com/</link>', '<description>Selected sports headlines from independent RSS sources. Original publishers retain their content.</description>', '<language>el</language>',f'<lastBuildDate>{email.utils.format_datetime(now)}</lastBuildDate>']
    for r in sorted(records,key=lambda x:x['date'],reverse=True):
        parts.extend(['<item>',f'<title>{e(r["title"])}</title>',f'<link>{e(r["link"])}</link>',f'<guid isPermaLink="false">{e(r["id"])}</guid>',f'<pubDate>{email.utils.format_datetime(r["date"])}</pubDate>',f'<description>{e("Πηγές: " + ", ".join(r["sources"]) + ". " + r["summary"])}</description>','</item>'])
    parts.append('</channel></rss>')
    OUTPUT.parent.mkdir(exist_ok=True)
    OUTPUT.write_text('\n'.join(parts),encoding='utf-8')


def run(now=None, source_items=None):
    now=now or dt.datetime.now(UTC)
    tz=ZoneInfo(CONFIG['timezone'])
    try: state=json.loads(STATE_PATH.read_text(encoding='utf-8'))
    except (FileNotFoundError,json.JSONDecodeError): state={'selected':[]}
    previous=[]
    for p in state['selected']:
        try: p['date']=dt.datetime.fromisoformat(p['date']); previous.append(p)
        except (ValueError,KeyError): pass
    incoming=[]; ok=0
    if source_items is not None: incoming=source_items;ok=1
    else:
        for src in CONFIG['sources']:
            try:
                entries=fetch(src);incoming.extend(entries);ok+=1
                print(f'{src["name"]}: {len(entries)} entries')
            except Exception as exc: print(f'WARN {src["name"]}: {exc}',file=sys.stderr)
    if not ok: raise RuntimeError('No sources available; leaving existing feed untouched')
    min_date=now-dt.timedelta(hours=CONFIG['lookback_hours'])
    groups=cluster([x for x in incoming if min_date <= x['date'] <= now+dt.timedelta(minutes=5)])
    existing_ids={p['id'] for p in previous}
    new=[]
    for g in groups:
        # Stable ID follows canonical article URL; clustering picks one representative publisher link.
        g['id']=hashlib.sha256(g['link'].encode('utf-8')).hexdigest()[:24]
        if g['id'] not in existing_ids: new.append(g)
    new.sort(key=lambda x:(score(x),x['date']),reverse=True)
    per_day=defaultdict(int)
    for p in previous: per_day[p['date'].astimezone(tz).date()]+=1
    selected=[]
    for g in new:
        day=g['date'].astimezone(tz).date()
        if per_day[day]>=CONFIG['hard_cap_per_day'] or len(selected)>=12: continue
        selected.append(g); per_day[day]+=1
    combined=previous+selected
    display_cut=now-dt.timedelta(days=CONFIG['display_days'])
    combined=[p for p in combined if p['date']>=display_cut]
    combined.sort(key=lambda x:x['date'],reverse=True)
    xml_output(combined,now)
    state['selected']=[{**p,'date':p['date'].isoformat()} for p in combined]
    STATE_PATH.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Accepted {len(selected)} new, total display {len(combined)}. Source fetches successful {ok}.')
    return combined

if __name__=='__main__':run()
