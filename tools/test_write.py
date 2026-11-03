import sys, time, json
sys.path.insert(0,'tools')
from rawm_proto import *

CONFIG_TYPE_CRC=0x24
def crc16(buf):
    crc=0xffff
    for b in buf:
        crc=((crc>>8)&0xff)|((crc<<8)&0xffff)
        crc^=b
        crc^=((crc&0xff)>>4)
        crc^=((crc<<8)<<4)&0xffff
        crc^=(((crc&0xff)<<4)<<1)&0xffff
        crc&=0xffff
    return crc

def wrapped(cmd, sub, data, crc=True):
    n=3+len(data)
    inner=bytes([((n>>8)<<4)|(cmd&0xf), n&0xff, sub])+bytes(data)
    if not crc: return inner
    total=len(inner)+5
    c=crc16(inner)
    out=bytes([((total>>8)<<4)|(CMD_CONFIG&0xf), total&0xff, CONFIG_TYPE_CRC, c&0xff, (c>>8)&0xff])+inner
    return out

def send_frame(dev, frame):
    dev.send_raw_payload(frame)

def query(dev):
    dev.events()  # clear leftovers
    dev.send_query()
    frames=dev.drain_events(2.5)
    for f in frames:
        cmd,n,sub,data=parse_frame(f)
        if cmd==CMD_QUERY_RESULT:
            # For CMD_QUERY_RESULT the payload is raw JSON; the "sub-type"
            # byte is actually the opening '{'.
            return json.loads((bytes([sub]) + data).rstrip(b'\x00'))
    return None

def param_data(info):
    d=bytearray()
    res=info['cpi']; d+=bytes([res&0xff,(res>>8)&0xff])
    pr=info['polling']; d+=bytes([pr&0xff,(pr>>8)&0xff])
    d.append(info['light']&0xff)
    lv=info['cpi_l']; d.append(len(lv))
    for v in lv: d+=bytes([v&0xff,(v>>8)&0xff])
    d.append(info['ob']&0xff); d.append(info['pm']&0xff)
    d+=b'\x00\x00\x00\x00'
    d.append(0)  # 32-bit cpi level count
    d.append(info['lod']&0xff)
    kd=info['kd']; d.append(len(kd)); d+=bytes([k&0xff for k in kd])
    d.append(info['ms']&0xff); d.append(info['at']&0xff)
    d.append(info['as']&0xff); d.append(info['rctrl']&0xff)
    cols=info['cpi_l_c']; d.append(len(cols)); d+=bytes([c&0x7 for c in cols])
    d.append(info['top']&0xff)
    bl=info['battery_levels'] if 'battery_levels' in info else [4100,4020,3900,3790,3720,3670,3630,3610,3560,3480,3200]
    d.append(len(bl))
    for v in bl: d+=bytes([v&0xff,(v>>8)&0xff])
    d.append(info['atp']&0xff)
    ocs=info['ocs']; d.append(len(ocs)); d+=bytes(ocs)
    d.append(info['gm'][1]&0xff)
    return bytes(d)

hits=find_vendor_hidraw(); dev=Device(f"/dev/{hits[0][0]}", debug=False)
info=query(dev)
print("BEFORE:", {k:info[k] for k in ('ms','polling','lod','cpi','as','rctrl','at')})
print("battery",info['battery'],"charging",info['chr'])

# add battery_levels from the notify frame (not in JSON)
info['battery_levels']=[4100,4020,3900,3790,3720,3670,3630,3610,3560,3480,3200]

data=param_data(info)
print("param struct len",len(data))
frame=wrapped(CMD_CONFIG,CONFIG_TYPE_MOUSE_PARAM,data,crc=bool(info['crc']))
print("frame len",len(frame),"crc",info['crc'])

# toggle motion sync on
info['ms']=1
data=param_data(info)
send_frame(dev, wrapped(CMD_CONFIG,CONFIG_TYPE_MOUSE_PARAM,data,crc=True))
time.sleep(1.0)
info2=query(dev)
print("AFTER ms=1:", {k:info2[k] for k in ('ms','polling','lod','cpi')})

# toggle back
info2['battery_levels']=[4100,4020,3900,3790,3720,3670,3630,3610,3560,3480,3200]
info2['ms']=info['ms'] if False else 0
send_frame(dev, wrapped(CMD_CONFIG,CONFIG_TYPE_MOUSE_PARAM,param_data(info2),crc=True))
time.sleep(1.0)
info3=query(dev)
print("AFTER ms=0:", {k:info3[k] for k in ('ms','polling','lod','cpi')})
dev.close()
