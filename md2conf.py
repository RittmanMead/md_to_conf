#!/usr/bin/env python3
"""
# --------------------------------------------------------------------------------------------------
# Rittman Mead Markdown to Confluence Tool
# --------------------------------------------------------------------------------------------------
# Create or Update Atlas pages remotely using markdown files.
#
# --------------------------------------------------------------------------------------------------
# Usage: rest_md2conf.py markdown spacekey
# --------------------------------------------------------------------------------------------------
"""

import logging
import sys
import os
import re
import json
import collections
import mimetypes
import codecs
import argparse
import urllib
import webbrowser
import requests
import markdown

logging.basicConfig(level=logging.INFO, format='%(asctime)s - \
%(levelname)s - %(funcName)s [%(lineno)d] - \
%(message)s')
LOGGER = logging.getLogger(__name__)

# ArgumentParser to parse arguments and options
PARSER = argparse.ArgumentParser()
PARSER.add_argument("markdownFile", help="Full path of the markdown file to convert and upload.")
PARSER.add_argument('spacekey',
                    help="Confluence Space key for the page. If omitted, will use user space.")
PARSER.add_argument('-u', '--username', help='Confluence username if $CONFLUENCE_USERNAME not set.')
PARSER.add_argument('-p', '--apikey', help='Confluence API key if $CONFLUENCE_API_KEY not set.')
PARSER.add_argument('--pat', help='Confluence Personal Access Token if $CONFLUENCE_PERSONAL_ACCESS_TOKEN not set.')
PARSER.add_argument('-o', '--orgname',
                    help='Confluence organisation if $CONFLUENCE_ORGNAME not set. '
                         'e.g. https://XXX.atlassian.net/wiki'
                         'If orgname contains a dot, considered as the fully qualified domain name.'
                         'e.g. https://XXX')
PARSER.add_argument('-a', '--ancestor',
                    help='Parent page under which page will be created or moved.')
PARSER.add_argument('-t', '--attachment', nargs='+',
                    help='Attachment(s) to upload to page. Paths relative to the markdown file.')
PARSER.add_argument('-c', '--contents', action='store_true', default=False,
                    help='Use this option to generate a contents page.')
PARSER.add_argument('-g', '--nogo', action='store_true', default=False,
                    help='Use this option to skip navigation after upload.')
PARSER.add_argument('-n', '--nossl', action='store_true', default=False,
                    help='Use this option if NOT using SSL. Will use HTTP instead of HTTPS.')
PARSER.add_argument('-d', '--delete', action='store_true', default=False,
                    help='Use this option to delete the page instead of create it.')
PARSER.add_argument('-l', '--loglevel', default='INFO',
                    help='Use this option to set the log verbosity.')
PARSER.add_argument('-s', '--simulate', action='store_true', default=False,
                    help='Use this option to only show conversion result.')
PARSER.add_argument('-v', '--version', type=int, action='store', default=1,
                    help='Version of confluence page (default is 1).')
PARSER.add_argument('-mds', '--markdownsrc', action='store', default='default',
                    choices=['default', 'bitbucket'],
                    help='Use this option to specify a markdown source (i.e. what processor this markdown was targeting). '
                         'Possible values: bitbucket.')
PARSER.add_argument('--label', action='append', dest='labels', default=[],
                    help='A list of labels to set on the page.')
PARSER.add_argument('--property', action='append', dest='properties', default=[],
                    type=lambda kv: kv.split("="),
                    help='A list of content properties to set on the page.')
PARSER.add_argument('--detail', action='append', dest='details', default=[],
                    type=lambda kv: kv.split("="),
                    help='A list of page details to set on the page')
PARSER.add_argument('--hide-details', action='store_true', dest='details_visibility', default=False,
                    help='Use this option to make page details table hidden.')
PARSER.add_argument('--pages-map', action='append', dest='pages_map', default=[],
                    type=lambda kv: kv.split("="),
                    help='Use this option to specify a mapping between a base URL (for links) '
                         'and base local directory (for .md files) to resolve page to page links')
PARSER.add_argument('--title', action='store', dest='title', default=None,
                    help='Set the title for the page, otherwise the title is going to be the first line in the markdown file')
PARSER.add_argument('--remove-emojies', action='store_true', dest='remove_emojies', default=False,
                    help='Remove emojies if there are any. This may be need if the database doesn\'t support emojies')

ARGS = PARSER.parse_args()

