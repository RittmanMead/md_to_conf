import logging
import re
import codecs
import markdown

LOGGER = logging.getLogger(__name__)


class MarkdownConverter:
    def __init__(self, md_file, api_url, md_source, editor_version):
        self.md_file = md_file
        self.api_url = api_url
        self.md_source = md_source
        self.editor_version = editor_version

    def get_html_from_markdown(
        self, has_title=False, remove_emojies=False, add_contents=False
    ):
        with codecs.open(self.md_file, "r", "utf-8") as mdfile:
            markdown_content = mdfile.read()
            html = markdown.markdown(
                markdown_content, extensions=["tables", "fenced_code", "footnotes"]
            )

        if not has_title:
            html = "\n".join(html.split("\n")[1:])

        html = self.create_table_of_content(html)
        html = self.convert_info_macros(html)
        html = self.convert_comment_block(html)
        html = self.convert_code_block(html)

        if remove_emojies:
            html = self.remove_emojies(html)

        if add_contents:
            html = self.add_contents(html)

        html = self.process_refs(html)
        return html

    def convert_comment_block(self, html):
        """
        Convert markdown code bloc to Confluence hidden comment

        :param html: string
        :return: modified html string
        """
        open_tag = "<ac:placeholder>"
        close_tag = "</ac:placeholder>"
        html = html.replace("<!--", open_tag).replace("-->", close_tag)
        return html

    def create_table_of_content(self, html):
        """
        Check for the string '[TOC]' and replaces it the
        Confluence "Table of Content" macro

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

    def convert_code_block(self, html):
        """
        Convert html code blocks to Confluence macros

        :param html: string
        :return: modified html string
        """
        code_blocks = re.findall(r"<pre><code.*?>.*?</code></pre>", html, re.DOTALL)
        if code_blocks:
            for tag in code_blocks:
                conf_ml = '<ac:structured-macro ac:name="code">'
                conf_ml = (
                    conf_ml + '<ac:parameter ac:name="theme">Midnight</ac:parameter>'
                )
                conf_ml = (
                    conf_ml + '<ac:parameter ac:name="linenumbers">true</ac:parameter>'
                )

                lang = re.search('code class="(.*)"', tag)
                if lang:
                    lang = lang.group(1)
                else:
                    lang = "none"

                conf_ml = (
                    conf_ml
                    + '<ac:parameter ac:name="language">'
                    + lang
                    + "</ac:parameter>"
                )
                content = re.search(
                    r"<pre><code.*?>(.*?)</code></pre>", tag, re.DOTALL
                ).group(1)
                content = (
                    "<ac:plain-text-body><![CDATA["
                    + content
                    + "]]></ac:plain-text-body>"
                )
                conf_ml = conf_ml + content + "</ac:structured-macro>"
                conf_ml = conf_ml.replace("&lt;", "<").replace("&gt;", ">")
                conf_ml = conf_ml.replace("&quot;", '"').replace("&amp;", "&")

                html = html.replace(tag, conf_ml)

        return html

    def remove_emojies(self, html):
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

    def convert_info_macros(self, html):
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
                    clean_tag = self.strip_type(quote, "Note")
                    macro_tag = (
                        clean_tag.replace("<p>", note_tag)
                        .replace("</p>", close_tag)
                        .strip()
                    )
                elif warning:
                    clean_tag = self.strip_type(quote, "Warning")
                    macro_tag = (
                        clean_tag.replace("<p>", warning_tag)
                        .replace("</p>", close_tag)
                        .strip()
                    )
                else:
                    macro_tag = (
                        quote.replace("<p>", info_tag)
                        .replace("</p>", close_tag)
                        .strip()
                    )

                html = html.replace("<blockquote>%s</blockquote>" % quote, macro_tag)

        # Convert doctoc to toc confluence macro
        html = self.convert_doctoc(html)

        return html

    def convert_doctoc(self, html):
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

    def strip_type(self, tag, tagtype):
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
        tag = self.upper_chars(tag, [string_start.end()])
        return tag

    def upper_chars(self, string, indices):
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

    def slug(self, string, lowercase):
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

    def process_refs(self, html):
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

                superscript = '<a id="test" href="%s"><sup>%s</sup></a>' % (
                    href,
                    ref_id,
                )
                html = html.replace("[^%s]" % ref_id, superscript)

        return html

    # Scan for images and upload as attachments if found

    def add_contents(self, html):
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
            contents_markup
            + '<ac:parameter ac:name="class">rm-contents</ac:parameter>\n'
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
