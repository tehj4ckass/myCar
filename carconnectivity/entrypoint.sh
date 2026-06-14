#!/bin/sh
python3 - <<'EOF'
import os

with open('/carconnectivity.json.template') as f:
    content = f.read()

for key, val in os.environ.items():
    content = content.replace('${' + key + '}', val)

with open('/carconnectivity.json', 'w') as f:
    f.write(content)
EOF

exec carconnectivity /carconnectivity.json "$@"
