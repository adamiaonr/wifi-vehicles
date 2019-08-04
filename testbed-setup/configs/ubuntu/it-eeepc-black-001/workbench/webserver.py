import SimpleHTTPServer
import SocketServer
import logging
import os
import json
import subprocess

from datetime import datetime

PORT = 8081
HTML_FILE=('%s/workbench/wifi-vehicles/testbed-setup/configs/ubuntu/it-eeepc-black-001/workbench/index.html' % (os.environ['HOME']))

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

def update_index(statuses):

    # open & update the index.html file
    with open(HTML_FILE, 'r') as f:
        lines = f.readlines()

    for status in statuses:

        node = str(status['node'])
        cols = columns[status['section']]
        print(('<td>%s</td>' % (node)))
        
        for i, line in enumerate(lines):

            if 'SYSTEM INFO' in line:
                lines.remove(line)

            elif ('<td>%s</td>' % (node)) in line:

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
                        tr += ("""<td><font color="black">%s</td>""" % (status[c]))

                tr += '</tr>\n'
                lines[i] = tr

    print('will write:')
    for line in lines:
        print line.strip()

    # re-write .html file w/ updated lines
    with open(HTML_FILE, 'w+') as f:
        for line in lines:
            f.write(line)
        # add system info line at the end
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
        # print("POST request,\nPath: %s\nHeaders:\n%s\n\nBody:\n%s\n" % (str(self.path), str(self.headers), post_data))
        # update .html status file
        update_index(json.loads(post_data))

Handler = myHandler
httpd = SocketServer.TCPServer(("", PORT), Handler)
os.chdir(HTML_FILE.rstrip('index.html'))
print("serving at port %s and dir %s" % (PORT, HTML_FILE.rstrip('index.html')))
httpd.serve_forever()