# Assign global variables
try:
    # Set log level
    LOGGER.setLevel(getattr(logging, ARGS.loglevel.upper(), None))

    MARKDOWN_FILE = ARGS.markdownFile
    SPACE_KEY = ARGS.spacekey
    USERNAME = os.getenv('CONFLUENCE_USERNAME', ARGS.username)
    API_KEY = os.getenv('CONFLUENCE_API_KEY', ARGS.apikey)
    PA_TOKEN = os.getenv('CONFLUENCE_PERSONAL_ACCESS_TOKEN', ARGS.pat)
    ORGNAME = os.getenv('CONFLUENCE_ORGNAME', ARGS.orgname)
    ANCESTOR = ARGS.ancestor
    NOSSL = ARGS.nossl
    DELETE = ARGS.delete
    SIMULATE = ARGS.simulate
    VERSION = ARGS.version
    MARKDOWN_SOURCE = ARGS.markdownsrc
    LABELS = ARGS.labels
    PROPERTIES = dict(ARGS.properties)
    DETAILS = dict(ARGS.details)
    DETAILS_VISIBILITY = ARGS.details_visibility
    PAGES_MAP = dict(ARGS.pages_map)
    ATTACHMENTS = ARGS.attachment
    GO_TO_PAGE = not ARGS.nogo
    CONTENTS = ARGS.contents
    TITLE = ARGS.title
    REMOVE_EMOJIES = ARGS.remove_emojies

    if USERNAME is None and PA_TOKEN is None:
        LOGGER.error('Error: Username/PAT Token not specified by environment variable or option.')
        sys.exit(1)

    if API_KEY is None and PA_TOKEN is None:
        LOGGER.error('Error: API key or Personal Access Token not specified by environment variable or option.')
        sys.exit(1)

    if not os.path.exists(MARKDOWN_FILE):
        LOGGER.error('Error: Markdown file: %s does not exist.', MARKDOWN_FILE)
        sys.exit(1)

    if SPACE_KEY is None:
        SPACE_KEY = '~%s' % (USERNAME)

    if ORGNAME is not None:
        if ORGNAME.find('.') != -1:
            CONFLUENCE_API_URL_TMP = 'https://%s' % ORGNAME
        else:
            CONFLUENCE_API_URL_TMP = 'https://%s.atlassian.net/wiki' % ORGNAME
    else:
        LOGGER.error('Error: Org Name not specified by environment variable or option.')
        sys.exit(1)
    CONFLUENCE_API_URL = CONFLUENCE_API_URL_TMP
    if NOSSL:
        CONFLUENCE_API_URL = CONFLUENCE_API_URL_TMP.replace('https://', 'http://')
    else:
        CONFLUENCE_API_URL = CONFLUENCE_API_URL_TMP

except Exception as err:
    LOGGER.error('\n\nException caught:\n%s ', err)
    LOGGER.error('\nFailed to process command line arguments. Exiting.')
    sys.exit(1)

def convert_comment_block(html):
    """
    Convert markdown code bloc to Confluence hidden comment

    :param html: string
    :return: modified html string
    """
    open_tag = '<ac:placeholder>'
    close_tag = '</ac:placeholder>'

    html = html.replace('<!--', open_tag).replace('-->', close_tag)

    return html

def create_table_of_content(html):
    """
    Check for the string '[TOC]' and replaces it the Confluence "Table of Content" macro

    :param html: string
    :return: modified html string
    """
    html = re.sub(
        r'<p>\[TOC\]</p>',
        '<p><ac:structured-macro ac:name="toc" ac:schema-version="1"/></p>',
        html,
        1)

    return html


def convert_code_block(html):
    """
    Convert html code blocks to Confluence macros

    :param html: string
    :return: modified html string
    """
    code_blocks = re.findall(r'<pre><code.*?>.*?</code></pre>', html, re.DOTALL)
    if code_blocks:
        for tag in code_blocks:

            conf_ml = '<ac:structured-macro ac:name="code">'
            conf_ml = conf_ml + '<ac:parameter ac:name="theme">Midnight</ac:parameter>'
            conf_ml = conf_ml + '<ac:parameter ac:name="linenumbers">true</ac:parameter>'

            lang = re.search('code class="(.*)"', tag)
            if lang:
                lang = lang.group(1)
            else:
                lang = 'none'

            conf_ml = conf_ml + '<ac:parameter ac:name="language">' + lang + '</ac:parameter>'
            content = re.search(r'<pre><code.*?>(.*?)</code></pre>', tag, re.DOTALL).group(1)
            content = content.replace("]]", "]]]]><![CDATA[")
            content = '<ac:plain-text-body><![CDATA[' + content + ']]></ac:plain-text-body>'
            conf_ml = conf_ml + content + '</ac:structured-macro>'
            conf_ml = conf_ml.replace('&lt;', '<').replace('&gt;', '>')
            conf_ml = conf_ml.replace('&quot;', '"').replace('&amp;', '&')

            html = html.replace(tag, conf_ml)

    return html

