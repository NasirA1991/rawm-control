import os, select, time, sys
sys.path.insert(0,'tools')
from rawm_proto import find_vendor_hidraw, CMD_QUERY

name, hn, desc = find_vendor_hidraw()[0]
path = f"/dev/{name}"
ts = int(time.time())
frame = bytes([0x01,0x0b,0x03,0x00,0x00]) + ts.to_bytes(6,'little')

def try_variant(label, body, gap=0.0):
    fd = os.open(path, os.O_RDWR|os.O_NONBLOCK)
    time.sleep(0.2)
    while select.select([fd],[],[],0)[0]:
        os.read(fd,256)
    try:
        n = os.write(fd, body)
    except OSError as e:
        print(f"{label}: write error {e}"); os.close(fd); return
    print(f"{label}: wrote {n}/{len(body)}")
    if gap: time.sleep(gap); os.write(fd, body)
    got=[]; end=time.time()+2.0
    while time.time()<end:
        r,_,_ = select.select([fd],[],[],0.2)
        if r:
            try: got.append(os.read(fd,256))
            except OSError: break
    print(f"   reports={len(got)} first={got[0].hex(' ')[:80] if got else '-'}")
    os.close(fd)
    time.sleep(0.5)

rep64 = bytes([0x80|len(frame)]) + frame + b"\x00"*(64-1-len(frame))
rep64_ff = bytes([0x80|(len(frame)+4)]) + b"\xff"*4 + frame + b"\x00"*(64-5-len(frame))
try_variant("A 64-byte, no id, no FF", rep64)
try_variant("B 65-byte, id0, no FF", b"\x00"+rep64)
try_variant("C 64-byte, no id, FF prefix", rep64_ff)
try_variant("D 65-byte, id0, FF prefix", b"\x00"+rep64_ff)
try_variant("E A twice 0.1s", rep64, gap=0.1)
