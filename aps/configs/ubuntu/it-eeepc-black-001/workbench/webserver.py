import SimpleHTTPServer
import SocketServer
import logging
import os
import json
import subprocess

from datetime import datetime

PORT = 8081

HTML_FILE=('%s/workbench/wifi-vehicles/aps/configs/ubuntu/it-eeepc-black-001/workbench/index.html' % (os.environ['HOME']))

def generate_updated(timestamp):
	# header line
	line = """<tr><th>last update</th><th>wifi network</th><th>ip addr</th></tr><tr><td>"""
	
	# 1) convert timestamp to readable datetime
	line += str(datetime.utcfromtimestamp(int(timestamp)).strftime('%Y-%m-%d %H:%M:%S')) + '</td><td>'

	# 2) which wifi network is giving us internet?
	output = ''
	essid = ''
	cmd = ['iwconfig', 'wlan-internet']
	try:
		output = subprocess.check_output(cmd, stdin = None, stderr = None, shell = False, universal_newlines = False)
	except subprocess.CalledProcessError:
		essid = 'n/a'

	if output != 'n/a':
		output = output.splitlines()
		essid = output[output.index([s for s in output if 'ESSID' in s][0])].split(':')[-1].replace('"', '').rstrip()

	line += essid + '</td><td>'

	# 3) which ip address in the wlan-internet iface?
	output = ''
	ip_addr = ''
	cmd = ['ifconfig', 'wlan-internet']
	try:
		output = subprocess.check_output(cmd, stdin = None, stderr = None, shell = False, universal_newlines = False)
	except subprocess.CalledProcessError:
		ip_addr = 'n/a'

	if output != 'n/a':
		output = output.splitlines()
		ip_addr = output[output.index([s for s in output if 'inet addr' in s][0])].split('inet addr:')[1].split(' ')[0].rstrip()

	line += ip_addr + '</td></tr>'

	return line

def update_index(status):
	
	# open & update the index.html file
	with open(HTML_FILE, 'r') as f:
		lines = f.readlines()

	cats = []
	if status['mode'] == 'backbone':
		cats = ['iperf3', 'ntp', 'cpu', 'batt', 'cbt']
	else:
		cats = ['iperf3', 'ntp', 'cpu', 'batt', 'gps', 'bitrate', 'monitor']

	print(status)

	src = '-'.join(str(status['src']).split('-')[-2:])
	with open(HTML_FILE, 'w') as f:

		for line in lines:

			if 'last update' in line:
				line = generate_updated(str(status['time']))

			elif src in line:

				tr = ("<tr><td>%s</td>" % (src))
				for cat in cats:
					if cat not in status:
						tr += """<td><font color="orange">n/a</td>"""
					elif status[cat] == 'n/a':
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

os.chdir(HTML_FILE.rstrip('index.html'))
print("serving at port %s and dir %s" % (PORT, HTML_FILE.rstrip('index.html')))
httpd.serve_forever()
