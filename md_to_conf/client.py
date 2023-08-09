import logging
import sys
import os
import re
import json
import collections
import mimetypes
import urllib
import requests

LOGGER = logging.getLogger(__name__)


class ConfluenceApiClient:
    def __init__(
        self, confluence_api_url, username, api_key, space_key, editor_version
    ):
        self.user_name = username
        self.api_key = api_key
        self.confluence_api_url = confluence_api_url
        self.space_key = space_key
        self.space_id = ""
        self.editor_version = editor_version

    def get_session(self, retry=False, json=True):
        session = requests.Session()
        if retry:
            retry_max_requests = 5
            retry_backoff_factor = 0.1
            retry_status_forcelist = (404, 500, 501, 502, 503, 504)
            retry = requests.adapters.Retry(
                total=retry_max_requests,
                connect=retry_max_requests,
                read=retry_max_requests,
                backoff_factor=retry_backoff_factor,
                status_forcelist=retry_status_forcelist,
            )
            adapter = requests.adapters.HTTPAdapter(max_retries=retry)
            session.mount("http://", adapter)
            session.mount("https://", adapter)
        session.auth = (self.user_name, self.api_key)
        if json:
            session.headers.update({"Content-Type": "application/json"})
        return session

    def check_errors_and_get_json(self, response):
        # Check for errors
        try:
            response.raise_for_status()
        except requests.RequestException as err:
            LOGGER.error("err.response: %s", err)
            if response.status_code == 404:
                return {"error": "Not Found", "status_code": 404}
            else:
                LOGGER.error("Error: %d - %s", response.status_code, response.content)
                sys.exit(1)

        return {"status_code": response.status_code, "data": response.json()}

    def update_page(self, page_id, title, body, version, parent_id):
        """
        Update a page

        :param page_id: confluence page id
        :param title: confluence page title
        :param body: confluence page content
        :param version: confluence page version
        :param parent_id: confluence parentId
        :param attachments: confluence page attachments
        :return: None
        """
        LOGGER.info("Updating page...")

        url = "%s/api/v2/pages/%s" % (self.confluence_api_url, page_id)

        page_json = {
            "id": page_id,
            "type": "page",
            "title": title,
            "spaceId": "%s" % self.get_space_id(),
            "status": "current",
            "body": {"value": body, "representation": "storage"},
            "version": {"number": version + 1, "minorEdit": True},
            "parentId": "%s" % parent_id,
        }

        # if LABELS:
        #     if 'metadata' not in page_json:
        #         page_json['metadata'] = {}

        #     labels = []
        #     for value in LABELS:
        #         labels.append({"name": value})

        #     page_json['metadata']['labels'] = labels

        session = self.get_session()
        response = self.check_errors_and_get_json(
            session.put(url, data=json.dumps(page_json))
        )

        if response["status_code"] == 404:
            LOGGER.error("Error: Page not found. Check the following are correct:")
            LOGGER.error("\tSpace Key : %s", self.space_key)
            LOGGER.error("\tURL: %s", self.confluence_api_url)
            return False

        if response["status_code"] == 200:
            data = response["data"]
            link = "%s%s" % (self.confluence_api_url, data["_links"]["webui"])
            LOGGER.info("Page updated successfully.")
            LOGGER.info("URL: %s", link)
            return True
        else:
            LOGGER.error("Page could not be updated.")

    def get_space_id(self):
        """
        Retrieve the integer space ID for the current self.space_key

        """
        if self.space_id != "":
            return self.space_id

        url = "%s/api/v2/spaces?keys=%s" % (self.confluence_api_url, self.space_key)

        response = self.check_errors_and_get_json(self.get_session().get(url))

        if response["status_code"] == 404:
            LOGGER.error("Error: Space not found. Check the following are correct:")
            LOGGER.error("\tSpace Key : %s", self.space_key)
            LOGGER.error("\tURL: %s", self.confluence_api_url)
        else:
            data = response["data"]
            if len(data["results"]) >= 1:
                self.space_id = data["results"][0]["id"]

        return self.space_id

    def create_page(self, title, body, parent_id):
        """
        Create a new page

        :param title: confluence page title
        :param body: confluence page content
        :param parent_id: confluence parentId
        :return:
        """
        LOGGER.info("Creating page...")

        url = "%s/api/v2/pages" % self.confluence_api_url

        space_id = self.get_space_id()

        new_page = {
            "title": title,
            "spaceId": "%s" % space_id,
            "status": "current",
            "body": {"value": body, "representation": "storage"},
            "parentId": "%s" % parent_id,
            "metadata": {
                "properties": {
                    "editor": {"key": "editor", "value": "v%d" % self.editor_version}
                }
            },
        }

        LOGGER.debug("data: %s", json.dumps(new_page))

        response = self.check_errors_and_get_json(
            self.get_session().post(url, data=json.dumps(new_page))
        )

        if response["status_code"] == 200:
            data = response["data"]
            space_id = data["spaceId"]
            page_id = data["id"]
            version = data["version"]["number"]
            link = "%s%s" % (self.confluence_api_url, data["_links"]["webui"])

            LOGGER.info("Page created in SpaceId %s with ID: %s.", space_id, page_id)
            LOGGER.info("URL: %s", link)

            return {"id": page_id, "spaceId": space_id, "version": version}
        else:
            LOGGER.error("Could not create page.")
            return {"id": "", "spaceId": "", "version": ""}

    def delete_page(self, page_id):
        """
        Delete a page

        :param page_id: confluence page id
        :return: None
        """
        LOGGER.info("Deleting page...")
        url = "%s/api/v2/pages/%s" % (self.confluence_api_url, page_id)

        response = self.get_session().delete(url)
        response.raise_for_status()

        if response.status_code == 204:
            LOGGER.info("Page %s deleted successfully.", page_id)
        else:
            LOGGER.error("Page %s could not be deleted.", page_id)

    def get_page(self, title):
        """
        Retrieve page details by title

        :param title: page tile
        :return: Confluence page info
        """

        space_id = self.get_space_id()

        LOGGER.info("\tRetrieving page information: %s", title)
        url = "%s/api/v2/spaces/%s/pages?title=%s" % (
            self.confluence_api_url,
            space_id,
            urllib.parse.quote_plus(title),
        )

        response = self.check_errors_and_get_json(self.get_session(retry=True).get(url))
        if response["status_code"] == 404:
            LOGGER.error("Error: Page not found. Check the following are correct:")
            LOGGER.error("\tSpace Id : %s", space_id)
            LOGGER.error("\tURL: %s", self.confluence_api_url)
        else:
            data = response["data"]

            LOGGER.debug("data: %s", str(data))

            if len(data["results"]) >= 1:
                page_id = data["results"][0]["id"]
                version_num = data["results"][0]["version"]["number"]
                link = "%s%s" % (
                    self.confluence_api_url,
                    data["results"][0]["_links"]["webui"],
                )

                page_info = collections.namedtuple(
                    "PageInfo", ["id", "version", "link"]
                )
                page = page_info(page_id, version_num, link)
                return page

        return False

    def get_page_properties(self, page_id):
        """
        Retrieve page properties by page id

        :param page_id: pageId
        :return: Page Properties Collection
        """

        LOGGER.info("\tRetrieving page property information: %s", page_id)
        url = "%s/api/v2/pages/%s/properties" % (self.confluence_api_url, page_id)

        response = self.check_errors_and_get_json(self.get_session(retry=True).get(url))
        if response["status_code"] == 404:
            LOGGER.error("Error: Page not found. Check the following are correct:")
            LOGGER.error("\tPage Id : %s", page_id)
            LOGGER.error("\tURL: %s", self.confluence_api_url)
        else:
            data = response["data"]
            LOGGER.debug("property data: %s", str(data["results"]))

            return data["results"]

        return []

    def update_page_property(self, page_id, page_property):
        """
        Update page property by page id

        :param page_id: pageId
        :return: True if successful
        """

        property_json = {
            "page-id": page_id,
            "key": page_property["key"],
            "value": page_property["value"],
            "version": {"number": page_property["version"], "minorEdit": True},
        }

        if "id" in page_property:
            url = "%s/api/v2/pages/%s/properties/%s" % (
                self.confluence_api_url,
                page_id,
                page_property["id"],
            )
            property_json.update({"property-id": page_property["id"]})
            LOGGER.info(
                "Updating Property ID %s on Page %s: %s=%s",
                property_json["property-id"],
                page_id,
                property_json["key"],
                property_json["value"],
            )
            response = self.check_errors_and_get_json(
                self.get_session(retry=True).put(url, data=json.dumps(property_json))
            )
        else:
            url = "%s/api/v2/pages/%s/properties" % (self.confluence_api_url, page_id)
            LOGGER.info(
                "Adding Property to Page %s: %s=%s",
                page_id,
                property_json["key"],
                property_json["value"],
            )
            response = self.check_errors_and_get_json(
                self.get_session(retry=True).post(url, data=json.dumps(property_json))
            )

        if response["status_code"] != 200:
            LOGGER.error("Error: Page not found. Check the following are correct:")
            LOGGER.error("\tPage Id : %s", page_id)
            LOGGER.error("\tURL: %s", self.confluence_api_url)
            return False
        else:
            return True

        return []

    def get_attachment(self, page_id, filename):
        """
        Get page attachment

        :param page_id: confluence page id
        :param filename: attachment filename
        :return: attachment info in case of success, False otherwise
        """
        url = "%s/api/v2/pages/%s/attachments?filename=%s" % (
            self.confluence_api_url,
            page_id,
            filename,
        )

        response = self.get_session().get(url)
        response.raise_for_status()
        data = response.json()

        if len(data["results"]) >= 1:
            att_id = data["results"][0]["id"]
            att_info = collections.namedtuple("AttachmentInfo", ["id"])
            attr_info = att_info(att_id)
            return attr_info

        return False

    def upload_attachment(self, page_id, file, comment):
        """
        Upload an attachement

        :param page_id: confluence page id
        :param file: attachment file
        :param comment: attachment comment
        :return: boolean
        """
        if re.search("http.*", file):
            return False

        content_type = mimetypes.guess_type(file)[0]
        filename = os.path.basename(file)

        if not os.path.isfile(file):
            LOGGER.error("File %s cannot be found --> skip ", file)
            return False

        file_to_upload = {
            "comment": comment,
            "file": (filename, open(file, "rb"), content_type, {"Expires": "0"}),
        }

        attachment = self.get_attachment(page_id, filename)
        if attachment:
            url = "%s/rest/api/content/%s/child/attachment/%s/data" % (
                self.confluence_api_url,
                page_id,
                attachment.id,
            )
        else:
            url = "%s/rest/api/content/%s/child/attachment/" % (
                self.confluence_api_url,
                page_id,
            )

        session = self.get_session(json=False)
        session.headers.update({"X-Atlassian-Token": "no-check"})

        LOGGER.info("\tUploading attachment %s...", filename)

        response = session.post(url, files=file_to_upload)
        response.raise_for_status()

        return True
