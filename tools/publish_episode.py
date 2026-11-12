#!/usr/bin/env python3
"""Add a briefing MP3 to the podcast feed and rebuild feed.xml.

Usage (from the repo root):
  python3 tools/publish_episode.py <briefing...mp3> [--script <briefing...txt>] [--summary "text"]

File names follow the hpc-hpai-briefing skill:
  briefing.<YYYY-MM-DD>.mp3                      -> weekly briefing (Monday)
  briefing.<YYYY-MM-DD>.addendum.<YYYY-MM-DD>.mp3 -> daily update
Re-publishing the same file name replaces that episode. Only the newest
KEEP episodes stay in the repo and feed (older MP3s are removed).
Then: git add -A && git commit && git push.
"""
import argparse, json, os, re, shutil, subprocess, sys
from datetime import datetime
from email.utils import format_datetime
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

BASE_URL = "https://n722pc.github.io/hpc-briefing"
SHOW_TITLE = "HPC & HPAI Briefing"
SHOW_DESC = ("Private daily briefing on high performance computing and high performance AI: "
             "systems, accelerators, interconnects, policy and industry news. Hosts Ava and Ryan.")
AUTHOR = "Michael Stevens"
KEEP = 30
TZ = ZoneInfo("America/Chicago")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EP_DIR = os.path.join(ROOT, "episodes")
INDEX = os.path.join(EP_DIR, "index.json")

NAME_RE = re.compile(r"^briefing\.(\d{4}-\d{2}-\d{2})(?:\.addendum\.(\d{4}-\d{2}-\d{2}))?\.mp3$")


def duration_seconds(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", path], capture_output=True, text=True, check=True)
    return int(round(float(out.stdout.strip())))


def summary_from_script(path, limit=600):
    lines = []
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = re.sub(r"^[AR]\|", "", raw.strip())
            if line:
                lines.append(line)
    body = " ".join(lines[2:6]) if len(lines) > 3 else " ".join(lines)
    return body[:limit].rsplit(" ", 1)[0] + "…" if len(body) > limit else body


def fmt_dur(s):
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def build_feed(episodes):
    now = format_datetime(datetime.now(TZ))
    items = []
    for e in episodes:
        url = f"{BASE_URL}/episodes/{e['file']}"
        items.append(f"""    <item>
      <title>{escape(e['title'])}</title>
      <description>{escape(e['summary'])}</description>
      <itunes:summary>{escape(e['summary'])}</itunes:summary>
      <pubDate>{e['pubDate']}</pubDate>
      <guid isPermaLink="false">{escape(e['file'])}</guid>
      <enclosure url="{escape(url)}" length="{e['bytes']}" type="audio/mpeg"/>
      <itunes:duration>{fmt_dur(e['seconds'])}</itunes:duration>
      <itunes:episodeType>full</itunes:episodeType>
      <itunes:explicit>false</itunes:explicit>
    </item>""")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{escape(SHOW_TITLE)}</title>
    <link>{BASE_URL}/</link>
    <atom:link href="{BASE_URL}/feed.xml" rel="self" type="application/rss+xml"/>
    <description>{escape(SHOW_DESC)}</description>
    <language>en-us</language>
    <lastBuildDate>{now}</lastBuildDate>
    <itunes:author>{escape(AUTHOR)}</itunes:author>
    <itunes:summary>{escape(SHOW_DESC)}</itunes:summary>
    <itunes:image href="{BASE_URL}/cover.png"/>
    <image><url>{BASE_URL}/cover.png</url><title>{escape(SHOW_TITLE)}</title><link>{BASE_URL}/</link></image>
    <itunes:category text="Technology"/>
    <itunes:explicit>false</itunes:explicit>
    <itunes:block>Yes</itunes:block>
    <itunes:type>episodic</itunes:type>
{chr(10).join(items)}
  </channel>
</rss>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mp3")
    ap.add_argument("--script")
    ap.add_argument("--summary")
    a = ap.parse_args()

    name = os.path.basename(a.mp3)
    m = NAME_RE.match(name)
    if not m:
        sys.exit(f"Unexpected file name: {name}")
    week, day = m.group(1), m.group(2)
    date = datetime.strptime(day or week, "%Y-%m-%d").replace(hour=5, minute=30, tzinfo=TZ)
    pretty = date.strftime("%a %b ") + str(date.day) + date.strftime(", %Y")
    title = f"Daily update — {pretty}" if day else f"Weekly briefing — {pretty}"

    summary = a.summary or (summary_from_script(a.script) if a.script else title)

    os.makedirs(EP_DIR, exist_ok=True)
    dest = os.path.join(EP_DIR, name)
    if os.path.abspath(a.mp3) != os.path.abspath(dest):
        shutil.copyfile(a.mp3, dest)

    index = json.load(open(INDEX)) if os.path.exists(INDEX) else []
    index = [e for e in index if e["file"] != name]
    index.append({
        "file": name, "title": title, "summary": summary,
        "sortKey": date.isoformat(), "pubDate": format_datetime(date),
        "bytes": os.path.getsize(dest), "seconds": duration_seconds(dest),
    })
    index.sort(key=lambda e: e["sortKey"], reverse=True)
    keep, drop = index[:KEEP], index[KEEP:]
    for e in drop:
        p = os.path.join(EP_DIR, e["file"])
        if os.path.exists(p):
            os.remove(p)

    with open(INDEX, "w") as f:
        json.dump(keep, f, indent=1)
    with open(os.path.join(ROOT, "feed.xml"), "w", encoding="utf-8") as f:
        f.write(build_feed(keep))
    print(json.dumps({"published": name, "title": title, "episodes": len(keep),
                      "removed": [e["file"] for e in drop],
                      "feed": f"{BASE_URL}/feed.xml"}))


if __name__ == "__main__":
    main()
