from __future__ import unicode_literals

import os
import re
import select
import socket
import subprocess
from subprocess import Popen, PIPE, STDOUT
from sys import stderr, stdout
from time import sleep

from common import PollWrapper, SocketWrapper


block_add_pattern = re.compile(
    r'KERNEL\[[^]]*\]\s*add\s*(?P<path>\S*)\s*\(block\)')
block_remove_pattern = re.compile(
    r'KERNEL\[[^]]*\]\s*remove\s*(?P<path>\S*)\s*\(block\)')


class ServerSocketWrapper(SocketWrapper):
    def interact(self):
        pass  # TODO

    def handle_command_generator(self, command, args, plugged):
        if command == 'mount':
            at = args.pop('at', None)
            if at is None:
                self.prepare_send(
                    'error', desc='The "at" argument is required.')
                yield

            def f(dev):
                for field, value in args.iteritems():
                    if field in dev and dev[field] == value:
                        return True
                return False
            matches = filter(f, plugged.itervalues())

            if len(matches) > 1:
                self.prepare_send('error', desc='Multiple devices matched')
                while self.send_message() is None:
                    yield
            if len(matches) == 0:
                sw.prepare_send('error', desc='No devices matched')
                while self.send_message() is None:
                    yield

            dev_path = '/dev/' + matches[0]['name']
            # FIXME: Fork or something.
            if subprocess.call(('mount', dev_path, at)) == 0:
                matches[0]['at'] = at
                raise StopIteration
            else:
                self.prepare_send('error', desc='Mount failed')
                while self.send_message() is None:
                    yield
                raise StopIteration
        elif command == 'unmount':
            def f(dev):
                for field, value in args.iteritems():
                    if field in dev and dev[field] == value:
                        return True
                return False
            matches = filter(f, plugged.itervalues())

            if len(matches) > 1:
                self.prepare_send('error', desc='Multiple devices matched')
                while self.send_message() is None:
                    yield
            if len(matches) == 0:
                self.prepare_send('error', desc='No devices matched')
                while self.send_message() is None:
                    yield

            dev_path = '/dev/' + matches[0]['name']
            # FIXME: Fork or something.
            if subprocess.call(('umount', dev_path)) == 0:
                del matches[0]['at']
                raise StopIteration
            else:
                self.prepare_send('error', desc='umount failed')
                while self.send_message() is None:
                    yield
        else:
            self.prepare_send('error', desc='Invalid command')
            while self.send_message() is None:
                yield

    def prepare_handle_command(self, command, args, plugged):
        if not self.command_handler


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
        stdout.write('inserted {}\n'.format(iden))
        plugged[path] = iden
        return

    m = block_remove_pattern.match(monitor_line)
    if m:
        path = m.groupdict()['path']
        iden = plugged.pop(path, None)
        if iden is not None:
            stdout.write('removed {}\n'.format(iden))
        return


class InvalidMessage(Exception):
    pass


def receive_message(s):
    def get(count):
        msg = b''
        while True:
            chunk = s.recv(count - len(msg))
            msg += chunk
            if len(msg) < count:
                yield
            else:
                yield msg

    def decode_length(encoded):
        return ord(encoded[0]) ** 2**8 + ord(encoded[1])

    for command_len in get(2):
        if command_len:
            break
        else:
            yield
    command_len = decode_length(command_len)
    if command_len == 0:
        raise InvalidMessage('Empty command')

    for command in get(command_len):
        if command:
            break
        else:
            yield
    command = command.decode('utf_8')

    args = {}
    while True:
        for arg_len in get(2):
            if arg_len:
                break
            else:
                yield
        arg_len = decode_length(arg_len)
        if arg_len == 0:
            yield command, args

        for arg in get(arg_len):
            if arg:
                break
            else:
                yield
        arg = arg.decode('utf_8')

        key, value = arg.split('=', 1)
        args[key] = value


def main_event_loop():
    poller = PollWrapper()

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

    while True:
        events = poller.poll()
        for fd, kind in events:
            if fd == monitor.stdout.fileno():
                handle_monitor_event(monitor.stdout.readline(), plugged)
            elif fd == socket_master.fileno():
                assert kind & select.POLLIN

                sock, _ = socket_master.accept()
                print 'Socket with fd {} accepted'.format(sock.fileno())
                sw = SocketWrapper(sock=sock, poller=poller)
                clients[s.fileno()] = sw
                ret = sw.receive_message()
                if ret:
                    items, dictionary = ret
                    sw.handle_command(items[0], dictionary, plugged)
            elif kind & select.POLLHUP:
                assert fd in clients

                clients[fd].close()
                print 'Socket with fd {} closed'.format(fd)
                del clients[fd]
            elif kind & select.POLLIN:
                assert fd in clients
            elif kind & select.POLLOUT:
                assert fd in clients

                clients[fd].send_message()
            else:
                raise Exception('An unacceptable state of affairs has '
                                'arisen')


if __name__ == '__main__':
    main_event_loop()
