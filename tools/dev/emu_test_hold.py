import sys,struct,random,os
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from unicorn import *
from unicorn.arm_const import *
import build_cave as B
blob,syms=B.build(); CAVE=B.CAVE
def go(held,rate_roll,charm_roll):
    mu=Uc(UC_ARCH_ARM,UC_MODE_THUMB)
    mu.mem_map(0x2000000,0x200000); mu.mem_map(0x3000000,0x10000)
    mu.mem_write(CAVE,blob)
    mu.mem_write(0x2090000,struct.pack("<HHBBBB",16,held,3,7,0,0))
    SP=0x3008000; LR=0x2100000
    regs={UC_ARM_REG_R4:0x2090000,UC_ARM_REG_R5:0x2091000,UC_ARM_REG_R6:0x66,UC_ARM_REG_R7:0x77,UC_ARM_REG_R1:0x11,UC_ARM_REG_R3:0x33}
    for k,v in regs.items(): mu.reg_write(k,v)
    mu.reg_write(UC_ARM_REG_SP,SP); mu.reg_write(UC_ARM_REG_LR,LR|1)
    calls=[]
    def hook(uc,addr,size,ud):
        if addr!=0x2005748: return
        n=uc.reg_read(UC_ARM_REG_R0); calls.append(n)
        uc.reg_write(UC_ARM_REG_R0,rate_roll if len(calls)==1 else charm_roll)
        uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
    mu.hook_add(UC_HOOK_CODE,hook)
    mu.emu_start(syms['helper_hold']|1,LR,count=2000)
    return mu,calls
ok=0
for held in (0,0x1234,5):
    for rate_roll in (0,1,19):
        for charm_roll in range(17):
            mu,calls=go(held,rate_roll,charm_roll)
            r2=mu.reg_read(UC_ARM_REG_R2); r0=mu.reg_read(UC_ARM_REG_R0)
            assert r0==0x27e,hex(r0)
            assert mu.reg_read(UC_ARM_REG_SP)==0x3008000
            assert mu.reg_read(UC_ARM_REG_R4)==0x2090000 and mu.reg_read(UC_ARM_REG_R5)==0x2091000
            assert mu.reg_read(UC_ARM_REG_R6)==0x66 and mu.reg_read(UC_ARM_REG_R7)==0x77
            if held!=0:
                assert r2==held and calls==[],(held,r2,calls)
            elif rate_roll==0:
                assert r2==548+charm_roll and calls==[B.FIND_RATE_DEFAULT,17],(r2,calls)
            else:
                assert r2==0 and calls==[B.FIND_RATE_DEFAULT]
            ok+=1
print("helper_hold ok:",ok)