def convert_iframe_macros(html):
    """[summary]
    Converts <iframe ...></iframe> to Confluence iframe macro

    :param html: html string
    :return: modified html string

    """

    html_tag = '<p><ac:structured-macro ac:name = "html" ><ac:plain-text-body > <![CDATA['
    close_tag = ']]> </ac:plain-text-body></ac:structured-macro ></p>'

    iframes = re.findall('<iframe(.*?)</iframe>', html, re.DOTALL)
    if iframes:
        for iframe in iframes:
            src = '<iframe' + iframe + '</iframe>'
            dst = html_tag + src + close_tag
            html = html.replace(src, dst)

    return html

def remove_emojies(html):
    """
    Remove emojies if there are any

    :param html: string
    :return: modified html string
    """
    regrex_pattern = re.compile(pattern = "["
        u"\U0001F600-\U0001F64F"  # emoticons
        u"\U0001F300-\U0001F5FF"  # symbols & pictographs
        u"\U0001F680-\U0001F6FF"  # transport & map symbols
        u"\U0001F1E0-\U0001F1FF"  # flags (iOS)
                           "]+", flags = re.UNICODE)
    return regrex_pattern.sub(r'',html)


def convert_info_macros(html):
    """
    Converts html for info, note or warning macros

    :param html: html string
    :return: modified html string
    """
    info_tag = '<p><ac:structured-macro ac:name="info"><ac:rich-text-body><p>'
    note_tag = info_tag.replace('info', 'note')
    warning_tag = info_tag.replace('info', 'warning')
    close_tag = '</p></ac:rich-text-body></ac:structured-macro></p>'

    # Custom tags converted into macros
    html = html.replace('<p>~?', info_tag).replace('?~</p>', close_tag)
    html = html.replace('<p>~!', note_tag).replace('!~</p>', close_tag)
    html = html.replace('<p>~%', warning_tag).replace('%~</p>', close_tag)

    # Convert block quotes into macros
    quotes = re.findall('<blockquote>(.*?)</blockquote>', html, re.DOTALL)
    if quotes:
        for quote in quotes:
            note = re.search('^<.*>Note', quote.strip(), re.IGNORECASE)
            warning = re.search('^<.*>Warning', quote.strip(), re.IGNORECASE)

            if note:
                clean_tag = strip_type(quote, 'Note')
                macro_tag = clean_tag.replace('<p>', note_tag).replace('</p>', close_tag).strip()
            elif warning:
                clean_tag = strip_type(quote, 'Warning')
                macro_tag = clean_tag.replace('<p>', warning_tag).replace('</p>', close_tag).strip()
            else:
                macro_tag = quote.replace('<p>', info_tag).replace('</p>', close_tag).strip()

            html = html.replace('<blockquote>%s</blockquote>' % quote, macro_tag)

    # Convert doctoc to toc confluence macro
    html = convert_doctoc(html)

    return html


def convert_doctoc(html):
    """
    Convert doctoc to confluence macro

    :param html: html string
    :return: modified html string
    """

    toc_tag = '''<p>
    <ac:structured-macro ac:name="toc">
      <ac:parameter ac:name="printable">true</ac:parameter>
      <ac:parameter ac:name="style">disc</ac:parameter>
      <ac:parameter ac:name="maxLevel">7</ac:parameter>
      <ac:parameter ac:name="minLevel">1</ac:parameter>
      <ac:parameter ac:name="type">list</ac:parameter>
      <ac:parameter ac:name="outline">clear</ac:parameter>
      <ac:parameter ac:name="include">.*</ac:parameter>
    </ac:structured-macro>
    </p>'''

    html = re.sub('\<\!\-\- START doctoc.*END doctoc \-\-\>', toc_tag, html, flags=re.DOTALL)

    return html


def strip_type(tag, tagtype):
    """
    Strips Note or Warning tags from html in various formats

    :param tag: tag name
    :param tagtype: tag type
    :return: modified tag
    """
    tag = re.sub('%s:\s' % tagtype, '', tag.strip(), re.IGNORECASE)
    tag = re.sub('%s\s:\s' % tagtype, '', tag.strip(), re.IGNORECASE)
    tag = re.sub('<.*?>%s:\s<.*?>' % tagtype, '', tag, re.IGNORECASE)
    tag = re.sub('<.*?>%s\s:\s<.*?>' % tagtype, '', tag, re.IGNORECASE)
    tag = re.sub('<(em|strong)>%s:<.*?>\s' % tagtype, '', tag, re.IGNORECASE)
    tag = re.sub('<(em|strong)>%s\s:<.*?>\s' % tagtype, '', tag, re.IGNORECASE)
    tag = re.sub('<(em|strong)>%s<.*?>:\s' % tagtype, '', tag, re.IGNORECASE)
    tag = re.sub('<(em|strong)>%s\s<.*?>:\s' % tagtype, '', tag, re.IGNORECASE)
    string_start = re.search('<.*?>', tag)
    tag = upper_chars(tag, [string_start.end()])
    return tag


