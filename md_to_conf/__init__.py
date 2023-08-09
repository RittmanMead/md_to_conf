#!/usr/bin/env python3
"""
# Spydersoft Markdown to Confluence Tool
# --------------------------------------------------------------------------------------------------
# Based on Rittman Mead Markdown to Confluence Tool
# --------------------------------------------------------------------------------------------------
# Create or Update Atlas pages remotely using markdown files.
#
# --------------------------------------------------------------------------------------------------
"""

import logging
import sys
import os
import re
import codecs
import argparse
import markdown
from .client import ConfluenceApiClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - \
%(levelname)s - %(funcName)s [%(lineno)d] - \
%(message)s",
)
LOGGER = logging.getLogger(__name__)

# ArgumentParser to parse arguments and options
PARSER = argparse.ArgumentParser()
PARSER.add_argument(
    "markdownFile", help="Full path of the markdown file to convert and upload."
)
PARSER.add_argument(
    "spacekey",
    help="Confluence Space key for the page. If omitted, will use user space.",
)
PARSER.add_argument(
    "-u", "--username", help="Confluence username if $CONFLUENCE_USERNAME not set."
)
PARSER.add_argument(
    "-p", "--apikey", help="Confluence API key if $CONFLUENCE_API_KEY not set."
)
PARSER.add_argument(
    "-o",
    "--orgname",
    help="Confluence organisation if $CONFLUENCE_ORGNAME not set. "
    "e.g. https://XXX.atlassian.net/wiki"
    "If orgname contains a dot, considered as the fully qualified domain name."
    "e.g. https://XXX",
)
PARSER.add_argument(
    "-a", "--ancestor", help="Parent page under which page will be created or moved."
)
PARSER.add_argument(
    "-t",
    "--attachment",
    nargs="+",
    help="Attachment(s) to upload to page. Paths relative to the markdown file.",
)
PARSER.add_argument(
    "-c",
    "--contents",
    action="store_true",
    default=False,
    help="Use this option to generate a contents page.",
)
PARSER.add_argument(
    "-n",
    "--nossl",
    action="store_true",
    default=False,
    help="Use this option if NOT using SSL. Will use HTTP instead of HTTPS.",
)
PARSER.add_argument(
    "-d",
    "--delete",
    action="store_true",
    default=False,
    help="Use this option to delete the page instead of create it.",
)
PARSER.add_argument(
    "-l", "--loglevel", default="INFO", help="Use this option to set the log verbosity."
)
PARSER.add_argument(
    "-s",
    "--simulate",
    action="store_true",
    default=False,
    help="Use this option to only show conversion result.",
)
PARSER.add_argument(
    "-v",
    "--version",
    type=int,
    action="store",
    default=2,
    help="Version of confluence page (default is 2).",
)
PARSER.add_argument(
    "-mds",
    "--markdownsrc",
    action="store",
    default="default",
    choices=["default", "bitbucket"],
    help="Use this option to specify a markdown source "
    " (i.e. what processor this markdown was targeting). "
    "Possible values: bitbucket.",
)
PARSER.add_argument(
    "--label",
    action="append",
    dest="labels",
    default=[],
    help="A list of labels to set on the page.",
)
PARSER.add_argument(
    "--property",
    action="append",
    dest="properties",
    default=[],
    type=lambda kv: kv.split("="),
    help="A list of content properties to set on the page.",
)
PARSER.add_argument(
    "--title",
    action="store",
    dest="title",
    default=None,
    help="Set the title for the page, otherwise the title is "
    "going to be the first line in the markdown file",
)
PARSER.add_argument(
    "--remove-emojies",
    action="store_true",
    dest="remove_emojies",
    default=False,
    help="Remove emojies if there are any. This may be need if "
    "the database doesn't support emojies",
)

ARGS = PARSER.parse_args()

