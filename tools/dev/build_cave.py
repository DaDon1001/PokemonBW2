import sys,struct
from keystone import *
CAVE=0x02085200
LEG=[144,145,146,150,151,243,244,245,249,250,251,377,378,379,380,381,382,383,384,385,386,
     480,481,482,483,484,485,486,487,488,490,491,492,493,494,638,639,640,641,642,643,644,645,646,647,648,649]
STA=[149,150,151,248,249,250,251,289,373,376,380,381,382,383,384,385,386,445,483,484,485,486,487,488,
     490,491,492,493,494,635,643,644,645,646,648,649]
FIND_RATE_DEFAULT=20
def src():
    s=f"""
.thumb
helper_entry:
  push {{r6, r7, lr}}
  movs r6, #0
  ldr r0, [r5]
  bl #0x2017354
  adds r7, r0, #0
  adds r0, r7, #0
  movs r1, #179
  movs r2, #1
  movs r3, #4
  bl #0x200842c
  orrs r6, r0
  adds r0, r7, #0
  movs r1, #180
  movs r2, #1
  movs r3, #4
  bl #0x200842c
  lsls r0, r0, #1
  orrs r6, r0
  adds r0, r7, #0
  movs r1, #181
  movs r2, #1
  movs r3, #4
  bl #0x200842c
  lsls r0, r0, #2
  orrs r6, r0
  adds r0, r7, #0
  movs r1, #182
  movs r2, #1
  movs r3, #4
  bl #0x200842c
  lsls r0, r0, #3
  orrs r6, r0
  ldr r0, flagp_a
  str r6, [r0]
  movs r0, #4
  tst r6, r0
  beq not_leg
  movs r0, #{len(LEG)}
  bl #0x2005748
  lsls r0, r0, #1
  ldr r1, legp
  ldrh r0, [r1, r0]
  b set_species
not_leg:
  movs r0, #8
  tst r6, r0
  beq done_e
  movs r0, #{len(STA)}
  bl #0x2005748
  lsls r0, r0, #1
  ldr r1, stap
  ldrh r0, [r1, r0]
set_species:
  strh r0, [r4]
  movs r0, #0
  strb r0, [r4, #5]
done_e:
  ldrh r0, [r4]
  ldrb r1, [r4, #5]
  pop {{r6, r7, pc}}
.align 2
flagp_a: .word FLAGADDR
legp: .word LEGADDR
stap: .word STAADDR

helper_count:
  push {{lr}}
  ldr r0, flagp_b
  ldr r0, [r0]
  movs r1, #1
  tst r0, r1
  beq normal
  movs r6, #0xff
  lsls r6, r6, #9
  b out_c
normal:
  movs r6, #1
  ldr r0, [r5]
  bl #0x2017354
  movs r1, #0x9e
  lsls r1, r1, #2
  movs r2, #1
  movs r3, #4
  bl #0x2008474
  cmp r0, #0
  beq out_c
  adds r6, r6, #2
out_c:
  adds r0, r6, #0
  pop {{pc}}
.align 2
flagp_b: .word FLAGADDR

helper_iv:
  ldr r1, flagp_c
  ldr r1, [r1]
  movs r0, #0
  mvns r0, r0
  movs r2, #2
  tst r1, r2
  beq out_i
  lsrs r0, r0, #2
out_i:
  bx lr
.align 2
flagp_c: .word FLAGADDR

helper_hold:
  push {{lr}}
  ldrh r0, [r4, #2]
  cmp r0, #0
  bne keep_h
  movs r0, #FINDRATE
  bl #0x2005748
  cmp r0, #0
  bne keep_h
  movs r0, #4
  bl #0x2005748
  adds r2, r0, #0
  adds r2, #179
  b out_h
keep_h:
  ldrh r2, [r4, #2]
out_h:
  ldr r0, maxp
  pop {{pc}}
.align 2
maxp: .word 0x27e
end_code:
"""
    return s
def assemble():
    ks=Ks(KS_ARCH_ARM,KS_MODE_THUMB)
    # Pass 1 mit Platzhaltern fuer Laengen
    tmp=src().replace("FLAGADDR","0").replace("LEGADDR","0").replace("STAADDR","0").replace("FINDRATE",str(FIND_RATE_DEFAULT))
    enc,_=ks.asm(tmp,CAVE); code=bytes(enc)
    # Symbole bestimmen (zweiter Durchlauf liefert Adressen)
    labels={}
    # Labels via keystone: Symbolauflösung ueber separate Assemblierung der Teilstuecke
    return code
