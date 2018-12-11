import SimpleHTTPServer
import SocketServer
import logging

import json

PORT = 8081

def update_index(status):
	
	# open & update the index.html file
	with open('index.html', 'r') as f:
		lines = f.readlines()

	src = '-'.join(str(status['src']).split('-')[-2:])
	with open('index.html', 'w') as f:

		for line in lines:

			if 'last update' in line:
				line = ("<p>last update : %s</p>\n" % (str(status['time'])))

			if src in line:

				tr = ("<tr><td>%s</td>" % (src))
				for cat in ['iperf3', 'ntp', 'gps', 'cpu', 'bitrate']:
					if cat not in status:
						tr += """<td><font color="orange">n/a</td>"""
					elif status[cat] != 'ok':
						tr += """<td><font color="red">bad</td>"""
					else:
						tr += """<td><font color="green">ok</td>"""

				tr += '</tr>\n'
				line = tr

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
