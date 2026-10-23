import requests


class FakeResponse:
    def __init__(self, text):
        self.text = text
        self.encoding = None

    def raise_for_status(self):
        pass


class FakeSession:
    """session.get(...) answers come from handler(params) -> html, or raise if handler returns an Exception."""

    def __init__(self, handler):
        self.handler = handler
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append(params)
        out = self.handler(params or {})
        if isinstance(out, Exception):
            raise out
        return FakeResponse(out)


def board(rows, headers=("Sija", "Pelaaja", "Kalalaji", "Järvi", "Päiväys", "Kalan paino"), links=()):
    """HTML like the site's leaderboard. rows: lists of cell texts; a row starting with '*' is highlighted."""
    head = "".join(f"<th>{h}</th>" for h in headers)
    body = ""
    for r in rows:
        hl = isinstance(r[0], str) and r[0].startswith("*")
        cells = [r[0].lstrip("*")] + list(r[1:]) if hl else list(r)
        cls = ' class="select"' if hl else ""
        body += "<tr>" + "".join(f"<td{cls}>{c}</td>" for c in cells) + "</tr>"
    a = "".join(f'<a href="?row={o}">p</a>' for o in links)
    return f'<table id="myTable"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>{a}'


ConnectionFailure = requests.ConnectionError
