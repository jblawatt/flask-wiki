
# Für später mal
# https://github.com/neurobin/mdx_include


import os
import string

from codecs import open
from datetime import datetime
from os.path import abspath, join, dirname, isfile, splitext
from collections import namedtuple

from typing import Iterable, List

from markdown import Markdown
from markdown.extensions.codehilite import CodeHiliteExtension
from markdown_include.include import MarkdownInclude
from full_yaml_metadata import FullYamlMetadataExtension
from flask import Flask, render_template, url_for, request, redirect, before_render_template
from flask_assets import Environment, Bundle

app: Flask = Flask(__name__)
assets: Environment = Environment(app=app)


Page = namedtuple('Page', ('title', 'filename', 'last_changed',
                           'html', 'tags', 'markdown', 'summary', 'url', 'url_edit'))
Tag = namedtuple('Tag', ('name', 'url'))

DATA_ROOT = join(abspath(dirname(__name__)), 'data')
BOOTSWATCH_THEME = 'flatly'


def apply_default_context(sender, template, context, **extra):
    context.setdefault('BOOTSWATCH_THEME', BOOTSWATCH_THEME)


before_render_template.connect(apply_default_context, app)


def _create_md_instance() -> Markdown:
    return Markdown(extensions=[
        'tables', 'extra', 'wikilinks', 'toc',
        CodeHiliteExtension(noclasses=True, pygments_style='borland'),
        FullYamlMetadataExtension(),
        MarkdownInclude(configs={'base_path': DATA_ROOT, 'encoding': 'utf-8'}),
        'markdown_checklist.extension'
    ])


from markdown_checklist.extension import makeExtension


def _parse_tags(tags: Iterable[str]) -> Iterable[Tag]:
    for tag in tags:
        yield Tag(tag, url_for('tag_pages', tag=tag))


def _parse_page(content, filename=None, last_changed: datetime = None) -> Page:
    md = _create_md_instance()
    html = md.convert(content)
    meta = md.Meta or dict(title='NEW', tags=[])
    last_changed = last_changed or datetime.now()
    if filename:
        wiki_title, __ = splitext(filename)
    else:
        wiki_title = ''
    return Page(
        meta.get('title'), filename, last_changed, html,
        _parse_tags(meta.get('tags', [])), content, meta.get('summary', ''),
        url_for('view', wiki_title=wiki_title),
        url_for('edit', wiki_title=wiki_title),
    )


def load_page(name) -> Page:
    file_abspath = join(DATA_ROOT, '%s.md' % name)
    stats = os.stat(file_abspath)
    last_modified = datetime.fromtimestamp(stats.st_mtime)
    with open(file_abspath, 'r', encoding='utf-8') as content:
        return _parse_page(content.read(), '%s.md' % name, last_modified)


def load_pages(tags: List[str] = None):
    for item in os.listdir(DATA_ROOT):
        if isfile(join(DATA_ROOT, item)):
            name, ext = splitext(item)
            if ext.lower() == '.md':
                page = load_page(name)
                if tags:
                    for t in page.tags:
                        if t.name in tags:
                            yield page
                            break
                else:
                    yield page


def page_exists(name) -> bool:
    file_abspath = join(DATA_ROOT, '%s.md' % name)
    return os.path.exists(file_abspath)


def save_page(name, content):
    file_abspath = join(DATA_ROOT, '%s.md' % name)
    with open(file_abspath, mode='w', encoding='utf-8') as md_file:
        md_file.write(content)


def load_tags() -> Iterable[Tag]:
    tags = set()
    for page in load_pages():
        for tag in page.tags:
            tags.add(tag)
    return sorted(tags, key=lambda t: t.name)


@app.route('/')
def index() -> str:
    return render_template('view.html', page=load_page('index'))


@app.route('/_pages')
def pages() -> str:
    filter_tags: List = []
    filter_tags_str: str = request.args.get('filter__tags', None)
    if filter_tags_str is not None:
        filter_tags = list(map(str.strip, filter_tags_str.split(',')))
    pages = load_pages(tags=filter_tags)
    return render_template('list.html', pages=pages)


@app.route('/_tags')
def tags() -> str:
    tags = load_tags()
    return render_template('tags.html', tags=tags)


@app.route('/_tags/<tag>')
def tag_pages(tag) -> str:
    pages = load_pages(tags=[tag])
    return render_template('list.html', pages=pages)


@app.route('/<wiki_title>/')
def view(wiki_title) -> str:
    if page_exists(wiki_title):
        page = load_page(wiki_title)
        return render_template('view.html', page=page)
    redirect_url = url_for('edit', wiki_title=wiki_title)
    return redirect(redirect_url)


@app.route('/<wiki_title>/_edit', methods=['GET', 'POST'])
def edit(wiki_title) -> str:
    if request.method == 'GET':
        page = load_page(name=wiki_title)
        return render_template('edit.html', page=page)
    else:
        content = request.form['content']
        content = content.replace('\r', '')
        if request.form['submit'] == 'preview':
            preview = _parse_page(content)
            page = load_page(wiki_title)
            return render_template('edit.html', preview=preview, page=page)
        else:
            save_page(wiki_title, content)
            redirect_url = url_for('view', wiki_title=wiki_title)
            return redirect(redirect_url)


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=3000, debug=True)
