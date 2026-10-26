"""Validate both deployment choices against the current downloaded Render schema."""
import json
from pathlib import Path
import yaml
import jsonschema
root=Path('/repo')
schema=json.loads((root/'.private/render-blueprint-schema.json').read_text())
for name in ['render.yaml','render-core.yaml','deploy/render-ollama-optional.yaml']:
    jsonschema.validate(yaml.safe_load((root/name).read_text()),schema)
    print(name+': current Render schema PASS')
