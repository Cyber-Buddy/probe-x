import json, base64, subprocess, os, re

with open("/tmp/vmsettings_v9.json") as f:
    d = json.load(f)

gs = d["extensionGoalStates"][0]
settings_list = gs.get("settings",[])
ps_b64 = None
for s in settings_list:
    ps = s.get("protectedSettings","")
    if ps and len(ps) > 100:
        ps_b64 = ps
        break

if not ps_b64:
    print("ERROR: No protectedSettings found")
    exit(1)

ps_der = base64.b64decode(ps_b64)
with open("/tmp/ps_v9.der","wb") as f:
    f.write(ps_der)
print(f"protectedSettings DER: {len(ps_der)} bytes, first byte: 0x{ps_der[0]:02x}")

r = subprocess.run(["openssl","cms","-decrypt","-inform","DER","-inkey","/tmp/crp_v9.pem","-in","/tmp/ps_v9.der","-out","/tmp/ps_v9.json"], capture_output=True)
if r.returncode != 0:
    print(f"CMS decrypt failed: {r.stderr.decode()[:300]}")
    r2 = subprocess.run(["openssl","smime","-decrypt","-inform","DER","-inkey","/tmp/crp_v9.pem","-in","/tmp/ps_v9.der","-out","/tmp/ps_v9.json"], capture_output=True)
    if r2.returncode != 0:
        print(f"SMIME also failed: {r2.stderr.decode()[:300]}")
        exit(1)

sz = os.path.getsize("/tmp/ps_v9.json")
print(f"Decrypted protectedSettings: {sz} bytes")

with open("/tmp/ps_v9.json") as f:
    ps_json = json.load(f)

script_b64 = ps_json.get("script","")
if script_b64:
    script = base64.b64decode(script_b64).decode(errors="replace")
    print(f"Script decoded: {len(script)} chars")

    for m in re.finditer(r"SCRIPT_PARAM_(\w+)='([^']*)'", script):
        name = m.group(1)
        val = m.group(2)
        if len(val) > 200:
            print(f"  {name}: {val[:80]}...({len(val)} chars)")
        else:
            print(f"  {name}: {val}")
else:
    for k,v in ps_json.items():
        if isinstance(v,str) and len(v)>50:
            print(f"  {k}: {v[:80]}...({len(v)} chars)")
        else:
            print(f"  {k}: {v}")