# Assign global variables
try:
    # Set log level
    LOGGER.setLevel(getattr(logging, ARGS.loglevel.upper(), None))

    MARKDOWN_FILE = ARGS.markdownFile
    SPACE_KEY = ARGS.spacekey
    USERNAME = os.getenv("CONFLUENCE_USERNAME", ARGS.username)
    API_KEY = os.getenv("CONFLUENCE_API_KEY", ARGS.apikey)
    ORGNAME = os.getenv("CONFLUENCE_ORGNAME", ARGS.orgname)
    ANCESTOR = ARGS.ancestor
    NOSSL = ARGS.nossl
    DELETE = ARGS.delete
    SIMULATE = ARGS.simulate
    VERSION = ARGS.version
    MARKDOWN_SOURCE = ARGS.markdownsrc
    LABELS = ARGS.labels
    PROPERTIES = dict(ARGS.properties)
    ATTACHMENTS = ARGS.attachment
    CONTENTS = ARGS.contents
    TITLE = ARGS.title
    REMOVE_EMOJIES = ARGS.remove_emojies

    if USERNAME is None:
        LOGGER.error("Error: Username not specified by environment variable or option.")
        sys.exit(1)

    if API_KEY is None:
        LOGGER.error("Error: API key not specified by environment variable or option.")
        sys.exit(1)

    if not os.path.exists(MARKDOWN_FILE):
        LOGGER.error("Error: Markdown file: %s does not exist.", MARKDOWN_FILE)
        sys.exit(1)

    if SPACE_KEY is None:
        SPACE_KEY = "~%s" % (USERNAME)

    if ORGNAME is not None:
        if ORGNAME.find(".") != -1:
            CONFLUENCE_API_URL = "https://%s" % ORGNAME
        else:
            CONFLUENCE_API_URL = "https://%s.atlassian.net/wiki" % ORGNAME
    else:
        LOGGER.error("Error: Org Name not specified by environment variable or option.")
        sys.exit(1)

    if NOSSL:
        CONFLUENCE_API_URL.replace("https://", "http://")

except Exception as err:
    LOGGER.error("\n\nException caught:\n%s ", err)
    LOGGER.error("\nFailed to process command line arguments. Exiting.")
    sys.exit(1)


def convert_comment_block(html):
    """
    Convert markdown code bloc to Confluence hidden comment

    :param html: string
    :return: modified html string
    """
    open_tag = "<ac:placeholder>"
    close_tag = "</ac:placeholder>"

    html = html.replace("<!--", open_tag).replace("-->", close_tag)

    return html


def create_table_of_content(html):
    """
    Check for the string '[TOC]' and replaces it the Confluence "Table of Content" macro

    :param html: string
    :return: modified html string
    """
    html = re.sub(
        r"<p>\[TOC\]</p>",
        '<p><ac:structured-macro ac:name="toc" ac:schema-version="1"/></p>',
        html,
        1,
    )

    return html


def convert_code_block(html):
    """
    Convert html code blocks to Confluence macros

    :param html: string
    :return: modified html string
    """
    code_blocks = re.findall(r"<pre><code.*?>.*?</code></pre>", html, re.DOTALL)
    if code_blocks:
        for tag in code_blocks:
            conf_ml = '<ac:structured-macro ac:name="code">'
            conf_ml = conf_ml + '<ac:parameter ac:name="theme">Midnight</ac:parameter>'
            conf_ml = (
                conf_ml + '<ac:parameter ac:name="linenumbers">true</ac:parameter>'
            )

            lang = re.search('code class="(.*)"', tag)
            if lang:
                lang = lang.group(1)
            else:
                lang = "none"

            conf_ml = (
                conf_ml + '<ac:parameter ac:name="language">' + lang + "</ac:parameter>"
            )
            content = re.search(
                r"<pre><code.*?>(.*?)</code></pre>", tag, re.DOTALL
            ).group(1)
            content = (
                "<ac:plain-text-body><![CDATA[" + content + "]]></ac:plain-text-body>"
            )
            conf_ml = conf_ml + content + "</ac:structured-macro>"
            conf_ml = conf_ml.replace("&lt;", "<").replace("&gt;", ">")
            conf_ml = conf_ml.replace("&quot;", '"').replace("&amp;", "&")

            html = html.replace(tag, conf_ml)

    return html


def remove_emojies(html):
    """
    Remove emojies if there are any

    :param html: string
    :return: modified html string
    """
    regrex_pattern = re.compile(
        pattern="["
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map symbols
        "\U0001F1E0-\U0001F1FF"  # flags (iOS)
        "]+",
        flags=re.UNICODE,
    )
    return regrex_pattern.sub(r"", html)


