# Sports RSS Curator — Unread Cloud

A small, free, **non-AI** RSS curator built for Athletiko, Gazzetta Football, and Sport-FM Football.

## Version 0.2

- Downloads the three original RSS feeds (source URLs taken from an Unread Cloud OPML export).
- Keeps articles published within the previous 36 hours; no historical flood.
- Groups similar titles when likely about the same story (approximate matching).
- Scores articles using explicit Greek/English keywords for important sports news, downranking low-signal items.
- Includes football and major stories from other sports present in the sources.
- Publishes the original article URL, headline, publisher names, and a short source-provided description. No unauthorized full-text republishing.
- Targets **40 per publication day** in Athens time, with a hard ceiling of **50**. The first v0.2 run fills available days up to the target; subsequent runs pace today’s admissions (10 in the morning, about 14 at noon, 28 at 16:17, 40 at 20:17). Delayed runs catch up. No fixed 12-item execution limit. Counts depend on dated, distinct articles actually available in the source feeds.
- Remembers already selected entries in `state.json`; exposes up to three days of selected articles.
- Preserves the RSS XML and state if all sources fail.

**Limitations:** Keyword scoring is not semantic AI and may miss a major event or admit trivial news. Deduplication is approximate. RSS items with no publication date are skipped. The source feeds may be inaccessible or change format. GitHub Actions schedules can be delayed or disabled due to inactivity. The selected count depends on source activity. GitHub Pages, if enabled, makes the resulting RSS public. No data from your Unread account is used beyond the three public feed URLs.

## Publish on GitHub (web interface)

1. Create a **public** GitHub repository named `sports-rss-curator` (prefer an empty repository).
2. Upload the contents of this folder to the repository, **including `.github/workflows/curate.yml`**. The workflow must be in the default `main` branch.
3. In **Settings → Actions → General**, ensure workflows have permission to read/write repository contents if your repository defaults do not allow it; the workflow explicitly requests `contents: write`.
4. In **Settings → Pages → Build and deployment**, choose **Deploy from a branch**, branch `main`, folder `/docs`. Save.
5. Open **Actions → Curate sports headlines → Run workflow** for the initial update.
6. Visit `https://YOUR_GITHUB_USERNAME.github.io/sports-rss-curator/feed.xml` and check that it displays XML.
7. In Unread, add a subscription using that URL. Do **not** delete existing sports sources until the output has been checked for several days.

If your default branch or repository name is different, adjust the Pages settings and URL. GitHub Pages propagation can be delayed.

## Schedule

Every ten minutes, at **:07, :17, :27, :37, :47 and :57**, throughout the day. GitHub does not guarantee exact execution times. On public repositories GitHub may disable schedules after 60 days without activity.

## Adjust selection

- `config.json` → `sources`: change weights or add feeds (only public RSS URLs).
- `target_per_day`: operational daily admission target (default 40).
- `hard_cap_per_day`: maximum admissions on one local date.
- `curator.py` → `HIGH`, `LOW`, `OTHER_SPORT`: classification signals.
- Initial v0.2 catch-up applies once, including existing installations. It does not delete history or change existing GUIDs. A first batch can include two publication dates; it is not a promise of 30–50 immediately or a measured daily rate.
- `state.json`: persistent selection history, updated by GitHub Actions. **Do not delete if you want stable read/unread behavior**.

## Test locally

```
python -m unittest discover -s tests -v
python curator.py
```

Requires Python 3.12+, standard library only. Running `curator.py` requires external network access and writes `state.json` + `docs/feed.xml`. Feed validity and source availability must be verified after deployment.

## Privacy, security, costs

- No password, account access, OpenAI API key, or paid plan is needed.
- GitHub Pages requires a publicly accessible feed; assume repository content is public too.
- Public GitHub repositories get standard GitHub Actions minutes free under current GitHub billing rules, subject to policy changes.
- Avoid adding credentials to config files or commits.


## Images and Unread verification

v0.2 reads Media RSS, image enclosures, and images in feed HTML. Missing images fall back to the original article’s Open Graph/Twitter image metadata, with bounded requests and six workers. Existing selected records are enriched in place, keeping their links, GUIDs, dates, and state. Images are emitted once as an HTML image in the RSS description. Failed image lookups leave readable articles intact and retry later. Publisher image URLs are used directly.

Keep Unread’s **Webpage Text** setting: it continues extracting full text using the original article URL. RSS image metadata can help thumbnails/feed text, but cannot force Unread’s independent webpage extractor to retain an image. No `content:encoded` full-text field is added. Refresh the subscription, check a newly admitted article’s thumbnail and Webpage Text, then temporarily inspect Feed Text to distinguish RSS image delivery from webpage extraction. Existing cached articles may not refresh in place. Do not delete/re-add the subscription or reset state to test this. Actual Unread rendering must be confirmed in the app.

Run `python -m unittest discover -s tests -v` before deploying. The concurrency group and state commit flow are retained. Profiles run in separate processes concurrently, and each profile fetches up to six sources concurrently. Source results are consumed in configuration order to preserve deterministic selection. A failed source does not block healthy sources; all-source failure preserves the existing feed and state.

The ten-minute schedule is a request to GitHub, not a delivery guarantee. GitHub may delay or drop scheduled runs; publisher RSS update times, Pages caching and Unread polling add independent delays. No external scheduling service or account is required. Profile durations are logged in Actions.
