"""
Renders the Markdown docs under docs/system/ and docs/manual/ (plus
docs/kiosk_deployment.md) inside the web app, so they're reachable without
repo access.

Deliberately an allowlist of known files (SECTIONS below), not a directory
listing off the filesystem -- same "don't trust the URL" posture already
used by ProtectedMediaView for media files.
"""
import posixpath
import re
from pathlib import Path

import markdown as _markdown
from django.conf import settings
from django.urls import reverse

DOCS_ROOT = Path(settings.BASE_DIR) / 'docs'

# section -> (subdir under DOCS_ROOT, [page slugs in nav order])
# 'README' is a section's index page, served at the section URL with no page.
SECTIONS = {
    'system': (
        'system',
        ['README', '01-visao-geral', '02-modelo-de-dados',
         '03-autenticacao-e-controle-de-acesso', '04-fluxo-biometrico',
         '05-arquitetura-kiosk', '06-deploy-e-operacao', '07-testes',
         '08-controles-de-acesso-e-gaps-conhecidos'],
    ),
    'manual': (
        'manual',
        ['README', '01-introducao', '02-login', '03-cadastro-funcionario',
         '04-registro-ponto', '05-visitantes', '06-caminhoes',
         '07-kiosk-biometrico', '08-erros-comuns', '09-privacidade-dados'],
    ),
    'root': (
        '',
        ['kiosk_deployment'],
    ),
}

SECTION_LABELS = {
    'system': 'Documentação técnica',
    'manual': 'Manual do usuário',
    'root': 'Outros documentos',
}

# Matches markdown links to another doc in this same tree, e.g.
# "[Modelo de dados](02-modelo-de-dados.md)" or "[x](../manual/README.md#y)".
_MD_LINK_RE = re.compile(r'\[([^\]]+)\]\(((?:\.\./)*[\w./-]+\.md(?:#[\w-]+)?)\)')


class DocNotFound(Exception):
    pass


def _file_path(section, page):
    if section not in SECTIONS:
        raise DocNotFound(section)
    subdir, pages = SECTIONS[section]
    if page not in pages:
        raise DocNotFound(page)
    filename = f'{page}.md'
    return DOCS_ROOT / subdir / filename if subdir else DOCS_ROOT / filename


def doc_url(section, page='README'):
    if page == 'README':
        return reverse('documentation_section', kwargs={'section': section})
    return reverse('documentation_page', kwargs={'section': section, 'page': page})


def _resolve_relative_link(current_section, target):
    """Resolve a relative .md link as written inside our own docs (e.g.
    "02-modelo-de-dados.md" or "../manual/README.md#anchor") into an in-app
    URL. Returns None when it doesn't resolve to a known page -- the link
    is then left untouched by the caller rather than guessed at."""
    target_path, _, anchor = target.partition('#')
    if not target_path:
        return None
    current_subdir = SECTIONS[current_section][0] or '.'
    combined = posixpath.normpath(posixpath.join(current_subdir, target_path))
    parts = combined.split('/')
    filename = parts[-1]
    resolved_subdir = '/'.join(parts[:-1])
    section = next(
        (name for name, (sub, _) in SECTIONS.items() if sub == resolved_subdir),
        None,
    )
    if section is None or not filename.endswith('.md'):
        return None
    page = filename[:-3]
    if page not in SECTIONS[section][1]:
        return None
    url = doc_url(section, page)
    return f'{url}#{anchor}' if anchor else url


def _rewrite_links(text, current_section):
    def repl(match):
        label, target = match.group(1), match.group(2)
        resolved = _resolve_relative_link(current_section, target)
        return f'[{label}]({resolved})' if resolved else match.group(0)
    return _MD_LINK_RE.sub(repl, text)


def _read_text(section, page):
    path = _file_path(section, page)
    try:
        return path.read_text(encoding='utf-8')
    except FileNotFoundError:
        raise DocNotFound(page)


def doc_title(section, page):
    """First top-level heading in the file, without a full Markdown render
    (cheap enough to call once per nav entry when building the index)."""
    for line in _read_text(section, page).splitlines():
        if line.startswith('# '):
            return line[2:].strip()
    return page


def render_doc(section, page):
    """Returns (title, html) for a doc page, or raises DocNotFound."""
    text = _read_text(section, page)
    text = _rewrite_links(text, section)
    html = _markdown.markdown(
        text,
        extensions=['extra', 'toc', 'sane_lists'],
        extension_configs={'toc': {'permalink': False}},
    )
    title_match = re.search(r'^#\s+(.+)$', text, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else page
    return title, html


def nav_tree():
    """Structure for the sidebar/index: list of sections, each with its
    ordered list of pages (slug, title, url)."""
    tree = []
    for section, (_, pages) in SECTIONS.items():
        entries = [
            {'page': page, 'title': doc_title(section, page), 'url': doc_url(section, page)}
            for page in pages
        ]
        tree.append({'section': section, 'label': SECTION_LABELS[section], 'entries': entries})
    return tree
