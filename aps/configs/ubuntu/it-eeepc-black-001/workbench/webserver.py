import SimpleHTTPServer
import SocketServer
import logging

import json

PORT = 8081

def update_index(status):

	# status line to print
	status_str = ''
	for cat in ['iperf3', 'ntp', 'cpu', 'gps']:
		if status[cat] != 'ok':
			status_str += ('%s,' % (cat))

	# open & update the index.html file
	with open('index.html', 'r') as f:
		lines = f.readlines()

	print(lines)
	print(status)

	src = '-'.join(str(status['src']).split('-')[-2:])
	print(src)
	with open('index.html', 'w') as f:

		for line in lines:

			if 'last update' in line:
				line = ("<p>last update : %s</p>\n" % (str(status['time'])))

			if src in line:
				if status_str != '':
					line = ("""<p><font color="red" size="16">%s : BAD (%s)</font></p>\n""" % (src, status_str))
				else:
					line = ("""<p><font color="green" size="16">%s : OK</font></p>\n""" % (src))

			f.write(line)

class myHandler(SimpleHTTPServer.SimpleHTTPRequestHandler):

	def _set_response(self):
		self.send_response(200)
		self.send_header('Content-type', 'text/html')
		self.end_headers()

	# handler for POSTs
	def do_POST(self):

		content_length = int(self.headers.getheader('content-length', 0))
		post_data = self.rfile.read(content_length)
		print("POST request,\nPath: %s\nHeaders:\n%s\n\nBody:\n%s\n" % (str(self.path), str(self.headers), post_data))

		update_index(json.loads(post_data))

Handler = myHandler
httpd = SocketServer.TCPServer(("", PORT), Handler)

print "serving at port", PORT
httpd.serve_forever()
