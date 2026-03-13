import re

path = 'D:/WebService/NostraDa_Pick/static/js/app.js'
content = open(path, encoding='utf-8').read()

# '───X' (공백 없이 바로 텍스트) → '─── X' (공백 삽입)
fixed = re.sub(r"'───([^─' ])", lambda m: "'─── " + m.group(1), content)
open(path, 'w', encoding='utf-8').write(fixed)
print('done')
