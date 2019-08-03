import SimpleHTTPServer
import SocketServer
import logging
import os
import json
import subprocess

from datetime import datetime

PORT = 8081
HTML_FILE=('%s/workbench/wifi-vehicles/aps/configs/ubuntu/it-eeepc-black-001/workbench/index.html' % (os.environ['HOME']))

columns = {
    'main-client' : ['iperf', 'tcpdump', 'cbt', 'ntp', 'batt', 'cpu', 'gps'],
    'bck-client' : ['iperf', 'cbt', 'ntp', 'batt', 'cpu'],
    'server' : ['iperf', 'ntp', 'batt', 'cpu'],
    'ap' : ['cbt', 'cpu'],
}

def generate_updated(timestamp):
    # header line
    line = """<h3>SYSTEM INFO</h3><table style="width:65%"><tr><th>last update</th><tr><td>"""
    # 1) convert timestamp to readable datetime
    line += str(datetime.utcfromtimestamp(int(timestamp)).strftime('%Y-%m-%d %H:%M:%S')) + '</td></tr></table>'
    return line

    # # 2) which wifi network is giving us internet?
    # output = ''
    # essid = ''
    # cmd = ['iwconfig', 'wlan-internet']
    # try:
    # output = subprocess.check_output(cmd, stdin = None, stderr = None, shell = False, universal_newlines = False)
    # except subprocess.CalledProcessError:
    # essid = 'n/a'

    # if output != 'n/a':
    # output = output.splitlines()
    # essid = output[output.index([s for s in output if 'ESSID' in s][0])].split(':')[-1].replace('"', '').rstrip()

    # line += essid + '</td><td>'

    # # 3) which ip address in the wlan-internet iface?
    # output = ''
    # ip_addr = ''
    # cmd = ['ifconfig', 'wlan-internet']
    # try:
    # output = subprocess.check_output(cmd, stdin = None, stderr = None, shell = False, universal_newlines = False)
    # except subprocess.CalledProcessError:
    # ip_addr = 'n/a'

    # if output != 'n/a':
    # output = output.splitlines()
    # ip_addr = output[output.index([s for s in output if 'inet addr' in s][0])].split('inet addr:')[1].split(' ')[0].rstrip()

    # line += ip_addr + '</td></tr></table>'

    # return line

def update_index(statuses):

    # open & update the index.html file
    with open(HTML_FILE, 'r') as f:
        lines = f.readlines()

    print(statuses)

    for status in statuses:
        
        node = str(status['node'])
        cols = columns[status['section']]

        with open(HTML_FILE, 'w') as f:

    		for line in lines:

    			if 'SYSTEM INFO' in line:
    				continue

    			elif ('<th>%s</th>' % (node)) in line:

                    # create a new line 
    				tr = ("<tr><td>%s</td>" % (node))

                    for c in cols:
                        if c not in status:
                            tr += """<td><font color="orange">n/a</td>"""
                        elif status[c] == 'n/a':
                            tr += """<td><font color="orange">n/a</td>"""
                        elif status[c] == 'bad':
                            tr += """<td><font color="red">bad</td>"""
                        elif status[c] == 'ok':
                            tr += """<td><font color="green">ok</td>"""
                        else:
                            tr += ("""<td><font color="black">%s</td>""" % (status[cat]))

    				tr += '</tr>\n'
    				line = tr

    			f.write(line)
    		# system info line at the end
    		# BEWARE : this was a last minute fix
    		f.write(generate_updated(str(status['time'])))

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
        # update .html status file
        update_index(json.loads(post_data))

Handler = myHandler
httpd = SocketServer.TCPServer(("", PORT), Handler)
os.chdir(HTML_FILE.rstrip('index.html'))
print("serving at port %s and dir %s" % (PORT, HTML_FILE.rstrip('index.html')))
httpd.serve_forever()
