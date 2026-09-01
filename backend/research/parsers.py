from __future__ import annotations

from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlsplit

from backend.research.network import safe_url


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text = []
        self.title = []
        self.in_title = False
        self.hidden = []
        self.published_at = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {"script", "style", "noscript", "svg", "nav", "footer", "form", "iframe"}:
            self.hidden.append(tag)
        if tag == "title":
            self.in_title = True
        if tag == "meta" and (attrs.get("property") or attrs.get("name")) in {"article:published_time", "datePublished", "date"}:
            try:
                self.published_at = datetime.fromisoformat(attrs.get("content", "").replace("Z", "+00:00")).isoformat()
            except ValueError:
                pass

    def handle_endtag(self, tag):
        if tag in self.hidden:
            self.hidden = self.hidden[:self.hidden.index(tag)]
        if tag == "title":
            self.in_title = False
        if tag in {"p", "div", "li", "h1", "h2", "h3", "tr", "section"}:
            self.text.append("\n")

    def handle_data(self, data):
        if self.hidden:
            return
        if self.in_title:
            self.title.append(data)
        elif data.strip():
            self.text.append(data.strip() + " ")

    def result(self):
        return " ".join(self.title).strip()[:240], "\n".join(" ".join(line.split()) for line in "".join(self.text).splitlines() if line.strip()), self.published_at


class SearchParser(HTMLParser):
    """Read plain DuckDuckGo result links, never execute returned HTML."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.results = []
        self.current = None
        self.anchor_depth = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and {"result__a", "result-link"}.intersection(attrs.get("class", "").split()):
            href = attrs.get("href", "")
            if href.startswith("//"):
                href = "https:" + href
            redirect = urlsplit(href)
            if redirect.hostname in {"duckduckgo.com", "html.duckduckgo.com", "lite.duckduckgo.com"}:
                href = parse_qs(redirect.query).get("uddg", [""])[0]
            try:
                url, _ = safe_url(href)
            except ValueError:
                self.current = None
                return
            self.current = {"url": url, "title": ""}
            self.anchor_depth = 1
        elif self.current:
            self.anchor_depth += 1

    def handle_data(self, data):
        if self.current:
            self.current["title"] += data

    def handle_endtag(self, tag):
        if self.current:
            self.anchor_depth -= 1
            if tag == "a" or self.anchor_depth <= 0:
                self.current["title"] = " ".join(self.current["title"].split())[:240]
                if self.current["title"] and not any(item["url"] == self.current["url"] for item in self.results):
                    self.results.append(self.current)
                self.current = None