def upper_chars(string, indices):
    """
    Make characters uppercase in string

    :param string: string to modify
    :param indices: character indice to change to uppercase
    :return: uppercased string
    """
    upper_string = "".join(c.upper() if i in indices else c for i, c in enumerate(string))
    return upper_string


def slug(string, lowercase):
    """
    Creates a slug string

    :param string: string to modify
    :param lowercase: bool indicating whether string has to be lowercased
    :return: slug string
    """

    slug_string = string
    if lowercase:
        slug_string = string.lower()


    # Remove all html code tags
    slug_string = re.sub(r'<[^>]+>', '', slug_string)

    # Remove html code like '&amp;'
    slug_string = re.sub(r'&[a-z]+;', '', slug_string)

    # Replace all spaces ( ) with dash (-)
    slug_string = re.sub(r'[ ]', '-', slug_string)

    # Remove all special chars, except for dash (-)
    slug_string = re.sub(r'[^a-zA-Z0-9-]', '', slug_string)
    return slug_string


def process_refs(html):
    """
    Process references

    :param html: html string
    :return: modified html string
    """
    refs = re.findall('\n(\[\^(\d)\].*)|<p>(\[\^(\d)\].*)', html)

    if refs:

        for ref in refs:
            if ref[0]:
                full_ref = ref[0].replace('</p>', '').replace('<p>', '')
                ref_id = ref[1]
            else:
                full_ref = ref[2]
                ref_id = ref[3]

            full_ref = full_ref.replace('</p>', '').replace('<p>', '')
            html = html.replace(full_ref, '')
            href = re.search('href="(.*?)"', full_ref).group(1)

            superscript = '<a id="test" href="%s"><sup>%s</sup></a>' % (href, ref_id)
            html = html.replace('[^%s]' % ref_id, superscript)

    return html


def get_page(title):
    """
     Retrieve page details by title

    :param title: page tile
    :return: Confluence page info
    """
    LOGGER.info('\tRetrieving page information: %s', title)
    url = '%s/rest/api/content?title=%s&spaceKey=%s&expand=version,ancestors' % (
        CONFLUENCE_API_URL, urllib.parse.quote_plus(title), SPACE_KEY)

    # We retrieve content property values as part of page content
    # to make sure we are able to update them later
    if PROPERTIES:
        url = '%s,%s' % (url, ','.join("metadata.properties.%s" % v for v in PROPERTIES.keys()))

    session = requests.Session()

    if PA_TOKEN:
        session.headers.update({'Authorization': 'Bearer ' + PA_TOKEN})
    else:
        session.auth = (USERNAME, API_KEY)

    retry_max_requests=5
    retry_backoff_factor=0.1
    retry_status_forcelist=(404, 500, 501, 502, 503, 504)
    retry = requests.adapters.Retry(
        total=retry_max_requests,
        connect=retry_max_requests,
        read=retry_max_requests,
        backoff_factor=retry_backoff_factor,
        status_forcelist=retry_status_forcelist,
    )
    adapter = requests.adapters.HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)

    response = session.get(url)

    # Check for errors
    try:
        response.raise_for_status()
    except requests.RequestException as err:
        LOGGER.error('err.response: %s', err)
        if response.status_code == 404:
            LOGGER.error('Error: Page not found. Check the following are correct:')
            LOGGER.error('\tSpace Key : %s', SPACE_KEY)
            LOGGER.error('\tOrganisation Name: %s', ORGNAME)
        else:
            LOGGER.error('Error: %d - %s', response.status_code, response.content)
        sys.exit(1)

    data = response.json()

    LOGGER.debug("data: %s", str(data))

    if len(data[u'results']) >= 1:
        page_id = data[u'results'][0][u'id']
        version_num = data[u'results'][0][u'version'][u'number']
        link = '%s%s' % (CONFLUENCE_API_URL, data[u'results'][0][u'_links'][u'webui'])

        try:
            properties = data[u'results'][0][u'metadata'][u'properties']
        except KeyError:
            # In case when page has no content properties we can simply ignore them
            properties = {}
            pass

        page_info = collections.namedtuple('PageInfo', ['id', 'version', 'link', 'properties'])
        page = page_info(page_id, version_num, link, properties)
        return page

    return False


