# md_to_conf.py

A very hacky script to import a named markdown document into Confluence. It handles inline images as well as code blocks. 

## Setup

To use it, set your username/password as environment variables: 

	export CONFLUENCE_USERNAME='Fred.Flinstone'
	export CONFLUENCE_PASSWORD='abc123'

If you use Google Apps to signin to Confluence, you can still have a username & password for your Confluence account. Just logout and follow the "Unable to access your account?" link from the signin page, which lets you set/retrieve a username and password.

You also need to set the organisation name that is used in the subdomain. So if your Confluence page is https://acme.atlassian.net/wiki/, you'd set: 

	export CONFLUENCE_ORGNAME='acme'

## Use

Then invoke the script passing the path of the document to import as the first argument

	./md_to_conf.py "foo/bar/path with spaces.md"

Optionally, you can pass the spacekey in which to store the document as the as the second argument. 

	./md_to_conf.py "foo/bar/path with spaces.md" INF

If you don't specify the spacekey the script attempts to use your personal space, and exists if one does not exist. 