def convert_info_macros(html):
    """
    Converts html for info, note or warning macros

    :param html: html string
    :return: modified html string
    """
    info_tag = '<p><ac:structured-macro ac:name="info"><ac:rich-text-body><p>'
    note_tag = info_tag.replace("info", "note")
    warning_tag = info_tag.replace("info", "warning")
    close_tag = "</p></ac:rich-text-body></ac:structured-macro></p>"

    # Custom tags converted into macros
    html = html.replace("<p>~?", info_tag).replace("?~</p>", close_tag)
    html = html.replace("<p>~!", note_tag).replace("!~</p>", close_tag)
    html = html.replace("<p>~%", warning_tag).replace("%~</p>", close_tag)

    # Convert block quotes into macros
    quotes = re.findall("<blockquote>(.*?)</blockquote>", html, re.DOTALL)
    if quotes:
        for quote in quotes:
            note = re.search("^<.*>Note", quote.strip(), re.IGNORECASE)
            warning = re.search("^<.*>Warning", quote.strip(), re.IGNORECASE)

            if note:
                clean_tag = strip_type(quote, "Note")
                macro_tag = (
                    clean_tag.replace("<p>", note_tag)
                    .replace("</p>", close_tag)
                    .strip()
                )
            elif warning:
                clean_tag = strip_type(quote, "Warning")
                macro_tag = (
                    clean_tag.replace("<p>", warning_tag)
                    .replace("</p>", close_tag)
                    .strip()
                )
            else:
                macro_tag = (
                    quote.replace("<p>", info_tag).replace("</p>", close_tag).strip()
                )

            html = html.replace("<blockquote>%s</blockquote>" % quote, macro_tag)

    # Convert doctoc to toc confluence macro
    html = convert_doctoc(html)

    return html


def convert_doctoc(html):
    """
    Convert doctoc to confluence macro

    :param html: html string
    :return: modified html string
    """

    toc_tag = """<p>
    <ac:structured-macro ac:name="toc">
      <ac:parameter ac:name="printable">true</ac:parameter>
      <ac:parameter ac:name="style">disc</ac:parameter>
      <ac:parameter ac:name="maxLevel">7</ac:parameter>
      <ac:parameter ac:name="minLevel">1</ac:parameter>
      <ac:parameter ac:name="type">list</ac:parameter>
      <ac:parameter ac:name="outline">clear</ac:parameter>
      <ac:parameter ac:name="include">.*</ac:parameter>
    </ac:structured-macro>
    </p>"""

    html = re.sub(
        "\<\!\-\- START doctoc.*END doctoc \-\-\>", toc_tag, html, flags=re.DOTALL
    )

    return html


def strip_type(tag, tagtype):
    """
    Strips Note or Warning tags from html in various formats

    :param tag: tag name
    :param tagtype: tag type
    :return: modified tag
    """
    tag = re.sub("%s:\s" % tagtype, "", tag.strip(), re.IGNORECASE)
    tag = re.sub("%s\s:\s" % tagtype, "", tag.strip(), re.IGNORECASE)
    tag = re.sub("<.*?>%s:\s<.*?>" % tagtype, "", tag, re.IGNORECASE)
    tag = re.sub("<.*?>%s\s:\s<.*?>" % tagtype, "", tag, re.IGNORECASE)
    tag = re.sub("<(em|strong)>%s:<.*?>\s" % tagtype, "", tag, re.IGNORECASE)
    tag = re.sub("<(em|strong)>%s\s:<.*?>\s" % tagtype, "", tag, re.IGNORECASE)
    tag = re.sub("<(em|strong)>%s<.*?>:\s" % tagtype, "", tag, re.IGNORECASE)
    tag = re.sub("<(em|strong)>%s\s<.*?>:\s" % tagtype, "", tag, re.IGNORECASE)
    string_start = re.search("<.*?>", tag)
    tag = upper_chars(tag, [string_start.end()])
    return tag


def upper_chars(string, indices):
    """
    Make characters uppercase in string

    :param string: string to modify
    :param indices: character indice to change to uppercase
    :return: uppercased string
    """
    upper_string = "".join(
        c.upper() if i in indices else c for i, c in enumerate(string)
    )
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
    slug_string = re.sub(r"<[^>]+>", "", slug_string)

    # Remove html code like '&amp;'
    slug_string = re.sub(r"&[a-z]+;", "", slug_string)

    # Replace all spaces ( ) with dash (-)
    slug_string = re.sub(r"[ ]", "-", slug_string)

    # Remove all special chars, except for dash (-)
    slug_string = re.sub(r"[^a-zA-Z0-9-]", "", slug_string)
    return slug_string


def process_refs(html):
    """
    Process references

    :param html: html string
    :return: modified html string
    """
    refs = re.findall("\n(\[\^(\d)\].*)|<p>(\[\^(\d)\].*)", html)

    if refs:
        for ref in refs:
            if ref[0]:
                full_ref = ref[0].replace("</p>", "").replace("<p>", "")
                ref_id = ref[1]
            else:
                full_ref = ref[2]
                ref_id = ref[3]

            full_ref = full_ref.replace("</p>", "").replace("<p>", "")
            html = html.replace(full_ref, "")
            href = re.search('href="(.*?)"', full_ref).group(1)

            superscript = '<a id="test" href="%s"><sup>%s</sup></a>' % (href, ref_id)
            html = html.replace("[^%s]" % ref_id, superscript)

    return html