# Scan for images and upload as attachments if found
def add_images(page_id, html):
    """
    Scan for images and upload as attachments if found

    :param page_id: Confluence page id
    :param html: html string
    :return: html with modified image reference
    """
    source_folder = os.path.dirname(os.path.abspath(MARKDOWN_FILE))

    for tag in re.findall('<img(.*?)\/>', html):
        rel_path = re.search('src="(.*?)"', tag).group(1)
        alt_text = re.search('alt="(.*?)"', tag).group(1)
        abs_path = os.path.join(source_folder, rel_path)
        basename = os.path.basename(rel_path)
        upload_attachment(page_id, abs_path, alt_text)
        if re.search('http.*', rel_path) is None:
            if CONFLUENCE_API_URL.endswith('/wiki'):
                html = html.replace('%s' % (rel_path),
                                    '/wiki/download/attachments/%s/%s' % (page_id, basename))
            else:
                html = html.replace('%s' % (rel_path),
                                    '/download/attachments/%s/%s' % (page_id, basename))
    return html


def add_contents(html):
    """
    Add contents page

    :param html: html string
    :return: modified html string
    """
    contents_markup = '<ac:structured-macro ac:name="toc">\n<ac:parameter ac:name="printable">' \
                     'true</ac:parameter>\n<ac:parameter ac:name="style">disc</ac:parameter>'
    contents_markup = contents_markup + '<ac:parameter ac:name="maxLevel">5</ac:parameter>\n' \
                                      '<ac:parameter ac:name="minLevel">1</ac:parameter>'
    contents_markup = contents_markup + '<ac:parameter ac:name="class">rm-contents</ac:parameter>\n' \
                                      '<ac:parameter ac:name="exclude"></ac:parameter>\n' \
                                      '<ac:parameter ac:name="type">list</ac:parameter>'
    contents_markup = contents_markup + '<ac:parameter ac:name="outline">false</ac:parameter>\n' \
                                      '<ac:parameter ac:name="include"></ac:parameter>\n' \
                                      '</ac:structured-macro>'

    html = contents_markup + '\n' + html
    return html


def add_attachments(page_id, files):
    """
    Add attachments for an array of files

    :param page_id: Confluence page id
    :param files: list of files to attach to the given Confluence page
    :return: None
    """
    source_folder = os.path.dirname(os.path.abspath(MARKDOWN_FILE))

    if files:
        for file in files:
            upload_attachment(page_id, os.path.join(source_folder, file), '')


def add_local_refs(page_id, title, html):
    """
    Convert local links to correct confluence local links

    :param page_title: string
    :param page_id: integer
    :param html: string
    :return: modified html string
    """

    ref_prefixes = {
      "default": "#",
      "bitbucket": "#markdown-header-"
    }
    ref_postfixes = {
      "default": "_%d",
      "bitbucket": "_%d"
    }

    # We ignore local references in case of unknown or unspecified markdown source
    if not MARKDOWN_SOURCE in ref_prefixes or \
       not MARKDOWN_SOURCE in ref_postfixes:
        LOGGER.warning('Local references weren\'t processed because '
                       '--markdownsrc wasn\'t set or specified source isn\'t supported')
        return html

    ref_prefix = ref_prefixes[MARKDOWN_SOURCE]
    ref_postfix = ref_postfixes[MARKDOWN_SOURCE]

    LOGGER.info('Converting confluence local links...')

    headers = re.findall(r'<h\d+>(.*?)</h\d+>', html, re.DOTALL)
    if headers:
        headers_map = {}
        headers_count = {}

        for header in headers:
            key = ref_prefix + slug(header, True)

            if VERSION == 1:
                value = re.sub(r'(<.+?>|[ ])', '', header)
            if VERSION == 2:
                value = slug(header, False)

            if key in headers_map:
                alt_count = headers_count[key]

                alt_key = key + (ref_postfix % alt_count)
                alt_value = value + ('.%s' % alt_count)

                headers_map[alt_key] = alt_value
                headers_count[key] = alt_count + 1
            else:
                headers_map[key] = value
                headers_count[key] = 1

        links = re.findall(r'<a href="#.+?">.+?</a>', html)
        if links:
            for link in links:
                matches = re.search(r'<a href="(#.+?)">(.+?)</a>', link)
                ref = matches.group(1)
                alt = matches.group(2)

                LOGGER.debug('--- Found local link: %s', ref)

                if ref not in headers_map:
                    LOGGER.error("Invalid '%s' local link detected: '%s'. Please update the source file or change the markdown source (-mds) parameter.", MARKDOWN_SOURCE, ref)
                    sys.exit(1)

                result_ref = headers_map.get(ref)

                LOGGER.debug('--- Found local header: %s', result_ref)

                if result_ref:
                    base_uri = '%s/spaces/%s/pages/%s/%s' % (CONFLUENCE_API_URL, SPACE_KEY, page_id, '+'.join(title.split()))
                    if VERSION == 1:
                        replacement_uri = '%s#%s-%s' % (base_uri, ''.join(title.split()), result_ref)
                        replacement = '<ac:link ac:anchor="%s"><ac:plain-text-link-body><![CDATA[%s]]></ac:plain-text-link-body></ac:link>' % (result_ref, re.sub(r'( *<.+?> *)', ' ', alt))
                    if VERSION == 2:
                        replacement_uri = '%s#%s' % (base_uri, result_ref)
                        replacement = '<a href="%s" title="%s">%s</a>' % (replacement_uri, alt, alt)

                    html = html.replace(link, replacement)

                    LOGGER.info('\tTransformed "%s" to "%s"', ref, replacement_uri)

    return html


