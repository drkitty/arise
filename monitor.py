from __future__ import unicode_literals

import re
from subprocess import Popen, PIPE, STDOUT
from sys import stdout
from time import sleep


monitor_p = Popen(('stdbuf', '-oL', 'udevadm', 'monitor', '-k'), stdout=PIPE,
          stderr=PIPE, bufsize=1)


block_add_pattern = re.compile(
    r'KERNEL\[[^]]*\]\s*add\s*(?P<path>\S*)\s*\(block\)')
block_remove_pattern = re.compile(
    r'KERNEL\[[^]]*\]\s*remove\s*(?P<path>\S*)\s*\(block\)')


info_uuid_pattern = re.compile(
    r'S:\s*disk/by-uuid/(?P<uuid>\S*)')
info_label_pattern = re.compile(
    r'S:\s*disk/by-label/(?P<label>\S*)')
info_name_pattern = re.compile(
    r'N:\s*(?P<name>\S*)')


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


def monitor_loop():


    plugged = {}

    monitor_p = Popen(('stdbuf', '-oL', 'udevadm', 'monitor', '-k'),
                      stdout=PIPE, stderr=PIPE, bufsize=1)
    for monitor_line in iter(monitor_p.stdout.readline, b''):
        m = block_add_pattern.match(monitor_line)
        if m:
            path = m.groupdict()['path']

            with open('/dev/null', 'w') as devnull:
                Popen(('udevadm', 'settle'), stdout=devnull,
                      stderr=STDOUT).wait()

            iden = get_dev_identifier(path)
            #stdout.write('{} inserted\n'.format(iden))
            print plugged
            plugged[path] = iden

        m = block_remove_pattern.match(monitor_line)
        if m:
            path = m.groupdict()['path']
            iden = plugged.pop(path, None)
            if iden is not None:
                #stdout.write('{} removed\n'.format(iden))
                print plugged


if __name__ == '__main__':
    monitor_loop()
