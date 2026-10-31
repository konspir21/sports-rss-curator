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
import argparse
from urllib.parse import urljoin, urlsplit
from html.parser import HTMLParser
from concurrent.futures import ThreadPoolExecutor
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


def image_url(value, base):
    value = urljoin(base, html.unescape(value or '').strip())
    return value if urlsplit(value).scheme in ('https', 'http') and urlsplit(value).hostname else ''


class ImageParser(HTMLParser):
    def __init__(self, base):
        super().__init__()
        self.base, self.meta, self.inline = base, {}, []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'meta':
            key = (a.get('property') or a.get('name') or '').lower()
            if key in ('og:image', 'og:image:secure_url', 'twitter:image', 'twitter:image:src'):
                self.meta.setdefault(key, image_url(a.get('content'), self.base))
        if tag == 'img':
            value = image_url(a.get('src') or a.get('data-src'), self.base)
            if value: self.inline.append(value)

    def result(self, inline=False):
        return next((self.meta[k] for k in ('og:image:secure_url', 'og:image', 'twitter:image', 'twitter:image:src') if self.meta.get(k)), '') or (next(iter(self.inline), '') if inline else '')


def feed_image(elem, link):
    for child in elem.iter():
        tag = child.tag.split('}')[-1]
        media = child.tag.startswith('{http://search.yahoo.com/mrss/}')
        if (media and tag in ('content', 'thumbnail') and child.get('medium', 'image') == 'image' and not child.get('type', 'image/').startswith(('video/', 'audio/'))) or (tag == 'enclosure' and child.get('type', '').startswith('image/')):
            value = image_url(child.get('url'), link)
            if value: return value
    parser = ImageParser(link)
    for child in elem:
        if child.tag.split('}')[-1] in ('description', 'summary', 'content', 'encoded'):
            parser.feed(child.text or '')
            for node in child.iter():
                if node.tag.split('}')[-1] == 'img':
                    parser.handle_starttag('img', list(node.attrib.items()))
    return parser.result(inline=True)


def article_image(item):
    try:
        req = urllib.request.Request(item['link'], headers={'User-Agent': 'SportsRSSCurator/0.2 (personal RSS reader)'})
        with urllib.request.urlopen(req, timeout=6) as response:
            parser = ImageParser(response.geturl())
            parser.feed(response.read(1_500_000).decode(response.headers.get_content_charset() or 'utf-8', errors='replace'))
            return parser.result()
    except Exception as exc:
        print(f"WARN image {item['link']}: {exc}", file=sys.stderr)
        return ''


def enrich_images(records):
    missing = [r for r in records if not r.get('image')]
    with ThreadPoolExecutor(max_workers=6) as pool:
        for record, value in zip(missing, pool.map(article_image, missing)):
            if value: record['image'] = value


def admission_limit(day, now, tz, bootstrap):
    if CONFIG.get('target_per_day') is None:
        return float('inf') if day <= now.astimezone(tz).date() else 0
    cap = CONFIG['hard_cap_per_day']
    target = min(cap, CONFIG['target_per_day'])
    local = now.astimezone(tz)
    if day < local.date(): return target
    if day > local.date(): return 0
    if bootstrap: return target
    # Reach the target at the final scheduled run, retaining room for later news.
    hour = local.hour + local.minute / 60
    fraction = min(1, max(0, (hour - 8) / 12))
    return min(cap, max(10, round(target * fraction)))


def parse_feed(content, name, weight):
    root = ET.fromstring(content)
    out = []
    for elem in root.iter():
        if elem.tag.split('}')[-1] not in ('item', 'entry'): continue
        title = field(elem, {'title'})
        link = field(elem, {'link'})
        if not link:
            for c in elem:
                if c.tag.split('}')[-1] == 'link' and c.attrib.get('href') and c.attrib.get('rel', 'alternate') == 'alternate':
                    link = c.attrib['href']; break
        published = date_parse(field(elem, {'pubDate','published','updated','date'}))
        summary = field(elem, {'description','summary','content'})
        if title and link and link.startswith(('https://','http://')) and published:
            out.append({'title':title,'link':link,'date':published,'summary':re.sub('<[^>]*>',' ',summary)[:350], 'sources':[name], 'weight':weight, 'image':feed_image(elem, link), 'categories':[c.text or c.get('term', '') for c in elem if c.tag.split('}')[-1] == 'category']})
    return out


