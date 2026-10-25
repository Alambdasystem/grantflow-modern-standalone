"""Run reviewed disposable suites in separate processes; preserve failures as evidence."""
import json
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

out=Path('/evidence/parity'); out.mkdir(parents=True,exist_ok=True)
files=['test_central_identity','test_identity_ownership','test_coyf_operations','test_application_readiness',
       'test_ingestion','test_ingestion_extensions','test_ingestion_review_tools','test_ingestion_workers',
       'test_integration_audit']
summary=[]
if '--current-only' in sys.argv:
    files=files[:-1]+['test_extended_parity','test_identity_repair','test_control_contracts','test_cold_and_legacy']
for name in files:
    xml=out/(name+'.xml')
    with (out/(name+'.log')).open('w') as log:
        proc=subprocess.run([sys.executable,'-m','pytest','tests/'+name+'.py','-q','-p','no:cacheprovider','-p','parity_trace','--junitxml='+str(xml)],
                            env={**os.environ,'GFM_TRACE_FILE':str(out/('trace-'+name+'.json'))},stdout=log,stderr=subprocess.STDOUT,timeout=240)
    counts={'suite':name,'exit_code':proc.returncode}
    if xml.exists():
        suite=ET.parse(xml).getroot().find('testsuite')
        counts.update({k:int(suite.get(k,'0')) for k in ['tests','failures','errors','skipped']})
    summary.append(counts)
    (out/'suite-summary.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(counts),flush=True)
if any(row['exit_code'] for row in summary):
    sys.exit(1)