# Scan for images and upload as attachments if found
def add_images(page_id, html, client):
    """
    Scan for images and upload as attachments if found

    :param page_id: Confluence page id
    :param html: html string
    :return: html with modified image reference
    """
    source_folder = os.path.dirname(os.path.abspath(MARKDOWN_FILE))

    for tag in re.findall("<img(.*?)\/>", html):
        rel_path = re.search('src="(.*?)"', tag).group(1)
        alt_text = re.search('alt="(.*?)"', tag).group(1)
        abs_path = os.path.join(source_folder, rel_path)
        basename = os.path.basename(rel_path)
        client.upload_attachment(page_id, abs_path, alt_text)
        if re.search("http.*", rel_path) is None:
            if CONFLUENCE_API_URL.endswith("/wiki"):
                html = html.replace(
                    "%s" % (rel_path),
                    "/wiki/download/attachments/%s/%s" % (page_id, basename),
                )
            else:
                html = html.replace(
                    "%s" % (rel_path),
                    "/download/attachments/%s/%s" % (page_id, basename),
                )
    return html


def add_contents(html):
    """
    Add contents page

    :param html: html string
    :return: modified html string
    """
    contents_markup = (
        '<ac:structured-macro ac:name="toc">\n<ac:parameter ac:name="printable">'
        'true</ac:parameter>\n<ac:parameter ac:name="style">disc</ac:parameter>'
    )
    contents_markup = (
        contents_markup + '<ac:parameter ac:name="maxLevel">5</ac:parameter>\n'
        '<ac:parameter ac:name="minLevel">1</ac:parameter>'
    )
    contents_markup = (
        contents_markup + '<ac:parameter ac:name="class">rm-contents</ac:parameter>\n'
        '<ac:parameter ac:name="exclude"></ac:parameter>\n'
        '<ac:parameter ac:name="type">list</ac:parameter>'
    )
    contents_markup = (
        contents_markup + '<ac:parameter ac:name="outline">false</ac:parameter>\n'
        '<ac:parameter ac:name="include"></ac:parameter>\n'
        "</ac:structured-macro>"
    )

    html = contents_markup + "\n" + html
    return html


def add_attachments(page_id, files, client):
    """
    Add attachments for an array of files

    :param page_id: Confluence page id
    :param files: list of files to attach to the given Confluence page
    :return: None
    """
    source_folder = os.path.dirname(os.path.abspath(MARKDOWN_FILE))

    if files:
        for file in files:
            client.upload_attachment(page_id, os.path.join(source_folder, file), "")


def add_local_refs(page_id, space_id, title, html):
    """
    Convert local links to correct confluence local links

    :param page_title: string
    :param page_id: integer
    :param html: string
    :return: modified html string
    """

    ref_prefixes = {"default": "#", "bitbucket": "#markdown-header-"}
    ref_postfixes = {"default": "_%d", "bitbucket": "_%d"}

    # We ignore local references in case of unknown or unspecified markdown source
    if MARKDOWN_SOURCE not in ref_prefixes or MARKDOWN_SOURCE not in ref_postfixes:
        LOGGER.warning(
            "Local references weren"
            "t processed because "
            "--markdownsrc wasn"
            "t set or specified source isn"
            "t supported"
        )
        return html

    ref_prefix = ref_prefixes[MARKDOWN_SOURCE]
    ref_postfix = ref_postfixes[MARKDOWN_SOURCE]

    LOGGER.info("Converting confluence local links...")

    headers = re.findall(r"<h\d+>(.*?)</h\d+>", html, re.DOTALL)
    if headers:
        headers_map = {}
        headers_count = {}

        for header in headers:
            key = ref_prefix + slug(header, True)

            if VERSION == 1:
                value = re.sub(r"(<.+?>|[ ])", "", header)
            if VERSION == 2:
                value = slug(header, False)

            if key in headers_map:
                alt_count = headers_count[key]

                alt_key = key + (ref_postfix % alt_count)
                alt_value = value + (".%s" % alt_count)

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

                result_ref = headers_map.get(ref)

                if result_ref:
                    base_uri = "%s/spaces/%s/pages/%s/%s" % (
                        CONFLUENCE_API_URL,
                        space_id,
                        page_id,
                        "+".join(title.split()),
                    )
                    if VERSION == 1:
                        replacement_uri = "%s#%s-%s" % (
                            base_uri,
                            "".join(title.split()),
                            result_ref,
                        )
                        replacement = (
                            '<ac:link ac:anchor="%s">'
                            '<ac:plain-text-link-body>'
                            '<![CDATA[%s]]></ac:plain-text-link-body></ac:link>'
                            % (result_ref, re.sub(r"( *<.+?> *)", " ", alt))
                        )
                    if VERSION == 2:
                        replacement_uri = "%s#%s" % (base_uri, result_ref)
                        replacement = '<a href="%s" title="%s">%s</a>' % (
                            replacement_uri,
                            alt,
                            alt,
                        )

                    html = html.replace(link, replacement)

    return html