if __name__=="__main__":
    code=assemble(); print(len(code))

def thumb_bl(addr,target):
    """Thumb-BL (Befehlspaar) von addr nach target als 4 Bytes."""
    off=(target-(addr+4))>>1
    assert -(1<<21)<=off<(1<<21)
    hi=0xF000|((off>>11)&0x7FF); lo=0xF800|(off&0x7FF)
    return struct.pack("<HH",hi,lo)


def fix_bl(code,source):
    """Keystone rechnet Spruenge nach .align falsch: alle BL neu kodieren und gegen die Quelle pruefen."""
    import re
    from capstone import Cs,CS_ARCH_ARM,CS_MODE_THUMB
    wanted=[int(m.group(1),16) for m in re.finditer(r"^\s*bl #(0x[0-9a-fA-F]+)",source,re.M)]
    md=Cs(CS_ARCH_ARM,CS_MODE_THUMB); md.skipdata=True
    pos=[i.address for i in md.disasm(code,CAVE) if i.mnemonic=="bl"]
    assert len(pos)==len(wanted),(len(pos),len(wanted))
    out=bytearray(code)
    for a,t in zip(pos,wanted):
        out[a-CAVE:a-CAVE+4]=thumb_bl(a,t)
    got=[int(i.op_str[1:],16) for i in md.disasm(bytes(out),CAVE) if i.mnemonic=="bl"]
    assert got==wanted,"BL-Ziele stimmen nicht"
    return bytes(out)


def build():
    from capstone import Cs,CS_ARCH_ARM,CS_MODE_THUMB
    ks=Ks(KS_ARCH_ARM,KS_MODE_THUMB)
    base_src=src()
    ph=base_src.replace("FLAGADDR","0").replace("LEGADDR","0").replace("STAADDR","0").replace("FINDRATE",str(FIND_RATE_DEFAULT))
    enc,_=ks.asm(ph,CAVE); code=bytes(enc)
    md=Cs(CS_ARCH_ARM,CS_MODE_THUMB)
    # Positionen der Funktionsenden (nur Code, nicht Literal-Woerter) per Durchlauf
    ends={}
    addr=CAVE; off=0
    # Funktionsenden anhand der erwarteten Instruktionsfolgen finden
    for ins in md.disasm(code,CAVE):
        if ins.mnemonic=="pop" and "r6, r7, pc" in ins.op_str and "e" not in ends: ends["e"]=ins.address+ins.size
        if ins.mnemonic=="pop" and ins.op_str=="{pc}":
            if "c" not in ends: ends["c"]=ins.address+ins.size
            elif "i" in ends and "h" not in ends: ends["h"]=ins.address+ins.size
        if ins.mnemonic=="bx" and ins.op_str=="lr" and "i" not in ends: ends["i"]=ins.address+ins.size
    al=lambda a:(a+3)&~3
    offs={}
    offs["flagp_a"]=al(ends["e"])-CAVE; offs["legp"]=offs["flagp_a"]+4; offs["stap"]=offs["legp"]+4
    offs["helper_count"]=offs["stap"]+4
    offs["flagp_b"]=al(ends["c"])-CAVE
    offs["helper_iv"]=offs["flagp_b"]+4
    offs["flagp_c"]=al(ends["i"])-CAVE
    offs["helper_hold"]=offs["flagp_c"]+4
    offs["maxp"]=al(ends["h"])-CAVE
    offs["end_code"]=offs["maxp"]+4
    code_len=offs["end_code"]
    assert code_len==len(code),(code_len,len(code))
    flag_addr=CAVE+code_len
    leg_addr=flag_addr+4
    sta_addr=leg_addr+2*len(LEG)
    final=base_src.replace("FINDRATE",str(FIND_RATE_DEFAULT)).replace("FLAGADDR",hex(flag_addr)).replace("LEGADDR",hex(leg_addr)).replace("STAADDR",hex(sta_addr))
    enc,_=ks.asm(final,CAVE); code=bytes(enc)
    assert len(code)==code_len
    code=fix_bl(code,final)
    data=struct.pack("<I",0)+b"".join(struct.pack("<H",x) for x in LEG)+b"".join(struct.pack("<H",x) for x in STA)
    blob=code+data
    syms={k:CAVE+v for k,v in offs.items()}
    syms.update(helper_entry=CAVE,flag=flag_addr,leg=leg_addr,sta=sta_addr)
    return blob,syms
if __name__=="__main__":
    blob,syms=build()
    print(len(blob),{k:hex(v) for k,v in syms.items()})
    open("cave.bin","wb").write(blob)
