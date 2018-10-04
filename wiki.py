
import os
import string
import functools
import mimetypes

from codecs import open
from datetime import datetime
from os.path import abspath, join, dirname, isfile, splitext
from collections import namedtuple

from typing import Iterable, List

from markdown import Markdown
from markdown.util import etree
from markdown.extensions.codehilite import CodeHiliteExtension
from markdown_include.include import MarkdownInclude
from markdown_checklist.extension import makeExtension
from markdown.extensions.admonition import AdmonitionExtension
from full_yaml_metadata import FullYamlMetadataExtension
from flask import Flask, render_template, url_for, request, redirect, before_render_template, send_from_directory
from flask_assets import Environment, Bundle
from slugify import slugify


Page = namedtuple('Page', ('title', 'filename', 'last_changed',
                           'html', 'tags', 'markdown', 'summary', 'url', 'url_edit'))

Tag = namedtuple('Tag', ('name', 'url'))

File = namedtuple('File', ('name', 'mimetype', 'url', 'raw_url', 'is_image', 'last_changed'))

APP_ROOT = abspath(dirname(__name__))
DATA_ROOT = join(APP_ROOT, 'data')
FILES_ROOT = join(DATA_ROOT, 'files')
PAGES_ROOT = join(DATA_ROOT, 'pages')
ASSETS_ROOT = join(APP_ROOT, 'static')

os.makedirs(DATA_ROOT, exist_ok=True)
os.makedirs(FILES_ROOT, exist_ok=True)
os.makedirs(PAGES_ROOT, exist_ok=True)

BOOTSWATCH_THEME = None # 'flatly'
NEW_PAGE_TEMPLATE = """
---
title: new page title
summary: summary of the new page
tags: 
    - checklist
---
new page content
""".strip()
WIKI_TITLE = 'FlaskWIKI'
WIKI_SUBTITLE = 'the flask based micro wiki'
LANG = 'de'


app: Flask = Flask(__name__)
assets: Environment = Environment(app=app)

assets.directory = ASSETS_ROOT

assets.register('js', Bundle(
    'vendor/js/jquery.slim.js',
    'vendor/js/popper.js',
    'vendor/js/bootstrap.js',
    filters='jsmin', output='dist/bundle.js',
))

assets.register('css', Bundle(
    'vendor/css/bootstrap.css',
    'css/flask-wiki.css',
    filters='cssmin', output='dist/bundle.css',
))


def apply_default_context(sender, template, context, **extra):
    context.setdefault('BOOTSWATCH_THEME', BOOTSWATCH_THEME)
    context.setdefault('WIKI_TITLE', WIKI_TITLE)
    context.setdefault('WIKI_SUBTITLE', WIKI_SUBTITLE)
    context.setdefault('LANG', LANG)


before_render_template.connect(apply_default_context, app)


class PageDoesNotExists(Exception):
    pass


# -----------------------------------------------------------
# -------------- Markdown Extensions ------------------------


from markdown.treeprocessors import Treeprocessor
from markdown.postprocessors import Postprocessor
from markdown.extensions import Extension

class LinkOptimizerExtension(Extension):

    def extendMarkdown(self, md: Markdown):
        # md.treeprocessors.register(MyTreeprocessor(md), 'prettify_links', 30)
        md.postprocessors.register(MyPostprocessor(md), 'pretty_links', 30)
        

class MyPostprocessor(Postprocessor):

    def run(self, text):
        return text


class MyTreeprocessor(Treeprocessor):
    def run(self, root):
        print(etree.tostring(root))



# -----------------------------------------------------------
# -------------- Helper -------------------------------------

