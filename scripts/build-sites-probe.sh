#!/bin/sh
set -eu
. "$(dirname "$0")/env.sh"
cd "$PROJECT_DIR"
mkdir -p .tools/sites-phone-build
cp -R sites/phone-probe/. .tools/sites-phone-build/
cd .tools/sites-phone-build
pebble build
cd "$PROJECT_DIR"
python - <<'PY'
import json
from pathlib import Path
from urllib.parse import urlsplit
import zipfile
root=Path.cwd()
source=root/'.tools/sites-phone-build/build/sites-phone-build.pbw'
with zipfile.ZipFile(source) as z:
    entries=[(i,z.read(i.filename)) for i in z.infolist()]
info=json.loads(next(d for i,d in entries if i.filename=='appinfo.json'))
info['manifestVersion']=2
url=json.loads((root/'docs/sites-access-probe.json').read_text())['url']
info['usesPermissions']=[{'name':'Internet','parameters':{'domains':[urlsplit(url).hostname]}}]
output=root/'dist/pebble-sites-test.pbw'
temporary=output.with_suffix('.tmp')
with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED) as z:
    for i,d in entries:
        z.writestr(i,json.dumps(info).encode() if i.filename=='appinfo.json' else d)
temporary.replace(output)
print('Packaged dist/pebble-sites-test.pbw; no Sites credential in phone/watch code.')
PY
