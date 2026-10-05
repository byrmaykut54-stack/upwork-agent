"""Catch syntax failures in external and inline browser scripts."""
from html.parser import HTMLParser
from pathlib import Path
import subprocess
import tempfile

class Scripts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.active=False
        self.blocks=[]
    def handle_starttag(self,tag,attrs):
        if tag=='script' and not dict(attrs).get('src'):
            self.active=True
            self.blocks.append('')
    def handle_data(self,data):
        if self.active:self.blocks[-1]+=data
    def handle_endtag(self,tag):
        if tag=='script':self.active=False

for path in Path('web').glob('*.js'):
    subprocess.run(['node','--check',str(path)],check=True)
for path in Path('web').glob('*.html'):
    parser=Scripts()
    parser.feed(path.read_text())
    for block in parser.blocks:
        with tempfile.NamedTemporaryFile(mode='w',suffix='.js') as temp:
            temp.write(block);temp.flush()
            subprocess.run(['node','--check',temp.name],check=True)
print('Browser script syntax passed')
