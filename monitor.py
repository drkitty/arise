import re
from subprocess import Popen, PIPE, STDOUT
from sys import stdout


p = Popen(('stdbuf', '-oL', 'udevadm', 'monitor', '-k'), stdout=PIPE,
          stderr=STDOUT, bufsize=1)

c = re.compile(r'KERNEL\[[^]]*\]\s*add\s*(?P<dev_path>\S*)\s*\(block\)')

for line in iter(p.stdout.readline, b''):
    m = c.match(line)
    if m:
        dev_path = m.groupdict()['dev_path']
        print dev_path