def add_pages_refs(html):
    """
    Convert markdown page to page links to correct confluence page to page links

    :param html: string
    :return: modified html string
    """

    # We ignore page to page references if no maps are specified
    if not PAGES_MAP:
        LOGGER.warning('Page to page references weren\'t processed because '
                       '--pages_map weren\'t specified')
        return html

    LOGGER.info('Converting confluence page to page links...')

    links = re.findall(r'<a href=".+?\.md">.+?</a>', html)
    if links:
        for link in links:
            matches = re.search(r'<a href="(.+?\.md)">(.+?)</a>', link)
            ref = matches.group(1)
            alt = matches.group(2)

            LOGGER.debug('--- Found page to page link: %s', ref)
            for key in PAGES_MAP:
                if ref.startswith(key):
                    path = os.path.join(PAGES_MAP[key], urllib.parse.unquote(ref[len(key):]))

                    LOGGER.debug('--- Possible page local path: %s', path)
                    try:
                        with open(path, 'r') as mdfile:
                            title = mdfile.readline().lstrip('#').strip()

                            LOGGER.debug('--- Found local page: %s', title)

                            page = get_page(title)
                            if not page:
                                LOGGER.error('Cannot find confluence page "%s"', title)
                                sys.exit(1)

                            LOGGER.debug('--- Found confluence page: %s', page.link)

                            replacement = '<a href="%s" title="%s">%s</a>' % (page.link, alt, alt)
                            html = html.replace(link, replacement)

                            LOGGER.info('\tTransformed "%s" to "%s"', ref, page.link)

                    except IOError:
                        LOGGER.error('Cannot find local file "%s" when resolving page to page link "%s"', path, ref)

    return html


def create_page(title, body, ancestors):
    """
    Create a new page

    :param title: confluence page title
    :param body: confluence page content
    :param ancestors: confluence page ancestor
    :return:
    """
    LOGGER.info('Creating page...')

    url = '%s/rest/api/content/' % CONFLUENCE_API_URL

    session = requests.Session()
    if PA_TOKEN:
        session.headers.update({'Authorization': 'Bearer ' + PA_TOKEN})
    else:
        session.auth = (USERNAME, API_KEY)
    session.headers.update({'Content-Type': 'application/json'})

    new_page = {
        'type': 'page',
        'title': title,
        'space': {'key': SPACE_KEY},
        'body': {
            'storage': {
                'value': body,
                'representation': 'storage'
            }
        },
        'ancestors': ancestors,
        'metadata': {
            'properties': {
                'editor': {
                    'value': 'v%d' % VERSION
                }
            }
        }
    }

    LOGGER.debug("data: %s", json.dumps(new_page))

    response = session.post(url, data=json.dumps(new_page))
    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as excpt:
        LOGGER.error("error: %s - %s", excpt, response.content)
        exit(1)

    if response.status_code == 200:
        data = response.json()
        space_name = data[u'space'][u'name']
        page_id = data[u'id']
        version = data[u'version'][u'number']
        link = '%s%s' % (CONFLUENCE_API_URL, data[u'_links'][u'webui'])

        LOGGER.info('Page created in %s with ID: %s.', space_name, page_id)
        LOGGER.info('URL: %s', link)

        # Populate properties dictionary with initial property values
        properties = {}
        if PROPERTIES:
            for key in PROPERTIES:
                properties[key] = {"key": key, "version": 1, "value": PROPERTIES[key]}

        img_check = re.search('<img(.*?)\/>', body)
        local_ref_check = re.search('<a href="(#.+?)">(.+?)</a>', body)
        if img_check or local_ref_check or properties or ATTACHMENTS or LABELS:
            LOGGER.info('\tAttachments, local references, content properties or labels found, update procedure called.')
            update_page(page_id, title, body, version, ancestors, properties, ATTACHMENTS)
        else:
            if GO_TO_PAGE:
                webbrowser.open(link)
    else:
        LOGGER.error('Could not create page.')
        sys.exit(1)


