MIRROR_CATALOG = [
    {"label": "gh-proxy.org", "url": "https://gh-proxy.org/"},
    {"label": "ghproxy.cc", "url": "https://ghproxy.cc/"},
    {"label": "ghproxy.net", "url": "https://ghproxy.net/"},
    {"label": "gh.ddlc.top", "url": "https://gh.ddlc.top/"},
    {"label": "ghfast.top", "url": "https://ghfast.top/"},
    {"label": "cf.ghproxy.cc", "url": "https://cf.ghproxy.cc/"},
]


DEFAULT_MIRROR_PREFIX = MIRROR_CATALOG[0]["url"]


def get_mirror_urls():
    return [item["url"] for item in MIRROR_CATALOG]
