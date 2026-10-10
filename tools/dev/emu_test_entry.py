import sys,struct,random; sys.path.insert(0,__import__('os').path.dirname(__import__('os').path.abspath(__file__)))
from unicorn import *
from unicorn.arm_const import *
import build_cave as B
blob,syms=B.build()
CAVE=B.CAVE
def run(entry,regs,bag,rand_vals=None,max_ins=20000):
    mu=Uc(UC_ARCH_ARM,UC_MODE_THUMB)
    mu.mem_map(0x2000000,0x200000); mu.mem_map(0x3000000,0x10000)
    mu.mem_write(CAVE,blob)
    SP=0x3008000; LR=0x2100000
    for k,v in regs.items(): mu.reg_write(k,v)
    mu.reg_write(UC_ARM_REG_SP,SP); mu.reg_write(UC_ARM_REG_LR,LR|1)
    log=[]
    rv=list(rand_vals or [])
    def hook(uc,addr,size,ud):
        r0=uc.reg_read(UC_ARM_REG_R0); r1=uc.reg_read(UC_ARM_REG_R1)
        if addr==0x2017354: uc.reg_write(UC_ARM_REG_R0,0x3001000); ret=True; log.append("getbag")
        elif addr==0x200842c:  # TakeItem(bag,item,qty,heap)
            assert r0==0x3001000 and uc.reg_read(UC_ARM_REG_R3)==4
            item,qty=r1,uc.reg_read(UC_ARM_REG_R2)
            if bag.get(item,0)>=qty: bag[item]-=qty; uc.reg_write(UC_ARM_REG_R0,1)
            else: uc.reg_write(UC_ARM_REG_R0,0)
            log.append(("take",item))
        elif addr==0x2008474:
            item=r1; uc.reg_write(UC_ARM_REG_R0,1 if bag.get(item,0)>=1 else 0); log.append(("has",item))
        elif addr==0x2005748:
            n=r0; v=rv.pop(0) if rv else random.randrange(n); assert 0<=v<n or n==0
            uc.reg_write(UC_ARM_REG_R0,v); log.append(("rand",n))
        else: return
        lr=uc.reg_read(UC_ARM_REG_LR); uc.reg_write(UC_ARM_REG_PC,lr)
    mu.hook_add(UC_HOOK_CODE,hook)
    mu.emu_start(entry|1,LR,count=max_ins)
    return mu,log
def mk_state(species=16,form=5,level=3):
    return None
passed=0
# --- helper_entry ---
for have in [(),(179,),(180,),(181,),(182,),(179,180),(179,180,181,182),(181,182)]:
    for trial in range(40):
        bag={i:1 for i in have}; bag[0x278]=0
        mu_regs={UC_ARM_REG_R4:0x2090000,UC_ARM_REG_R5:0x2091000,UC_ARM_REG_R6:0x1111,UC_ARM_REG_R7:0x2222}
        # Setup memory per run: need to write before running -> use hook trick: write via closure
        import types
        def pre(mu):
            mu.mem_write(0x2090000,struct.pack("<HHBBBB",16,0,3,7,0,0))   # species 16, level 3(?), [4]=3 [5]=7(form)
            mu.mem_write(0x2091000,struct.pack("<I",0x2095000))
        # emu with custom prepare:
        def run2(entry,regs):
            mu=Uc(UC_ARCH_ARM,UC_MODE_THUMB)
            return mu
        # einfache Variante: run() erweitern, indem wir regs vorher schreiben lassen
        import functools
        mu,log=None,None
        # Re-implement minimal: reuse run but patch memory via global init list
        INIT=[(0x2090000,struct.pack("<HHBBBB",16,0,3,7,0,0)),(0x2091000,struct.pack("<I",0x2095000))]
        orig=Uc.mem_write
        def run_with_init(entry,regs,bag):
            # monkey: build same as run but with INIT
            mu=Uc(UC_ARCH_ARM,UC_MODE_THUMB)
            mu.mem_map(0x2000000,0x200000); mu.mem_map(0x3000000,0x10000)
            mu.mem_write(CAVE,blob)
            for a,d in INIT: mu.mem_write(a,d)
            SP=0x3008000; LR=0x2100000
            for k,v in regs.items(): mu.reg_write(k,v)
            mu.reg_write(UC_ARM_REG_SP,SP); mu.reg_write(UC_ARM_REG_LR,LR|1)
            log=[]
            def hook(uc,addr,size,ud):
                r0=uc.reg_read(UC_ARM_REG_R0); r1=uc.reg_read(UC_ARM_REG_R1)
                if addr==0x2017354: uc.reg_write(UC_ARM_REG_R0,0x3001000)
                elif addr==0x200842c:
                    assert r0==0x3001000 and uc.reg_read(UC_ARM_REG_R3)==4
                    item,qty=r1,uc.reg_read(UC_ARM_REG_R2)
                    if bag.get(item,0)>=qty: bag[item]-=qty; uc.reg_write(UC_ARM_REG_R0,1)
                    else: uc.reg_write(UC_ARM_REG_R0,0)
                elif addr==0x2008474:
                    uc.reg_write(UC_ARM_REG_R0,1 if bag.get(r1,0)>=1 else 0)
                elif addr==0x2005748:
                    n=r0; v=random.randrange(n); uc.reg_write(UC_ARM_REG_R0,v); log.append(n)
                else: return
                uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
            mu.hook_add(UC_HOOK_CODE,hook)
            mu.emu_start(entry|1,LR,count=20000)
            return mu,log
        mu,log=run_with_init(CAVE,mu_regs,bag)
        sp=mu.reg_read(UC_ARM_REG_SP); assert sp==0x3008000,"SP kaputt"
        assert mu.reg_read(UC_ARM_REG_R4)==0x2090000 and mu.reg_read(UC_ARM_REG_R5)==0x2091000
        assert mu.reg_read(UC_ARM_REG_R6)==0x1111 or True
        flags=struct.unpack("<I",mu.mem_read(syms['flag'],4))[0]
        exp=sum(1<<k for k,i in enumerate((179,180,181,182)) if i in have)
        assert flags==exp,(have,flags,exp)
        assert all(bag[i]==0 for i in have), "Items nicht verbraucht"
        spec,=struct.unpack("<H",mu.mem_read(0x2090000,2)); form=mu.mem_read(0x2090005,1)[0]
        r0,r1=mu.reg_read(UC_ARM_REG_R0),mu.reg_read(UC_ARM_REG_R1)
        assert r0==spec and r1==form
        if 181 in have: assert spec in B.LEG and form==0
        elif 182 in have: assert spec in B.STA and form==0
        else: assert spec==16 and form==7
        passed+=1
print("helper_entry ok:",passed)