def _print_header(func):
    """
    Decorator helper to print all given http headers.
    
    :param func: function to wrap
    :type func: types.FunctionType
    :return: Wrapper Function
    :rtype: types.FunctionType
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        for key in request.headers.keys():
            print('%s ::> %s' % (key, request.headers.get(key)))
        return func(*args, **kwargs)
    return wrapper


# -----------------------------------------------------------
# -------------- Parser -------------------------------------


def _create_md_instance() -> Markdown:
    return Markdown(extensions=[
        FullYamlMetadataExtension(),
        'tables', 
        'extra', 
        'toc',
        'admonition',
        CodeHiliteExtension(noclasses=True, pygments_style='borland'),
        MarkdownInclude(configs={'base_path': PAGES_ROOT, 'encoding': 'utf-8'}),
        'markdown_checklist.extension',
        # LinkOptimizerExtension(),
    ])


def _parse_tags(tags: Iterable[str]) -> Iterable[Tag]:
    for tag in tags:
        yield Tag(tag, url_for('tag_pages', tag=tag))


def _parse_page(content, filename=None, last_changed: datetime = None) -> Page:
    md = _create_md_instance()
    html = md.convert(content)
    meta = md.Meta or dict()

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


# -----------------------------------------------------------
# -------------- Loader API Functions------------------------


def load_page(name) -> Page:
    file_abspath = join(PAGES_ROOT, '%s.md' % name)
    if not os.path.exists(file_abspath):
        raise PageDoesNotExists(name)
    stats = os.stat(file_abspath) 
    last_modified = datetime.fromtimestamp(stats.st_mtime)
    with open(file_abspath, 'r', encoding='utf-8') as content:
        return _parse_page(content.read(), '%s.md' % name, last_modified)


def new_page(name) -> Page:
    return Page(
        '', '%s.md' % name, datetime.now(), '', [], NEW_PAGE_TEMPLATE, '', '', ''
    )


def load_pages(tags: List[str] = None):
    for item in os.listdir(PAGES_ROOT):
        if isfile(join(PAGES_ROOT, item)):
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
    file_abspath = join(PAGES_ROOT, '%s.md' % name)
    return os.path.exists(file_abspath)


def save_page(name, content):
    file_abspath = join(PAGES_ROOT, '%s.md' % name)
    with open(file_abspath, mode='w', encoding='utf-8') as md_file:
        md_file.write(content)


def load_tags() -> Iterable[Tag]:
    tags = set()
    for page in load_pages():
        for tag in page.tags:
            tags.add(tag)
    return sorted(tags, key=lambda t: t.name)


def load_file(filename) -> File:
    abs_path = join(FILES_ROOT, filename)
    mtype, __ = mimetypes.guess_type(abs_path)
    return File(filename, mtype, url_for('file_', filename=filename), 
                url_for('raw', filename=filename), mtype.startswith('image/'), datetime.now())


def load_files() -> Iterable[File]:
    for item in os.listdir(FILES_ROOT):
        if isfile(join(FILES_ROOT, item)):
            yield load_file(item)


def file_exists(filename) -> bool:
    return True


# -----------------------------------------------------------
# -------------- Views --------------------------------------


@app.route('/')
def index() -> str:
    return render_template('page.html', page=load_page('index'))


@app.route('/_pages')
def pages() -> str:
    filter_tags: List = []
    filter_tags_str: str = request.args.get('filter__tags', None)
    if filter_tags_str is not None:
        filter_tags = list(map(str.strip, filter_tags_str.split(',')))
    pages = load_pages(tags=filter_tags)
    return render_template('pages.html', pages=pages)


@app.route('/_tags')
def tags() -> str:
    tags = load_tags()
    return render_template('tags.html', tags=tags)


@app.route('/_tags/<tag>')
def tag_pages(tag) -> str:
    pages = load_pages(tags=[tag])
    return render_template('pages.html', pages=pages)


@app.route('/<wiki_title>/')
def view(wiki_title) -> str:
    if page_exists(wiki_title):
        page: Page = load_page(wiki_title)
        return render_template('page.html', page=page)
    redirect_url = url_for('edit', wiki_title=wiki_title)
    return redirect(redirect_url)


@app.route('/<wiki_title>/_edit', methods=['GET', 'POST'])
def edit(wiki_title) -> str:
    if not page_exists(wiki_title):
        if wiki_title != slugify(wiki_title):
            redirect_url = url_for('edit', wiki_title=slugify(wiki_title))
            return redirect(redirect_url)
    if request.method == 'GET':
        if page_exists(wiki_title):
            page: Page = load_page(name=wiki_title)
        else:
            page: Page = new_page(name=wiki_title)
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


@app.route('/_new')
def new():
    name = request.args.get('name')
    name = slugify(name)
    url = url_for('edit', wiki_title=name)
    return redirect(url)


@app.route('/_files')
def files():
    files = load_files()
    return render_template('files.html', files=files)


@app.route('/_files/<filename>', methods=['GET', 'POST'])
def file_(filename):
    if request.accept_mimetypes.best.startswith('image/'):
        os.makedirs(FILES_ROOT, exist_ok=True)
        return send_from_directory(FILES_ROOT, filename)
    if request.method == 'GET':
        if file_exists(filename):
            file_ = load_file(filename)
        else:
            file_ = None
        return render_template('file.html', file=file_)
    elif request.method == 'POST':
        if 'file' not in request.files:
            return redirect(request.url)
        file = request.files['file']
        file.save(join(FILES_ROOT, filename))
        return redirect(url_for('file_', filename=filename))


@app.route('/_raw/<filename>')
@_print_header
def raw(filename):
    os.makedirs(FILES_ROOT, exist_ok=True)
    return send_from_directory(FILES_ROOT, filename)


@app.route('/_debug')
def debug():
    resp = []
    for key in request.headers.keys():
        tpl = " -> ".join((key, request.headers.get(key)))
        resp.append(tpl)
    return "<br />".join(resp)
    

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=3000, debug=True)