def fetch(source):
    req = urllib.request.Request(source['url'],headers={'User-Agent':'SportsRSSCurator/0.2 (personal RSS reader)', 'Accept':'application/rss+xml,application/atom+xml,application/xml,text/xml,*/*'})
    with urllib.request.urlopen(req, timeout=18) as r: return parse_feed(r.read(4_000_000),source['name'],source['weight'])


def general_score(item):
    profile = CONFIG.get('profile')
    title = normalize(item['title'])
    value = 2 * item['weight'] + min(4, len(set(item['sources'])) - 1) * 3.5
    important = {
        'news': ['σεισμ', 'πυρκαγ', 'εκλογ', 'κυβερνη', 'νομοσχεδ', 'οικονομ', 'πολεμ', 'απεργ', 'δικασ', 'επιτοκι', 'φορολ'],
        'apple': ['security', 'ασφαλει', 'vulnerab', 'ευπαθει', 'releases', 'διαθεσιμ', 'ανακοιν', 'launch', 'update', 'ενημερωσ'],
    }
    value += sum(1.2 for term in important.get(profile, []) if normalize(term) in title)
    # Transparent low-signal selection; does not claim to fact-check publishers.
    low = ['ζωδια', 'horoscope', 'κουιζ', 'quiz', 'δεν θα πιστευ', 'θα παθετε', 'σοκαρει', 'betting', 'στοιχηματικ']
    value -= sum(5 for term in low if normalize(term) in title)
    if profile == 'apple' and any(term in title for term in ['deal', 'discount', 'εκπτωση', 'προσφορα']):
        value -= 1.5
    return round(value, 3)


def is_independent(item):
    text = normalize(item['title'] + ' ' + ' '.join(item.get('categories', [])))
    return any(re.search(r'\b' + re.escape(normalize(term)) + r'\b', text) for term in ['review', 'reviews', 'hands on', 'how to', 'guide', 'οδηγοσ', 'δοκιμη', 'συγκριση', 'comparison'])


def apple_signature(title):
    text = normalize(title)
    products = {p for p in ['iphone', 'ipad', 'macbook', 'imac', 'macos', 'ios', 'ipados', 'watchos', 'tvos', 'visionos', 'airpods', 'homepod'] if re.search(r'\b' + p + r'\b', text)}
    if 'apple watch' in text:
        products.add('apple watch')
    # Models such as Pro/Air must not collapse into the base model.
    variants = {v for v in ['pro', 'max', 'air', 'mini', 'ultra'] if re.search(r'\b' + v + r'\b', text)}
    numbers = set(re.findall(r'\d+(?:\.\d+)*', title))
    action = None
    for kind, terms in [
        ('security', ['security', 'vulnerability', 'ευπαθει', 'κενο ασφαλει']),
        ('beta', ['beta', 'μπετα']),
        ('rumor', ['rumor', 'rumour', 'leak', 'φημ', 'διαρρο']),
        ('release', ['releases', 'released', 'available', 'launch', 'announces', 'arrives in stores', 'διαθεσιμ', 'κυκλοφορ', 'ανακοιν', 'ενημερωσ', 'update']),
    ]:
        if any(term in text for term in terms):
            action = kind
            break
    # Only merge translations when concrete product/version/action anchors agree.
    if not products or not numbers or action is None:
        return None
    return (tuple(sorted(products)), tuple(sorted(variants)), tuple(sorted(numbers)), action)


def score(item):
    if CONFIG.get('profile', 'sports') != 'sports':
        return general_score(item)
    title = normalize(item['title'])
    total = item['weight'] * 2
    total += min(4, len(item['sources']) - 1) * 3.5
    total += sum(2.4 for term in HIGH if normalize(term) in title)
    total -= sum(1.8 for term in LOW if normalize(term) in title)
    if any(normalize(t) in title for t in OTHER_SPORT): total -= 0.7
    return round(total, 3)


def is_opinion(item):
    """Conservative metadata/title hints; do not merge identified commentary."""
    path = urlsplit(item['link']).path.lower()
    sections = ('blog', 'blogs', 'opinion', 'opinions', 'columns', 'apopseis', 'gnomes', 'arthrografia', 'analysis')
    if any(part in sections for part in path.split('/')):
        return True
    categories = normalize(' '.join(item.get('categories', [])))
    if any(normalize(term) in categories for term in ('απόψεις', 'γνώμη', 'αρθρογραφία', 'ανάλυση', 'blogs', 'opinion', 'editorial')):
        return True
    title = normalize(item['title'])
    return any(title.startswith(normalize(term) + ' ') for term in ('Γνώμη', 'Άποψη', 'Ανάλυση', 'Opinion', 'Editorial'))


