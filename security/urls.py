"""Opening URLs only over http and https.

urllib.request.urlopen also accepts file: and other schemes. Every URL this stack opens comes from
operator configuration, but the scheme is still checked here so a bad value fails loudly.
"""

import urllib.parse
import urllib.request


def checked_urlopen(target, timeout):
    """Open a URL string or urllib Request, refusing any scheme other than http or https."""
    url = target.full_url if isinstance(target, urllib.request.Request) else target
    scheme = urllib.parse.urlsplit(url).scheme.lower()
    if scheme not in ("http", "https"):
        raise ValueError(f"refusing to open a URL with scheme {scheme!r}")
    return urllib.request.urlopen(target, timeout=timeout)  # nosec B310 - scheme checked above
