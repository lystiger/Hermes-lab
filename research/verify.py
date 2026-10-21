"""source_check: confirm a quote really appears on its source page.

Hosts are the release registries (research.watch) plus the design-source hosts Lystiger lists in
config/research_hosts.json. Page text is read only to look for the quote. Nothing in the page is
followed or acted on, whatever it says.
"""

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

from research.watch import ALLOWED_HOSTS
from security.urls import checked_urlopen

HOSTS_FILE = Path(__file__).resolve().parent.parent / "config" / "research_hosts.json"
MAX_BYTES = 512 * 1024
USER_AGENT = "hermes-researcher/0.1 (source check)"


class _Text(HTMLParser):
    SKIP = {"script", "style", "noscript", "template"}

    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip_depth += 1

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip_depth:
            self.skip_depth -= 1

    def handle_data(self, data):
        if not self.skip_depth:
            self.parts.append(data)


def html_to_text(html):
    parser = _Text()
    parser.feed(html)
    return re.sub(r"\s+", " ", " ".join(parser.parts)).strip()


def normalize(text):
    return re.sub(r"\s+", " ", text).strip().lower()


def allowed_hosts():
    extra = json.loads(HOSTS_FILE.read_text()) if HOSTS_FILE.exists() else []
    return set(ALLOWED_HOSTS) | set(extra)


def verify_quote(url, quote, fetch=None, hosts=None):
    """VERIFIED when the quote is on the page, NOT_FOUND when it is not, UNPROVEN when the page cannot be read."""
    host = urllib.parse.urlsplit(url).hostname or ""
    if host not in (hosts if hosts is not None else allowed_hosts()):
        return {"url": url, "status": "UNPROVEN", "reason": f"host {host!r} is not on the research allowlist"}
    if not quote or not quote.strip():
        return {"url": url, "status": "UNPROVEN", "reason": "no quote given"}
    try:
        body = (fetch or _fetch)(url)
    except Exception as exc:  # noqa: BLE001 - any read failure is reported, never hidden
        return {"url": url, "status": "UNPROVEN", "reason": f"could not read the page: {exc}"[:200]}
    text = html_to_text(body) if "<" in body[:500] else body
    found = normalize(quote) in normalize(text)
    return {"url": url, "status": "VERIFIED" if found else "NOT_FOUND"}


def _fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with checked_urlopen(request, timeout=15) as response:
        return response.read(MAX_BYTES).decode("utf-8", errors="replace")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Check that a quote appears on its source page")
    parser.add_argument("--url", required=True)
    parser.add_argument("--quote", required=True)
    args = parser.parse_args(argv)
    result = verify_quote(args.url, args.quote)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "VERIFIED" else 1


if __name__ == "__main__":
    sys.exit(main())