def representative_rank(item):
    if CONFIG.get('profile', 'sports') != 'sports':
        return (bool(item.get('image')), item['weight'], len(item.get('summary', '')))
    host = urlsplit(item['link']).hostname or ''
    alternative = host in ('gazzetta.gr', 'www.gazzetta.gr', 'sport-fm.gr', 'www.sport-fm.gr')
    return (bool(alternative and item.get('image')), item['weight'], bool(item.get('image')))


def translated_tokens(title):
    """Small bilingual vocabulary for conservative Apple headline comparison."""
    mappings = {
        'release': ('release', 'κυκλοφορ', 'διαθεσιμ', 'ανακοιν', 'available', 'launch', 'arrives'),
        'acquire': ('acquir', 'buys', 'εξαγορ'),
        'display': ('display', 'screen', 'οθον'),
        'crack': ('crack', 'ρωγμ', 'ραγισ'),
        'issue': ('issue', 'problem', 'προβλημ'),
        'confirm': ('confirm', 'παραδεχ', 'επιβεβαι'),
        'security': ('security', 'ασφαλει'),
        'update': ('update', 'ενημερωσ'),
        'touch': ('touch', 'αφη'),
    }
    stops = {'apple', 'the', 'a', 'an', 'in', 'on', 'to', 'for', 'with', 'and', 'of', 'its', 'new', 'more', 'this', 'these', 'from', 'το', 'τησ', 'την', 'του', 'τα', 'με', 'και', 'στο', 'στην', 'για', 'νεο', 'νεα', 'η', 'ο', 'οι', 'που'}
    tokens = set()
    for token in normalize(title).split():
        if token in stops:
            continue
        canonical = next((name for name, roots in mappings.items() if any(token.startswith(root) for root in roots)), token)
        tokens.add(canonical)
    return tokens


def translated_match(a, b):
    ta, tb = translated_tokens(a['title']), translated_tokens(b['title'])
    anchors = ta & tb
    products = {'iphone', 'ipad', 'ios', 'ipados', 'macos', 'macbook', 'homepod', 'airpods', 'watchos'}
    events = {'acquire', 'crack', 'security', 'release'}
    # Require an event, a concrete product/name, and substantial title overlap.
    named = {t for t in anchors if t.isascii() and t.isalpha() and len(t) >= 4 and t not in {'apple', 'display', 'issue', 'confirm', 'release', 'security', 'update', 'acquire', 'crack', 'coming', 'week', 'next'}}
    return bool(anchors & events) and bool(anchors & products or named) and len(anchors) >= 4 and len(anchors) / max(1, len(ta | tb)) >= .5


def same_story(a, b):
    if a['link'] == b['link']:
        return True
    if abs((a['date'] - b['date']).total_seconds()) > 36 * 3600:
        return False
    if is_opinion(a) or is_opinion(b):
        return False
    # Independent reviews/tutorials are distinct work, not duplicate news.
    if CONFIG.get('profile') == 'apple' and (is_independent(a) or is_independent(b)):
        return False
    if CONFIG.get('profile') == 'apple':
        sig_a, sig_b = apple_signature(a['title']), apple_signature(b['title'])
        if sig_a and sig_b:
            return sig_a == sig_b
    ta, tb = title_tokens(a['title']), title_tokens(b['title'])
    # Conflicting numeric details often indicate different events or versions.
    na, nb = set(re.findall(r'\d+', a['title'])), set(re.findall(r'\d+', b['title']))
    if na and nb and na != nb:
        return False
    if CONFIG.get('profile') == 'apple' and translated_match(a, b):
        return True
    overlap = len(ta & tb)
    jacc = overlap / max(1, len(ta | tb))
    ratio = difflib.SequenceMatcher(None, normalize(a['title']), normalize(b['title'])).ratio()
    return (jacc >= .58 and overlap >= 3) or ratio >= .78


def cluster(items):
    groups = []
    for item in sorted(items, key=lambda x: x['date'], reverse=True):
        match = next((g for g in groups if same_story(item, g)), None)
        if match is None:
            groups.append({**item, 'sources': list(item['sources'])})
            continue
        # Count corroboration once per publisher, regardless of feed count.
        sources = list(dict.fromkeys(match['sources'] + item['sources']))
        if not is_opinion(item) and representative_rank(item) > representative_rank(match):
            match.update({k: item.get(k, '') for k in ['title', 'link', 'weight', 'summary', 'image', 'date', 'categories']})
        match['sources'] = sources
    return groups


