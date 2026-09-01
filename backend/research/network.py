from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from urllib.parse import parse_qsl, urljoin, urlsplit, urlunsplit

import httpx

from backend.tools.contracts import ToolError

MAX_RESPONSE_BYTES = 2_000_000
SENSITIVE = re.compile(r"(?:sk-[A-Za-z0-9_-]{12,}|Bearer\s+\S+|(?:api[_-]?key|password|secret|token|authorization)\s*[:=]\s*\S+)", re.I)


def public_ip(value: str) -> bool:
    address = ipaddress.ip_address(value)
    return address.is_global and not address.is_multicast and not address.is_reserved and not getattr(address, "ipv4_mapped", None)


def domain(value: str) -> str:
    value = value.strip().lower()
    if any(char in value for char in "/:@*\\%?#") or value.endswith("."):
        raise ValueError("Укажите точное имя домена без URL, порта и звёздочек")
    try:
        value = value.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValueError("Некорректное имя домена") from exc
    if len(value) > 253 or not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", value):
        raise ValueError("Некорректное имя домена")
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        if "." not in value or any(not label or len(label) > 63 or label.startswith('-') or label.endswith('-') for label in value.split('.')):
            raise ValueError("Нужен публичный домен, например docs.python.org")
        if value.endswith((".localhost", ".local", ".internal", ".home", ".test")):
            raise ValueError("Локальные домены недоступны research-инструментам")
    else:
        if not public_ip(str(address)):
            raise ValueError("Локальные и служебные адреса запрещены")
    return value


def safe_url(value: str) -> tuple[str, str]:
    if len(value) > 2048 or re.search(r"[\s\x00-\x1f\x7f\\]", value):
        raise ValueError("URL слишком длинный или содержит недопустимые символы")
    parsed = urlsplit(value)
    if parsed.scheme != "https" or parsed.username is not None or parsed.password is not None or parsed.port not in (None, 443):
        raise ValueError("Разрешены только публичные HTTPS URL без пароля и нестандартного порта")
    host = domain(parsed.hostname or "")
    if SENSITIVE.search(value) or any(re.search(r"token|secret|password|api.?key|signature|authorization", key, re.I) for key, _ in parse_qsl(parsed.query)):
        raise ValueError("URL содержит возможный секрет; используйте публичную ссылку")
    return urlunsplit(("https", host, parsed.path or "/", parsed.query, "")), host


def public_query(value: str) -> str:
    if "\n" in value or "\r" in value or SENSITIVE.search(value) or re.search(r"[A-Z]:[\\/]|/Users/|/home/|[\w.+-]+@[\w.-]+\.[a-z]{2,}", value, re.I):
        raise ValueError("Нужны публичные ключевые слова без переписки, путей, email и секретов")
    value = " ".join(value.split())
    if not 2 <= len(value) <= 240 or len(value.split()) > 32:
        raise ValueError("Поисковый запрос: 2–240 знаков и не более 32 слов")
    return value


async def resolve_public(host: str) -> list[str]:
    try:
        rows = await asyncio.wait_for(asyncio.get_running_loop().getaddrinfo(host, 443, type=socket.SOCK_STREAM), timeout=5)
    except (OSError, TimeoutError) as exc:
        raise ToolError("web_dns", "Не удалось разрешить публичный адрес сайта") from exc
    addresses = sorted({row[4][0] for row in rows})
    if not addresses or not all(public_ip(address) for address in addresses):
        raise ToolError("web_private_address", "Домен указывает на локальный или служебный адрес; запрос заблокирован")
    return addresses


class SafeWebClient:
    """Pin a verified public IP while retaining TLS SNI/Host; recheck every redirect.

    No ambient proxies, cookies, credentials, automatic redirects or decompression.
    A transport/resolver may be injected by tests only; production uses TLS validation.
    """

    def __init__(self, *, transport=None, resolver=resolve_public):
        self.transport = transport
        self.resolver = resolver

    async def get(self, url: str, *, allowed: set[str], enabled, on_event=None) -> tuple[str, bytes, str]:
        for hop in range(5):
            try:
                url, host = safe_url(url)
            except ValueError as exc:
                raise ToolError("web_invalid_url", str(exc)) from exc
            if not enabled():
                raise ToolError("internet_disabled", "Интернет выключен в настройках этого чата")
            if host not in allowed:
                raise ToolError("web_domain_not_allowed", "Переадресация на другой домен требует отдельного разрешения", details={"url": url, "domain": host})
            addresses = await self.resolver(host)
            if not addresses or not all(public_ip(ip) for ip in addresses):
                raise ToolError("web_private_address", "Непубличный адрес заблокирован")
            if not enabled():
                raise ToolError("internet_disabled", "Интернет выключен")
            if on_event:
                await on_event("research.requested", {"url": url, "domain": host, "method": "GET", "redirect": hop})
            # URL connects to the checked numeric IP, so a later DNS rebinding cannot
            # send this connection to localhost. TLS still verifies the original host.
            target = httpx.URL(url).copy_with(host=addresses[0])
            try:
                async with httpx.AsyncClient(transport=self.transport, trust_env=False, timeout=15, follow_redirects=False) as client:
                    async with client.stream("GET", target, headers={"Host": host, "User-Agent": "Symphony/0.7 (+local research)", "Accept": "text/html,text/plain,application/json", "Accept-Encoding": "identity"}, extensions={"sni_hostname": host}) as response:
                        if response.status_code in (301, 302, 303, 307, 308):
                            location = response.headers.get("location")
                            if not location:
                                raise ToolError("web_redirect", "Пустая переадресация")
                            url = urljoin(url, location)
                            continue
                        if response.status_code != 200:
                            raise ToolError("web_http", f"Сайт вернул HTTP {response.status_code}; подтверждения не получено")
                        if response.headers.get("content-encoding", "identity").lower() != "identity":
                            raise ToolError("web_encoding", "Сжатый ответ отклонён для защиты от decompression bomb")
                        mime = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                        if mime not in {"text/html", "application/xhtml+xml", "text/plain", "application/json"}:
                            raise ToolError("web_content_type", "Research читает HTML/текст, а не бинарные загрузки")
                        data = bytearray()
                        async for chunk in response.aiter_raw():
                            if not enabled():
                                raise ToolError("internet_disabled", "Интернет выключен")
                            if len(data) + len(chunk) > MAX_RESPONSE_BYTES:
                                raise ToolError("web_size_limit", "Страница превышает лимит 2 MB")
                            data.extend(chunk)
                        if on_event:
                            await on_event("research.received", {"url": url, "bytes": len(data), "status": 200})
                        return url, bytes(data), mime
            except httpx.HTTPError as exc:
                # Never echo request headers, proxy credentials or connection details.
                raise ToolError("web_connection", "Не удалось безопасно прочитать сайт по HTTPS") from exc
        raise ToolError("web_redirect_limit", "Слишком много переадресаций")
