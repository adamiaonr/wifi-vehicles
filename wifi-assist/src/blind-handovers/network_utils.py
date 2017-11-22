import os
import sys
import glob
import math
import time
import pwd

# required for external commands (e.g. wpa_supplicant, iwconfig, ifconfig)
import signal
import subprocess as sp
import shlex
import tempfile as tf
import pty

from select import select

# required by dhcp
import socket
import fcntl
import struct

WPA_SUPPLICANT = '/home/pi/workbench/wpa_supplicant/wpa_supplicant'

def get_ip_address(iface):

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    ip_addr = ''

    try:
        r = fcntl.ioctl(s.fileno(), 0x8915, struct.pack('256s', iface[:15].strip()))[20:24]
        ip_addr = socket.inet_ntoa(r)

    except Exception as e:
        print("%s::get_ip_address() : [ERROR]" % (sys.argv[0]))
        print(e)

    return ip_addr

def dhclient(iface, log_filename = ''):

    try:
        # since we don't need to read output of dhclient in 'real time',
        # we use subprocess.check_output()
        output = sp.check_output(('/sbin/dhclient %s -v ' % (iface)), shell = True, stderr = sp.STDOUT)

        if not log_filename:
            return 0

        # since dhclient output cannont be timestamped, we add timestamps a posteriori
        # FIXME : this is VERY wrong
        log_file = open(log_filename, 'a+')
        for line in output.split('\n'):
            log_file.write(('%s : %s\n' % (time.time(), line)))
            log_file.flush()

    except sp.CalledProcessError as e:
        sys.stderr.write(
            "%s::dhclient() : [ERROR]: output = %s, error code = %s\n"
            % (sys.argv[0], e.output, e.returncode))

    return 0

def wpa_supplicant(ap, iface, log_filename, force_dhclient = False):

    # open a pseudo-terminal. master and slave are file descriptors which
    # will be used in Popen()
    master, slave = pty.openpty()

    # call wpa_supplicant w/ ap config file: 
    #   - with sp.Popen()
    #   - shell = False 
    #   - direct stdout to the slave end of the pseudo-terminal
    #
    # why do we do this? this is due to the 'suffering from buffering' [1] problem:
    #   - most programs buffer their output for efficiency, i.e. they retain the
    #     their output every k lines before flushing them to the output stream.
    #   - if a program determines it's connected to the terminal, it flushes
    #     its output line by line, immediately
    #   - if the program detects it's not connected to a terminal - e.g. when invoked with 
    #     Popen() + stdout = PIPE - it retains its output.
    #
    # in our case, we started by using Popen() w/ stdout = PIPE, which wouldn't 
    # keep our python script from reading the whole output.
    #
    # the solution is to 'trick' the program invoked by Popen() to determine it's 
    # connected to a terminal. we use the pty python module to accomplish it.
    #
    # sources:
    # [1] https://stackoverflow.com/questions/33886406/how-to-avoid-the-deadlock-in-a-subprocess-without-using-communicate
    # https://stackoverflow.com/questions/38374063/python-can-we-use-tempfile-with-subprocess-to-get-non-buffering-live-output-in-p
    # https://stackoverflow.com/questions/31926470/run-command-and-get-its-stdout-stderr-separately-in-near-real-time-like-in-a-te
    # https://stackoverflow.com/questions/21442360/issuing-commands-to-psuedo-shells-pty
    # https://stackoverflow.com/questions/8710829/send-command-and-exit-using-python-pty-pseudo-terminal-process
    # https://stackoverflow.com/questions/21442360/issuing-commands-to-psuedo-shells-pty
    # https://docs.python.org/3/library/pty.html
    # https://www.programcreek.com/python/example/8151/pty.openpty
    #
    try:
        p = sp.Popen(shlex.split(('%s -dd -t -K -i%s -c%s -Dwext' % (WPA_SUPPLICANT, iface, ap.config_file))), 
            shell = False, stdin = None, stdout = slave, stderr = None)

        # save output of wpa_supplicant in log file
        log_file = open(log_filename, 'a+')

        # termination flag
        terminate = False
        # read output from wpa_supplicant here
        while p.poll() is None:

            if select([master], [], [], 0):

                # read a block of 1024 byte (default) from the master fd
                lines = os.read(master, 1024)
                # write lines to log file
                log_file.write(lines)
                log_file.flush()

                # now search for patterns : 
                #   - 'connection to x completed' : force dhcp and/or terminate the wpa_supplicant() call
                lines = lines.split('\n')
                for line in lines:
                    if ('%s: CTRL-EVENT-CONNECTED' % (iface)) in line[18:]:

                        # after a successful wifi connection setup, initialize 
                        # a dhcp request, if specified
                        if (not get_ip_address(iface)) and force_dhclient:
                            dhclient(iface)

                        terminate = True

            # jump off the reading while cycle if terminate flag is set
            if terminate:
                break

        # close the pty fds
        os.close(slave)
        os.close(master)

    except sp.CalledProcessError as e:
        sys.stderr.write(
            "%s::wpa_supplicant() : [ERROR]: output = %s, error code = %s\n"
            % (sys.argv[0], e.output, e.returncode))

    # return the fd of the process started w/ Popen()
    return p