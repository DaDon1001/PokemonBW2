"""Emulator-Test fuer helper_entry: 17 Edelsteine (548..564) als Charms, Gruppen 8/4/3/2."""
import os, random, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from unicorn import *
from unicorn.arm_const import *
import build_cave as B

blob, syms = B.build()
CAVE = B.CAVE
GROUP_OF = {i: bit for bit, ids in B.GROUPS for i in ids}


def run_entry(bag):
    mu = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
    mu.mem_map(0x2000000, 0x200000)
    mu.mem_map(0x3000000, 0x10000)
    mu.mem_write(CAVE, blob)
    mu.mem_write(0x2090000, struct.pack("<HHBBBB", 16, 0, 3, 7, 0, 0))
    mu.mem_write(0x2091000, struct.pack("<I", 0x2095000))
    SP, LR = 0x3008000, 0x2100000
    for k, v in {UC_ARM_REG_R4: 0x2090000, UC_ARM_REG_R5: 0x2091000, UC_ARM_REG_R6: 0x1111,
                 UC_ARM_REG_R7: 0x2222}.items():
        mu.reg_write(k, v)
    mu.reg_write(UC_ARM_REG_SP, SP)
    mu.reg_write(UC_ARM_REG_LR, LR | 1)
    takes = []

    def hook(uc, addr, size, ud):
        r0, r1 = uc.reg_read(UC_ARM_REG_R0), uc.reg_read(UC_ARM_REG_R1)
        if addr == 0x2017354:
            uc.reg_write(UC_ARM_REG_R0, 0x3001000)
        elif addr == 0x200842c:
            assert r0 == 0x3001000 and uc.reg_read(UC_ARM_REG_R3) == 4 and uc.reg_read(UC_ARM_REG_R2) == 1
            takes.append(r1)
            if bag.get(r1, 0) >= 1:
                bag[r1] -= 1
                uc.reg_write(UC_ARM_REG_R0, 1)
            else:
                uc.reg_write(UC_ARM_REG_R0, 0)
        elif addr == 0x2005748:
            uc.reg_write(UC_ARM_REG_R0, random.randrange(r0))
        else:
            return
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
    mu.hook_add(UC_HOOK_CODE, hook)
    mu.emu_start(CAVE | 1, LR, count=30000)
    return mu, takes


ok = 0
all_ids = list(range(548, 565))
rng = random.Random(1)
cases = [[]] + [[i] for i in all_ids] + [rng.sample(all_ids, rng.randrange(2, 8)) for _ in range(60)] + [all_ids]
for have in cases:
    for _ in range(3):
        bag = {i: 1 for i in have}
        bag[999] = 5  # fremdes Item darf nie beruehrt werden
        mu, takes = run_entry(bag)
        assert mu.reg_read(UC_ARM_REG_SP) == 0x3008000
        assert mu.reg_read(UC_ARM_REG_R4) == 0x2090000 and mu.reg_read(UC_ARM_REG_R5) == 0x2091000
        assert sorted(takes) == all_ids, "es muessen genau die 17 Gems abgefragt werden"
        assert all(bag[i] == 0 for i in have) and bag[999] == 5
        flags = struct.unpack("<I", mu.mem_read(syms['flag'], 4))[0]
        exp = 0
        for i in have:
            exp |= 1 << GROUP_OF[i]
        assert flags == exp, (have, flags, exp)
        spec, = struct.unpack("<H", mu.mem_read(0x2090000, 2))
        form = mu.mem_read(0x2090005, 1)[0]
        assert mu.reg_read(UC_ARM_REG_R0) == spec and mu.reg_read(UC_ARM_REG_R1) == form
        if exp & 4:
            assert spec in B.LEG and form == 0
        elif exp & 8:
            assert spec in B.STA and form == 0
        else:
            assert spec == 16 and form == 7
        ok += 1
print("helper_entry ok:", ok)
