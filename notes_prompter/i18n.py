"""System-language selection and shared, explicit UI message catalogs.

Notes, file names, preset names and other user content never pass through this layer.
"""
from __future__ import annotations
import ctypes
import json
import locale
import re
import sys
from functools import lru_cache
from pathlib import Path


def language_for(tag: str | None) -> str:
    language = (tag or '').replace('_', '-').split('-', 1)[0].lower()
    return language if language in {'ca', 'es'} else 'en'


@lru_cache(maxsize=1)
def get_language() -> str:
    try:
        if sys.platform == 'darwin':
            from Foundation import NSLocale
            preferred = NSLocale.preferredLanguages()
            return language_for(str(preferred[0]) if preferred else None)
        if sys.platform == 'win32':
            # Use the user's display language, independently of the formatting locale.
            primary = ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3ff
            return 'ca' if primary == 3 else 'es' if primary == 10 else 'en'
        return language_for(locale.getlocale()[0])
    except (ImportError, AttributeError, OSError, ValueError, IndexError):
        return 'en'


@lru_cache(maxsize=3)
def catalog(language: str) -> dict[str, str]:
    return json.loads((Path(__file__).with_name('locales') / f'{language}.json').read_text(encoding='utf-8'))


def tr(message: str, *values: object) -> str:
    translated = catalog(get_language()).get(message, message)
    return re.sub(r'\{(\d+)\}', lambda match: str(values[int(match[1])]), translated) if values else translated


def localized_html(source: str) -> str:
    """Translate explicit static text/attributes; never traverse user-generated DOM."""
    import html
    def text(match):
        content = match[1]
        stripped = html.unescape(content.strip())
        if stripped not in catalog(get_language()):
            return match[0]
        leading = content[:len(content)-len(content.lstrip())]
        trailing = content[len(content.rstrip()):]
        return '>' + leading + html.escape(tr(stripped), quote=False) + trailing + '<'
    source = re.sub(r'>([^<>]+)<', text, source)
    source = re.sub(r'(\b(?:title|placeholder|aria-label)=")([^"]*)(")',
                    lambda m: m[1]+html.escape(tr(html.unescape(m[2])), quote=True)+m[3], source)
    source = re.sub(r'<html lang="[^"]*"', f'<html lang="{get_language()}"', source)
    messages = json.dumps(catalog(get_language()), ensure_ascii=True).replace('<', '\\u003c')
    bootstrap = '<script>window.NP_LANGUAGE=' + json.dumps(get_language()) + ';window.NP_MESSAGES=' + messages + ';</script><script src="/static/i18n.js"></script>'
    return source.replace('</head>', bootstrap+'</head>')