def delete_page(page_id):
    """
    Delete a page

    :param page_id: confluence page id
    :return: None
    """
    LOGGER.info('Deleting page...')
    url = '%s/rest/api/content/%s' % (CONFLUENCE_API_URL, page_id)

    session = requests.Session()
    if PA_TOKEN:
        session.headers.update({'Authorization': 'Bearer ' + PA_TOKEN})
    else:
        session.auth = (USERNAME, API_KEY)
    session.headers.update({'Content-Type': 'application/json'})

    response = session.delete(url)
    response.raise_for_status()

    if response.status_code == 204:
        LOGGER.info('Page %s deleted successfully.', page_id)
    else:
        LOGGER.error('Page %s could not be deleted.', page_id)


def update_page(page_id, title, body, version, ancestors, properties, attachments):
    """
    Update a page

    :param page_id: confluence page id
    :param title: confluence page title
    :param body: confluence page content
    :param version: confluence page version
    :param ancestors: confluence page ancestor
    :param attachments: confluence page attachments
    :return: None
    """
    LOGGER.info('Updating page...')

    # Add images and attachments
    body = add_images(page_id, body)
    add_attachments(page_id, attachments)

    # Add local references
    body = add_local_refs(page_id, title, body)

    # Add page to page references
    body = add_pages_refs(body)

    url = '%s/rest/api/content/%s' % (CONFLUENCE_API_URL, page_id)

    session = requests.Session()
    if PA_TOKEN:
        session.headers.update({'Authorization': 'Bearer ' + PA_TOKEN})
    else:
        session.auth = (USERNAME, API_KEY)
    session.headers.update({'Content-Type': 'application/json'})

    page_json = {
        "id": page_id,
        "type": "page",
        "title": title,
        "space": {"key": SPACE_KEY},
        "body": {
            "storage": {
                "value": body,
                "representation": "storage"
                }
            },
        "version": {
            "number": version + 1,
            "minorEdit" : True
            },
        'ancestors': ancestors
    }

    if LABELS:
        if 'metadata' not in page_json:
            page_json['metadata'] = {}

        labels = []
        for value in LABELS:
            labels.append({"name": value})

        page_json['metadata']['labels'] = labels

    response = session.put(url, data=json.dumps(page_json))

    # Check for errors
    try:
        response.raise_for_status()
    except requests.RequestException as err:
        LOGGER.error('err.response: %s', err)
        if response.status_code == 404:
            LOGGER.error('Error: Page not found. Check the following are correct:')
            LOGGER.error('\tSpace Key : %s', SPACE_KEY)
            LOGGER.error('\tOrganisation Name: %s', ORGNAME)
        else:
            LOGGER.error('Error: %d - %s', response.status_code, response.content)
        sys.exit(1)

    if response.status_code == 200:
        data = response.json()
        link = '%s%s' % (CONFLUENCE_API_URL, data[u'_links'][u'webui'])

        LOGGER.info("Page updated successfully.")
        LOGGER.info('URL: %s', link)

        if properties:
            LOGGER.info("Updating page content properties...")

            for key in properties:
                prop_url = '%s/property/%s' % (url, key)
                prop_json = {"key": key, "version": {"number": properties[key][u"version"]}, "value": properties[key][u"value"]}

                response = session.put(prop_url, data=json.dumps(prop_json))
                response.raise_for_status()

                if response.status_code == 200:
                    LOGGER.info("\tUpdated property %s", key)

        if GO_TO_PAGE:
            webbrowser.open(link)
    else:
        LOGGER.error("Page could not be updated.")


def get_attachment(page_id, filename):
    """
    Get page attachment

    :param page_id: confluence page id
    :param filename: attachment filename
    :return: attachment info in case of success, False otherwise
    """
    url = '%s/rest/api/content/%s/child/attachment?filename=%s' % (CONFLUENCE_API_URL, page_id, filename)

    session = requests.Session()
    if PA_TOKEN:
        session.headers.update({'Authorization': 'Bearer ' + PA_TOKEN})
    else:
        session.auth = (USERNAME, API_KEY)

    response = session.get(url)
    response.raise_for_status()
    data = response.json()

    if len(data[u'results']) >= 1:
        att_id = data[u'results'][0]['id']
        att_info = collections.namedtuple('AttachmentInfo', ['id'])
        attr_info = att_info(att_id)
        return attr_info

    return False


