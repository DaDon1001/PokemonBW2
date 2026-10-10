import sys,struct; sys.path.insert(0,__import__('os').path.dirname(__import__('os').path.abspath(__file__)))
from unicorn import *
from unicorn.arm_const import *
import build_cave as B
blob,syms=B.build(); CAVE=B.CAVE
def go(entry,flags,bag,regs):
    mu=Uc(UC_ARCH_ARM,UC_MODE_THUMB)
    mu.mem_map(0x2000000,0x200000); mu.mem_map(0x3000000,0x10000)
    mu.mem_write(CAVE,blob); mu.mem_write(syms['flag'],struct.pack("<I",flags))
    mu.mem_write(0x2091000,struct.pack("<I",0x2095000))
    SP=0x3008000; LR=0x2100000
    for k,v in regs.items(): mu.reg_write(k,v)
    mu.reg_write(UC_ARM_REG_SP,SP); mu.reg_write(UC_ARM_REG_LR,LR|1)
    def hook(uc,addr,size,ud):
        r0=uc.reg_read(UC_ARM_REG_R0); r1=uc.reg_read(UC_ARM_REG_R1)
        if addr==0x2017354: uc.reg_write(UC_ARM_REG_R0,0x3001000)
        elif addr==0x2008474:
            assert r1==0x278 and uc.reg_read(UC_ARM_REG_R2)==1 and uc.reg_read(UC_ARM_REG_R3)==4
            uc.reg_write(UC_ARM_REG_R0,1 if bag.get(r1,0)>=1 else 0)
        else: return
        uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
    mu.hook_add(UC_HOOK_CODE,hook)
    mu.emu_start(entry|1,LR,count=5000)
    return mu
ok=0
for flags in range(16):
    for has_key in (0,1):
        regs={UC_ARM_REG_R4:0x2090000,UC_ARM_REG_R5:0x2091000,UC_ARM_REG_R6:0xdead,UC_ARM_REG_R7:0xbeef}
        mu=go(syms['helper_count'],flags,{0x278:has_key},regs)
        r6=mu.reg_read(UC_ARM_REG_R6); r0=mu.reg_read(UC_ARM_REG_R0)
        exp=130560 if flags&1 else (3 if has_key else 1)
        assert r6==exp and r0==exp,(flags,has_key,r6,r0)
        assert mu.reg_read(UC_ARM_REG_R4)==0x2090000 and mu.reg_read(UC_ARM_REG_R5)==0x2091000 and mu.reg_read(UC_ARM_REG_R7)==0xbeef
        assert mu.reg_read(UC_ARM_REG_SP)==0x3008000
        ok+=1
for flags in range(16):
    mu=go(syms['helper_iv'],flags,{},{UC_ARM_REG_R4:1,UC_ARM_REG_R5:2,UC_ARM_REG_R6:3,UC_ARM_REG_R7:4})
    r0=mu.reg_read(UC_ARM_REG_R0)
    exp=0x3FFFFFFF if flags&2 else 0xFFFFFFFF
    assert r0==exp,(flags,hex(r0))
    assert [mu.reg_read(r) for r in (UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7)]==[1,2,3,4]
    ok+=1
print("count/iv ok:",ok)
