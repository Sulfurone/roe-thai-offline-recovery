import json
import re
import sys

pattern = re.compile(sys.argv[1], re.I)
manifest = json.load(open(r'F:\roe\recovery\extracted\thai_vfs0\vfs-manifest.json', encoding='utf-8'))
names = [e['name'].lstrip('\\') for e in manifest['entries'] if e.get('name')]
hits = [n for n in names if pattern.search(n)]
print('total', len(names), 'hits', len(hits))
for name in hits[:300]:
    print(name)
