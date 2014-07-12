from __future__ import unicode_literals

import os
import re
import select
import socket
from subprocess import Popen, PIPE, STDOUT
from sys import stdout
from time import sleep


block_add_pattern = re.compile(
    r'KERNEL\[[^]]*\]\s*add\s*(?P<path>\S*)\s*\(block\)')
block_remove_pattern = re.compile(
    r'KERNEL\[[^]]*\]\s*remove\s*(?P<path>\S*)\s*\(block\)')


def get_dev_identifier(path):
    identifier = {}

    name_p = Popen(('udevadm', 'info', '-q', 'name', '-p', path), stdout=PIPE,
              stderr=PIPE)
    name, _ = name_p.communicate()
    identifier['name'] = name.split()

    symlinks_p = Popen(('udevadm', 'info', '-q', 'symlink', '-p', path),
        stdout=PIPE, stderr=PIPE)
    symlinks, _ = symlinks_p.communicate()
    for symlink in symlinks.split():
        symlink = symlink[len('disk/'):]
        kind, value = symlink.split(b'/')
        kind = kind[len('by-'):].decode('utf_8')
        value = value.decode('string_escape').decode('utf_8')
        if kind in ('uuid', 'label'):
            identifier[kind] = value

    return identifier


def handle_monitor_event(monitor_line, plugged):
    m = block_add_pattern.match(monitor_line)
    if m:
        path = m.groupdict()['path']

        with open('/dev/null', 'w') as devnull:
            Popen(('udevadm', 'settle'), stdout=devnull,
                  stderr=STDOUT).wait()

        iden = get_dev_identifier(path)
        #stdout.write('{} inserted\n'.format(iden))
        plugged[path] = iden
        print plugged
        return

    m = block_remove_pattern.match(monitor_line)
    if m:
        path = m.groupdict()['path']
        iden = plugged.pop(path, None)
        if iden is not None:
            #stdout.write('{} removed\n'.format(iden))
            print plugged
        return


def main_event_loop():
    poller = select.poll()

    monitor = Popen(('stdbuf', '-oL', 'udevadm', 'monitor', '-k'),
                      stdout=PIPE, stderr=PIPE, bufsize=1)
    poller.register(monitor.stdout, select.POLLIN)

    socket_master = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        os.remove('/tmp/arise.sock')
    except OSError as e:
        if e.errno != 2:  # "No such file or directory"
            raise
    socket_master.bind('/tmp/arise.sock')
    socket_master.listen(1)
    poller.register(socket_master, select.POLLIN)

    plugged = {}
    clients = {}

    while True:
        events = poller.poll()
        for fd, kind in events:
            if fd == monitor.stdout.fileno():
                handle_monitor_event(monitor.stdout.readline(), plugged)
            elif fd == socket_master.fileno():
                s, _ = socket_master.accept()
                print 'New socket with fd {}'.format(s.fileno())
                poller.register(s, select.POLLIN | select.POLLHUP)
                clients[s.fileno()] = s
            elif fd in clients:
                if kind & select.POLLHUP:
                    print 'Socket with fd {} died'.format(fd)
                    poller.unregister(fd)
                    del clients[fd]
                elif kind & select.POLLIN:
                    #handle_message(clients[fd])
                    print 'Message from socket with fd {} reads "{}"'.format(
                        fd, clients[fd].recv(3))
                else:
                    raise Exception('An unacceptable state of affairs has '
                                    'occurred')
            else:
                raise Exception('An unacceptable state of affairs has '
                                'occurred')


if __name__ == '__main__':
    main_event_loop()
