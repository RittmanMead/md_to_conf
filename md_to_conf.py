#!/usr/bin/python
#
# @rmoff 20140330
#
# "A Hack But It Works"
#----------------------------------------
#
# This will import specified Markdown file into Confluence
#
# It uses [depreciated] XMLRPC API for Confluence. Supports inline images and code blocks. 
#
#-----------------------------------------
#
# TODO:
#   Put some proper structure in, not a dirty mess of indented if statements.
#   Convert to use REST API?
#
#
import  sys,os,markdown,mimetypes,codecs
from xmlrpclib import Server,Binary
username=os.getenv('CONFLUENCE_USERNAME', 'UNSET')
password=os.getenv('CONFLUENCE_PASSWORD', 'UNSET')
orgname=os.getenv('CONFLUENCE_ORGNAME', 'UNSET')
if (username=='UNSET' or password=='UNSET'):
	print '\nConfluence username/password not found.\n\n\t==> Please set CONFLUENCE_USERNAME and CONFLUENCE_PASSWORD environment variables and try again.'
	sys.exit(2)
if orgname=='UNSET':
	print '\nConfluence orgname not set.   (https://xxxx.atlassian.net/wiki/)\n\n\t==> Please set CONFLUENCE_ORGNAME environment variable and try again.'
	sys.exit(2)
if len(sys.argv)<2:
	print '\n\t\n\tError: Filename missing. Program aborts. Specify the full path of the file to import as the first commandline argument.\n\n'
else:
	markdown_file_to_import=sys.argv[1]
	if os.path.exists(markdown_file_to_import):
		if len(sys.argv)>2:
			spacekey=sys.argv[2]
		else:
			spacekey='~%s' % (username)
		headers = {'Accept':'application/json'}
		s=Server("https://%s.atlassian.net/wiki/rpc/xmlrpc"%(orgname))
		conf_token = s.confluence2.login(username,password)

		try:
			space=s.confluence2.getSpace(conf_token,spacekey)
			print '\n\tPage will be added to space: %s' % space['name'] 
		except:
			print 'Space %s not found\n\tEither create a Personal Space, or specify a spacekey (eg INF) as the second commandline argument.' % (spacekey)
			sys.exit(1)

		source_folder=os.path.dirname(markdown_file_to_import)
		markdown_basename=os.path.basename(markdown_file_to_import)

		# Necessary to handle unicode
		with codecs.open(markdown_file_to_import,'r','utf-8') as f:
		    html=markdown.markdown(f.read())

		"""with open(markdown_file_to_import) as f:
		    html=markdown.markdown(f.read())
		    title=f.name
		"""

		# Build the new page
		# NB the API doesn't honour created, modified, creator, modifier
		conf_page_data = {}
		conf_page_data['space'] = spacekey
		title=markdown_basename
		conf_page_data['title'] = title
		# Code block
		# replace <pre><code> with code macro
		html=html.replace('<pre><code>','<ac:structured-macro ac:name="code"><ac:parameter ac:name="theme">Midnight</ac:parameter><ac:plain-text-body><![CDATA[').replace('</code></pre>',']]></ac:plain-text-body></ac:structured-macro>')
		conf_page_data['content'] = html

		try: 
			# Create page
			conf_page = s.confluence2.storePage(conf_token, conf_page_data)
			print '\nConfluence page created:\n\t%s\n\thttps://%s.atlassian.net/wiki/pages/viewpage.action?pageId=%s' % (conf_page['title'],orgname,conf_page['id'])

			#
			if (conf_page_data['content'].find('<img')>0):
				for img in conf_page_data['content'].split('<img')[1:]:
					img_rel_path=img.split('src="')[1].split('"')[0]
					img_basename=os.path.basename(img_rel_path)
					img_abs_path=os.path.join(source_folder,img_rel_path)
					with open(img_abs_path,'rb') as i:
						image_file=i.read()
					conf_attachment={}
					conf_attachment['fileName']=img_basename
					conf_attachment['contentType']=mimetypes.guess_type(img_abs_path)[0]
					conf_attachment = s.confluence2.addAttachment(conf_token,conf_page['id'],conf_attachment,Binary(image_file))
					print '\t\tAdded inline image: %s' % (img_basename)
					conf_page['content']=conf_page['content'].replace('%s'%(img_rel_path),'/wiki/download/attachments/%s/%s'%(conf_page['id'],img_basename))
					pageupdateoptions={"versionComment":"Fix img src path for %s"%(img_basename),"minorEdit":True}
					conf_page=s.confluence2.updatePage(conf_token,conf_page,pageupdateoptions)
		except Exception, err:
			print 'Failed:\n%s'%(err)
	else:
		print 'Input file not specified, or does not exist:\n%s' % (markdown_file_to_import)