def xml_output(records, now):
    # Plain RSS 2.0: one publication date, canonical links and unchanged GUIDs.
    rss = ET.Element('rss', version='2.0')
    channel = ET.SubElement(rss, 'channel')
    for tag, value in [
        ('title', CONFIG['feed_title']),
        ('link', 'https://konspir21.github.io/sports-rss-curator/'),
        ('description', 'Selected sports headlines. Original publishers retain their content.'),
        ('language', 'el'),
        ('lastBuildDate', email.utils.format_datetime(now)),
    ]:
        ET.SubElement(channel, tag).text = value
    for record in sorted(records, key=lambda r: date_parse(r.get('selected_at')) or r['date'], reverse=True):
        item = ET.SubElement(channel, 'item')
        ET.SubElement(item, 'title').text = record['title']
        ET.SubElement(item, 'link').text = record['link']
        ET.SubElement(item, 'guid', isPermaLink='false').text = record['id']
        published = date_parse(record.get('selected_at')) or record['date']
        ET.SubElement(item, 'pubDate').text = email.utils.format_datetime(published)
        body = '<p>' + html.escape('Πηγές: ' + ', '.join(record['sources']) + '. ' + record['summary']) + '</p>'
        if record.get('image'):
            body = '<p><img src="' + html.escape(record['image'], quote=True) + '" alt="" /></p>' + body
        ET.SubElement(item, 'description').text = body
    OUTPUT.parent.mkdir(exist_ok=True)
    ET.indent(rss)
    ET.ElementTree(rss).write(OUTPUT, encoding='utf-8', xml_declaration=True)


def run(now=None, source_items=None):
    now=now or dt.datetime.now(UTC)
    tz=ZoneInfo(CONFIG['timezone'])
    try: state=json.loads(STATE_PATH.read_text(encoding='utf-8'))
    except FileNotFoundError: state={'selected':[]}
    except json.JSONDecodeError as exc:
        raise RuntimeError(f'Invalid state file {STATE_PATH}; leaving feed and state untouched') from exc
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
        if g['id'] not in existing_ids and not any(same_story(g, old) for old in previous):
            new.append(g)
            existing_ids.add(g['id'])
    new = [g for g in new if score(g) >= CONFIG.get('min_score', float('-inf'))]
    new.sort(key=lambda x:(score(x),x['date']),reverse=True)
    per_day=defaultdict(int)
    for p in previous: per_day[p['date'].astimezone(tz).date()]+=1
    bootstrap = not state.get('v02_initialized', False)
    selected=[]
    for g in new:
        day=g['date'].astimezone(tz).date()
        if per_day[day] >= admission_limit(day, now, tz, bootstrap): continue
        g['selected_at'] = now.isoformat()
        selected.append(g); per_day[day]+=1
    # Recover late Gazzetta admissions once; retain all existing article identities.
    if not state.get('curated_dates_v1'):
        for record in previous:
            if urlsplit(record['link']).hostname in ('gazzetta.gr', 'www.gazzetta.gr'):
                record.setdefault('selected_at', now.isoformat())
    combined=previous+selected
    display_cut=now-dt.timedelta(days=CONFIG['display_days'])
    combined=[p for p in combined if p['date']>=display_cut]
    combined.sort(key=lambda x:x['date'],reverse=True)
    # Reuse feed images for older selected articles without changing IDs or links.
    images = {x['link']: x.get('image') for x in incoming if x.get('image')}
    for record in combined:
        if not record.get('image') and images.get(record['link']): record['image'] = images[record['link']]
    if source_items is None: enrich_images(combined)
    xml_output(combined,now)
    state['v02_initialized'] = True
    state['curated_dates_v1'] = True
    state['selected']=[{**p,'date':p['date'].isoformat()} for p in combined]
    STATE_PATH.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Accepted {len(selected)} new, total display {len(combined)}. Source fetches successful {ok}.')
    return combined

def activate_profile(name):
    global CONFIG, STATE_PATH, OUTPUT
    CONFIG = json.loads((ROOT / ('config.json' if name == 'sports' else f'config-{name}.json')).read_text(encoding='utf-8'))
    STATE_PATH = ROOT / ('state.json' if name == 'sports' else f'state-{name}.json')
    OUTPUT = ROOT / 'docs' / ('feed.xml' if name == 'sports' else f'{name}.xml')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--profile', choices=['sports', 'news', 'apple'], default='sports')
    activate_profile(parser.parse_args().profile)
    run()





