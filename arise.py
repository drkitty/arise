from __future__ import unicode_literals

import os
import re
import select
import socket
import subprocess
from subprocess import Popen, PIPE, STDOUT
from sys import stderr, stdout
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
    identifier['name'] = name.strip()

    symlinks_p = Popen(('udevadm', 'info', '-q', 'symlink', '-p', path),
        stdout=PIPE, stderr=PIPE)
    symlinks, _ = symlinks_p.communicate()
    symlinks.strip()
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


class InvalidMessage(Exception):
    pass


# FIXME: Review and possibly refactor.
def receive_message(client):
    def get(count):
        msg = b''
        while True:
            chunk = client.recv(count - len(msg))
            msg += chunk
            if len(msg) < count:
                yield
            else:
                yield msg

    command_len = ''
    while True:
        for c in get(1):
            if c:
                break
            else:
                yield
        c.decode('ascii')
        if '0' <= c <= '9':
            command_len += c
        elif c == ':':
            break
        else:
            raise InvalidMessage('Expected digit or ":"')
    command_len = int(command_len)

    for command in get(command_len):
        if command:
            break
        else:
            yield
    try:
        command = command.decode('utf_8')
    except UnicodeDecodeError:
        raise InvalidMessaged('Invalid UTF-8')

    args = {}
    while True:
        for c in get(1):
            if c:
                break
            else:
                yield
        c = c.decode('ascii')
        if c == '$':  # end of message
            yield command, args
        elif '0' <= c <= '9':
            arg_len = c
        else:
            raise InvalidMessage('Expected digit, ":", or "$"')

        while True:
            for c in get(1):
                if c:
                    break
                else:
                    yield
            c = c.decode('ascii')
            if '0' <= c <= '9':
                arg_len += c
            elif c == ':':
                break
            else:
                raise InvalidMessage('Expected digit or ":"')
        arg_len = int(arg_len)

        for arg in get(arg_len):
            if arg:
                break
            else:
                yield
        try:
            arg = arg.decode('utf_8')
        except UnicodeDecodeError:
            raise InvalidMessage('Invalid UTF-8')

        key, value = arg.split('=', 1)
        args[key] = value


def handle_message(fd, client, waiting):
    if fd not in waiting:
        waiting[fd] = receive_message(client)
    ret = next(waiting[fd])

    if ret is None:
        return

    del waiting[fd]
    return ret


def handle_command(client, plugged, command, args):
    if command == 'mount':
        at = args.pop('at', None)
        if at is None:
            stderr.write('"at" argument is required\n')
            return

        def f(dev):
            for field, value in args.iteritems():
                if field in dev and dev[field] == value:
                    return True
            return False
        matches = filter(f, plugged.itervalues())

        if len(matches) > 1:
            stderr.write('More than one device matched\n')
            return
        if len(matches) == 0:
            stderr.write('No devices matched\n')
            return

        dev_path = '/dev/' + matches[0]['name']
        subprocess.call(('mount', dev_path, at))


def main_event_loop():
    poller = select.poll()

    monitor = Popen(('stdbuf', '-oL', 'udevadm', 'monitor', '-k'),
                      stdout=PIPE, stderr=PIPE)
    poller.register(monitor.stdout, select.POLLIN)

    socket_master = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        os.remove('/tmp/arise.sock')
    except OSError as e:
        if e.errno != 2:  # "No such file or directory"
            raise
    socket_master.bind('/tmp/arise.sock')
    os.chmod('/tmp/arise.sock', 0666)
    socket_master.listen(1)
    poller.register(socket_master, select.POLLIN)

    plugged = {}
    clients = {}
    waiting = {}

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
                if kind & select.POLLHUP and not (kind & select.POLLIN and
                        clients[fd].recv(1, socket.MSG_PEEK)):
                    print 'Socket with fd {} died'.format(fd)
                    poller.unregister(fd)
                    del clients[fd]
                    waiting.pop(fd, None)
                elif kind & select.POLLIN:
                    try:
                        ret = handle_message(fd, clients[fd], waiting)
                    except InvalidMessage as e:
                        stderr.write('Invalid message ({})\n'.format(
                            e.message))
                        poller.unregister(fd)
                        del clients[fd]
                        waiting.pop(fd, None)
                        print 'Killed socket with fd {}'.format(fd)

                    if ret is not None:
                        command, args = ret
                        print '({}, {})'.format(command, args)
                        handle_command(clients[fd], plugged, command, args)
                else:
                    raise Exception('An unacceptable state of affairs has '
                                    'arisen')
            else:
                raise Exception('An unacceptable state of affairs has '
                                'arisen')


if __name__ == '__main__':
    main_event_loop()
