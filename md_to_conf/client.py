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
        self.space_id = -1
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

    def update_page(self, page_id: int, title, body, version, parent_id):
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

        url = "%s/api/v2/pages/%d" % (self.confluence_api_url, page_id)

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
        if self.space_id > -1:
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
                self.space_id = int(data["results"][0]["id"])

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
            "spaceId": "%d" % space_id,
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
            space_id = int(data["spaceId"])
            page_id = int(data["id"])
            version = data["version"]["number"]
            link = "%s%s" % (self.confluence_api_url, data["_links"]["webui"])

            LOGGER.info("Page created in SpaceId %d with ID: %d.", space_id, page_id)
            LOGGER.info("URL: %s", link)

            page_info = collections.namedtuple(
                "PageInfo", ["id", "spaceId", "version", "link"]
            )
            return page_info(page_id, space_id, version, link)
        else:
            LOGGER.error("Could not create page.")
            return {"id": 0, "spaceId": 0, "version": ""}

    def delete_page(self, page_id: int):
        """
        Delete a page

        :param page_id: confluence page id
        :return: None
        """
        LOGGER.info("Deleting page...")
        url = "%s/api/v2/pages/%d" % (self.confluence_api_url, page_id)

        response = self.get_session().delete(url)
        response.raise_for_status()

        if response.status_code == 204:
            LOGGER.info("Page %d deleted successfully.", page_id)
        else:
            LOGGER.error("Page %d could not be deleted.", page_id)

    def get_page(self, title):
        """
        Retrieve page details by title

        :param title: page tile
        :return: Confluence page info
        """

        space_id = self.get_space_id()

        LOGGER.info("\tRetrieving page information: %s", title)
        url = "%s/api/v2/spaces/%d/pages?title=%s" % (
            self.confluence_api_url,
            space_id,
            urllib.parse.quote_plus(title),
        )

        response = self.check_errors_and_get_json(self.get_session(retry=True).get(url))
        if response["status_code"] == 404:
            LOGGER.error("Error: Page not found. Check the following are correct:")
            LOGGER.error("\tSpace Id : %d", space_id)
            LOGGER.error("\tURL: %s", self.confluence_api_url)
        else:
            data = response["data"]

            LOGGER.debug("data: %s", str(data))

            if len(data["results"]) >= 1:
                page_id = int(data["results"][0]["id"])
                space_id = int(data["results"][0]["spaceId"])
                version_num = data["results"][0]["version"]["number"]
                link = "%s%s" % (
                    self.confluence_api_url,
                    data["results"][0]["_links"]["webui"],
                )

                page_info = collections.namedtuple(
                    "PageInfo", ["id", "spaceId", "version", "link"]
                )
                page = page_info(page_id, space_id, version_num, link)
                return page

        return False

    def get_page_properties(self, page_id: int):
        """
        Retrieve page properties by page id

        :param page_id: pageId
        :return: Page Properties Collection
        """

        LOGGER.info("\tRetrieving page property information: %d", page_id)
        url = "%s/api/v2/pages/%d/properties" % (self.confluence_api_url, page_id)

        response = self.check_errors_and_get_json(self.get_session(retry=True).get(url))
        if response["status_code"] == 404:
            LOGGER.error("Error: Page not found. Check the following are correct:")
            LOGGER.error("\tPage Id : %d", page_id)
            LOGGER.error("\tURL: %s", self.confluence_api_url)
        else:
            data = response["data"]
            LOGGER.debug("property data: %s", str(data["results"]))

            return data["results"]

        return []

    def update_page_property(self, page_id: int, page_property):
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
            url = "%s/api/v2/pages/%d/properties/%s" % (
                self.confluence_api_url,
                page_id,
                page_property["id"],
            )
            property_json.update({"property-id": page_property["id"]})
            LOGGER.info(
                "Updating Property ID %s on Page %d: %s=%s",
                property_json["property-id"],
                page_id,
                property_json["key"],
                property_json["value"],
            )
            response = self.check_errors_and_get_json(
                self.get_session(retry=True).put(url, data=json.dumps(property_json))
            )
        else:
            url = "%s/api/v2/pages/%d/properties" % (self.confluence_api_url, page_id)
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
            LOGGER.error("\tPage Id : %d", page_id)
            LOGGER.error("\tURL: %s", self.confluence_api_url)
            return False
        else:
            return True

        return []

    def get_attachment(self, page_id: int, filename):
        """
        Get page attachment

        :param page_id: confluence page id
        :param filename: attachment filename
        :return: attachment info in case of success, False otherwise
        """
        url = "%s/api/v2/pages/%d/attachments?filename=%s" % (
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

    def upload_attachment(self, page_id: int, file, comment):
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
            url = "%s/rest/api/content/%d/child/attachment/%s/data" % (
                self.confluence_api_url,
                page_id,
                attachment.id,
            )
        else:
            url = "%s/rest/api/content/%d/child/attachment/" % (
                self.confluence_api_url,
                page_id,
            )

        session = self.get_session(json=False)
        session.headers.update({"X-Atlassian-Token": "no-check"})

        LOGGER.info("\tUploading attachment %s...", filename)

        response = session.post(url, files=file_to_upload)
        response.raise_for_status()

        return True

    def get_label_info(self, label_name: str):
        """
        Get label information for the given label name

        :param label_name: pageId
        :return: LabelInfo.  If not found, labelInfo will be 0
        """

        LOGGER.debug("\tRetrieving label information: %s", label_name)
        url = "%s/rest/api/label?name=%s" % (
            self.confluence_api_url,
            urllib.parse.quote_plus(label_name),
        )

        response = self.check_errors_and_get_json(self.get_session().get(url))

        label_info = collections.namedtuple(
            "LabelInfo", ["id", "name", "prefix", "label"]
        )
        data = response["data"]["label"]
        if response["status_code"] == 404:
            label = label_info(0, "", "", "")
        else:
            label = label_info(
                int(data["id"]),
                data["name"],
                data["prefix"],
                data["label"],
            )

        return label

    def add_label(self, page_id: int, label_name: str):
        label_info = self.get_label_info(label_name)
        if label_info.id > 0:
            prefix = label_info.prefix
        else:
            prefix = "global"

        add_label_json = {"prefix": prefix, "name": label_name}

        url = "%s/rest/api/content/%d/label" % (self.confluence_api_url, page_id)

        response = self.get_session().post(url, data=json.dumps(add_label_json))
        response.raise_for_status()
        return True

    def update_labels(self, page_id: int, labels):
        """
        Update labels on given page Id

        :param page_id: pageId
        :param labels: labels to be added
        :return: True if successful
        """

        LOGGER.info("\tRetrieving page property information: %d", page_id)
        url = "%s/api/v2/pages/%d/labels" % (self.confluence_api_url, page_id)

        response = self.check_errors_and_get_json(self.get_session(retry=True).get(url))
        if response["status_code"] == 404:
            LOGGER.error(
                "Error: Error finding existing labels. Check the following are correct:"
            )
            LOGGER.error("\tPage Id : %d", page_id)
            LOGGER.error("\tURL: %s", self.confluence_api_url)
            return False

        data = response["data"]
        for label in labels:
            found = False
            for existingLabel in data["results"]:
                if label == existingLabel["name"]:
                    found = True

            if not found:
                LOGGER.info("Adding Label '%s' to Page Id %d", label, page_id)
                self.add_label(page_id, label)

            LOGGER.debug("property data: %s", str(data["results"]))

        return data["results"]
