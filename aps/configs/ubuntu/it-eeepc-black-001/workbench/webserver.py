import SimpleHTTPServer
import SocketServer
import logging
import os
import json

PORT = 8081

HTML_FILE=('%s/workbench/wifi-vehicles/aps/configs/ubuntu/it-eeepc-black-001/workbench/index.html' % (os.environ['HOME']))

def update_index(status):
	
	# open & update the index.html file
	with open(HTML_FILE, 'r') as f:
		lines = f.readlines()

	cats = []
	if status['mode'] == 'backbone':
		cats = ['iperf3', 'ntp', 'cpu', 'batt', 'cbt']
	else:
		cats = ['iperf3', 'ntp', 'cpu', 'batt', 'gps', 'bitrate']

	src = '-'.join(str(status['src']).split('-')[-2:])
	with open(HTML_FILE, 'w') as f:

		for line in lines:

			if 'last update' in line:
				line = ("<p>last update : %s</p>\n" % (str(status['time'])))

			if src in line:

				tr = ("<tr><td>%s</td>" % (src))
				for cat in cats:
					if cat not in status:
						tr += """<td><font color="orange">n/a</td>"""
					elif status[cat] == 'bad':
						tr += """<td><font color="red">bad</td>"""
					elif status[cat] == 'ok':
						tr += """<td><font color="green">ok</td>"""
					else:
						tr += ("""<td><font color="black">%s</td>""" % (status[cat]))

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