def get_html_from_markdown(markdown_file):

    with codecs.open(markdown_file, "r", "utf-8") as mdfile:
        markdown_content = mdfile.read()
        html = markdown.markdown(
            markdown_content, extensions=["tables", "fenced_code", "footnotes"]
        )

    if not TITLE:
        html = "\n".join(html.split("\n")[1:])

    html = create_table_of_content(html)
    html = convert_info_macros(html)
    html = convert_comment_block(html)
    html = convert_code_block(html)

    if REMOVE_EMOJIES:
        html = remove_emojies(html)

    if CONTENTS:
        html = add_contents(html)

    html = process_refs(html)


def main():
    """
    Main program

    :return:
    """

    LOGGER.info("\t\t----------------------------------")
    LOGGER.info("\t\tMarkdown to Confluence Upload Tool")
    LOGGER.info("\t\t----------------------------------\n\n")

    LOGGER.info("Markdown file:\t%s", MARKDOWN_FILE)
    LOGGER.info("Space Key:\t%s", SPACE_KEY)

    client = ConfluenceApiClient(
        CONFLUENCE_API_URL, USERNAME, API_KEY, SPACE_KEY, VERSION
    )

    if TITLE:
        title = TITLE
    else:
        with open(MARKDOWN_FILE, "r") as mdfile:
            title = mdfile.readline().lstrip("#").strip()
            mdfile.seek(0)

    LOGGER.info("Title:\t\t%s", title)

    html = get_html_from_markdown(MARKDOWN_FILE)

    LOGGER.debug("html: %s", html)

    if SIMULATE:
        LOGGER.info("Simulate mode is active - stop processing here.")
        sys.exit(0)

    LOGGER.info("Checking if Atlas page exists...")
    page = client.get_page(title)

    if DELETE and page:
        client.delete_page(page.id)
        sys.exit(1)

    if ANCESTOR:
        parent_page = client.get_page(ANCESTOR)
        if parent_page:
            parent_page_id = parent_page.id
        else:
            LOGGER.error("Error: Parent page does not exist: %s", ANCESTOR)
            sys.exit(1)
    else:
        parent_page_id = 0

    if not page:
        page = client.create_page(title, html, parent_page_id)
        page_id = page["id"]
        page_version = page["version"]
        space_id = page["space_id"]
    else:
        page_id = page.id
        page_version = page.version
        space_id = page.spaceId

    if ATTACHMENTS:
        add_attachments(page_id, ATTACHMENTS, client)

    properties = client.get_page_properties(page_id)
    properties_for_update = []
    for existingProp in properties:
        # Change the editor version
        if existingProp["key"] == "editor" and existingProp["value"] != (
            "v%d" % VERSION
        ):
            properties_for_update.append(
                {
                    "key": "editor",
                    "version": existingProp["version"]["number"] + 1,
                    "value": ("v%d" % VERSION),
                    "id": existingProp["id"],
                }
            )

    if PROPERTIES:
        for key in PROPERTIES:
            found = False
            for existingProp in properties:
                if existingProp["key"] == key:
                    properties_for_update.append(
                        {
                            "key": key,
                            "version": existingProp["version"]["number"] + 1,
                            "value": PROPERTIES[key],
                            "id": existingProp["id"],
                        }
                    )
                    found = True
            if not found:
                properties_for_update.append(
                    {"key": key, "version": 1, "value": PROPERTIES[key]}
                )

    html = add_images(page_id, html, client)
    # Add local references
    html = add_local_refs(page_id, space_id, title, html)

    client.update_page(page_id, title, html, page_version, parent_page_id)
    if properties_for_update and len(properties_for_update) > 0:
        LOGGER.info("Updating %s page content properties..." % len(properties))

        for prop in properties_for_update:
            client.update_page_property(page_id, prop)

    LOGGER.info("Markdown Converter completed successfully.")


if __name__ == "__main__":
    main()