def upload_attachment(page_id, file, comment):
    """
    Upload an attachement

    :param page_id: confluence page id
    :param file: attachment file
    :param comment: attachment comment
    :return: boolean
    """
    if re.search('http.*', file):
        return False

    content_type = mimetypes.guess_type(file)[0]
    filename = os.path.basename(file)

    if not os.path.isfile(file):
        LOGGER.error('File %s cannot be found --> skip ', file)
        return False

    file_to_upload = {
        'comment': comment,
        'file': (filename, open(file, 'rb'), content_type, {'Expires': '0'})
    }

    attachment = get_attachment(page_id, filename)
    if attachment:
        url = '%s/rest/api/content/%s/child/attachment/%s/data' % (CONFLUENCE_API_URL, page_id, attachment.id)
    else:
        url = '%s/rest/api/content/%s/child/attachment/' % (CONFLUENCE_API_URL, page_id)

    session = requests.Session()
    if PA_TOKEN:
        session.headers.update({'Authorization': 'Bearer ' + PA_TOKEN})
    else:
        session.auth = (USERNAME, API_KEY)
    session.headers.update({'X-Atlassian-Token': 'no-check'})

    LOGGER.info('\tUploading attachment %s...', filename)

    response = session.post(url, files=file_to_upload)
    response.raise_for_status()

    return True


def main():
    """
    Main program

    :return:
    """
    LOGGER.info('\t\t----------------------------------')
    LOGGER.info('\t\tMarkdown to Confluence Upload Tool')
    LOGGER.info('\t\t----------------------------------\n\n')

    LOGGER.info('Markdown file:\t%s', MARKDOWN_FILE)
    LOGGER.info('Space Key:\t%s', SPACE_KEY)

    if TITLE:
        title = TITLE
    else:
        with open(MARKDOWN_FILE, 'r') as mdfile:
            title = mdfile.readline().lstrip('#').strip()
            mdfile.seek(0)

    LOGGER.info('Title:\t\t%s', title)

    with codecs.open(MARKDOWN_FILE, 'r', 'utf-8') as mdfile:
        html = mdfile.read()
        html = markdown.markdown(html, extensions=['tables', 'fenced_code', 'footnotes'])

    if not TITLE:
        html = '\n'.join(html.split('\n')[1:])

    if DETAILS:
        LOGGER.info('Generating page properties macro...')

        # Print 'page properties' macro on a page
        details = '''
          <ac:structured-macro ac:name="details">
            <ac:parameter ac:name="hidden">''' + str(DETAILS_VISIBILITY) + '''</ac:parameter>
            <ac:rich-text-body>
              <table>
                <tbody>'''

        for key in DETAILS:
            details += '<tr><th>' + key + '</th><td>' + DETAILS[key] + '</td></tr>'

        details += '''
                </tbody>
              </table>
            </ac:rich-text-body>
          </ac:structured-macro>'''

        html = details + html


    html = create_table_of_content(html)

    html = convert_info_macros(html)
    html = convert_comment_block(html)
    html = convert_code_block(html)
    html = convert_iframe_macros(html)

    if REMOVE_EMOJIES:
        html = remove_emojies(html)

    if CONTENTS:
        html = add_contents(html)

    html = process_refs(html)

    LOGGER.debug('html: %s', html)

    if SIMULATE:
        LOGGER.info("Simulate mode is active - stop processing here.")
        sys.exit(0)

    LOGGER.info('Checking if Atlas page exists...')
    page = get_page(title)

    if DELETE and page:
        delete_page(page.id)
        sys.exit(1)

    if ANCESTOR:
        parent_page = get_page(ANCESTOR)
        if parent_page:
            ancestors = [{'type': 'page', 'id': parent_page.id}]
        else:
            LOGGER.error('Error: Parent page does not exist: %s', ANCESTOR)
            sys.exit(1)
    else:
        ancestors = []

    if page:
        # Populate properties dictionary with updated property values
        properties = {}
        if PROPERTIES:
            for key in PROPERTIES:
                if key in page.properties:
                    properties[key] = {"key": key, "version": page.properties[key][u'version'][u'number'] + 1, "value": PROPERTIES[key]}
                else:
                    properties[key] = {"key": key, "version": 1, "value": PROPERTIES[key]}

        update_page(page.id, title, html, page.version, ancestors, properties, ATTACHMENTS)
    else:
        create_page(title, html, ancestors)

    LOGGER.info('Markdown Converter completed successfully.')


if __name__ == "__main__":
    main()
