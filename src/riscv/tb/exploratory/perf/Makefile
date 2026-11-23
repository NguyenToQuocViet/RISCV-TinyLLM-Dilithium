#------------------------------------------------------------------------------
# File        : Makefile
# Description : Perf bench: Verilator C++ bench for core_top, CoreMark (flag
#               sets A and B), Dhrystone, straight-line fetch probe, gate run
#               and post-route fmax. Outputs in build/perf/.
# Author      : Claude Code (Anthropic)
# Date        : 2026-11-20
#------------------------------------------------------------------------------
# Use from src/riscv: make -C tb/exploratory/perf all | fmax

ROOT   := $(abspath ../../..)
B      := $(ROOT)/build/perf
SW     := $(abspath ../sw)
PY     := $(ROOT)/.venv/bin/python
PREFIX ?= /opt/Xilinx/2026.1/Vitis/gnu/riscv/lin/bin/riscv64-unknown-elf-
CC     := $(PREFIX)gcc
TB     := $(B)/obj/tb_perf
ITER   ?= 10

BASEFLAGS := -march=rv32i -mabi=ilp32 -nostdlib -nostartfiles -ffreestanding \
             -mstrict-align -msmall-data-limit=0 -mno-relax -Wl,--build-id=none \
             -T $(SW)/link.ld
START     := $(SW)/start.S $(SW)/common.c

# CoreMark flag sets: A neutral, B as lowRISC Ibex core_portme.mak
FLAGS_A := -O2
FLAGS_B := -O3 -falign-functions=16 -funroll-all-loops -finline-functions \
           -falign-jumps=4 -mtune=sifive-3-series -mcmodel=medlow
CM_SRC  := $(addprefix coremark/,core_list_join.c core_main.c core_matrix.c \
           core_state.c core_util.c) port_coremark/core_portme.c port_coremark/ee_printf.c
CM_DEF  := -DPERFORMANCE_RUN=1 -DTOTAL_DATA_SIZE=2000 -DMAIN_HAS_NOARGC=1 \
           -DHAS_FLOAT=0 -Iport_coremark -Icoremark

# Dhrystone: riscv-tests benchmarks Makefile options
DH_DIR   := ../isa/riscv-tests/benchmarks/dhrystone
DH_FLAGS := -std=gnu99 -O2 -ffast-math -fno-common -fno-builtin-printf \
            -fno-tree-loop-distribute-patterns -Wno-implicit-int \
            -Wno-implicit-function-declaration -Wno-return-type -Iport_dhry

.PHONY: all tb gate sw run fmax clean-perf

all: tb gate sw run

tb: $(TB)
$(TB): tb_perf.cpp $(wildcard $(ROOT)/rtl/*.sv) $(ROOT)/core_top.f
	cd $(ROOT) && verilator --cc --exe --build -j 8 -O3 --x-assign fast --x-initial fast \
	  --public-flat-rw -Wno-fatal -Wno-lint -Wno-style --top-module core_top \
	  -F core_top.f tb/exploratory/perf/tb_perf.cpp -Mdir $(B)/obj -o tb_perf

# ELF -> flat image at address 0, after the BASE operation gate. EBREAK is let
# through only as a compiler trap on a dead path; its PCs go to .traps and the
# bench fails if one reaches EX.
define image
	$(PY) -c "import sys; sys.path.insert(0, '$(abspath ..)'); import xp_sw, pathlib; \
	  xp_sw.BASE_OPS.add('ebreak'); \
	  h = xp_sw.check_ops(pathlib.Path('$(1).elf')); print('ops ok', '$(notdir $(1))', sum(h.values()), 'ebreak', h['ebreak'])"
	$(PREFIX)objdump -d $(1).elf | awk '/\tebreak/{sub(":","",$$1); printf "0x%s ", $$1}' > $(1).traps
	$(PREFIX)objcopy -O binary $(1).elf $(1).bin
	$(PREFIX)size $(1).elf | tail -1
endef

sw: $(B)/sw/coremark_A.bin $(B)/sw/coremark_B.bin $(B)/sw/dhrystone.bin $(B)/sw/straight.bin

$(B)/sw/coremark_%.bin: $(CM_SRC) $(START)
	mkdir -p $(B)/sw
	$(CC) $(FLAGS_$*) $(BASEFLAGS) $(CM_DEF) -DITERATIONS=$(ITER) \
	  -DFLAGS_STR='"$(strip $(FLAGS_$*))"' $(START) $(CM_SRC) -lgcc -o $(B)/sw/coremark_$*.elf
	$(call image,$(B)/sw/coremark_$*)

$(B)/sw/dhrystone.bin: $(DH_DIR)/dhrystone.c $(DH_DIR)/dhrystone_main.c port_dhry/util.h port_dhry/syscalls.c $(START)
	mkdir -p $(B)/sw
	$(CC) $(DH_FLAGS) $(BASEFLAGS) $(START) port_dhry/syscalls.c \
	  $(DH_DIR)/dhrystone.c $(DH_DIR)/dhrystone_main.c -Wl,--wrap=debug_printf -lgcc -o $(B)/sw/dhrystone.elf
	$(call image,$(B)/sw/dhrystone)

$(B)/sw/straight.bin: straight.S $(START)
	mkdir -p $(B)/sw
	$(CC) $(BASEFLAGS) $(START) straight.S -o $(B)/sw/straight.elf
	$(call image,$(B)/sw/straight)

# each benchmark twice: the cycle counts must match (deterministic sim)
run: $(TB) sw
	for p in straight coremark_A coremark_B dhrystone; do \
	  for k in 1 2; do $(TB) $(B)/sw/$$p.bin 400000000 $$(cat $(B)/sw/$$p.traps) > $(B)/sw/$$p.run$$k.log 2>&1 || exit 1; done; \
	  cmp -s $(B)/sw/$$p.run1.log $(B)/sw/$$p.run2.log && echo "$$p: two runs identical" || { echo "$$p: runs differ"; exit 1; }; \
	  grep "TB_END\|TB_WINDOW" $(B)/sw/$$p.run1.log; \
	done

# TB gate: riscv-tests rv32ui (fence_i, ma_data are the existing skips), negatives, SW KAT
gate: $(TB)
	mkdir -p $(B)/gate
	pass=0; fail=0; for e in ../isa/build/*.elf; do b=$$(basename $$e .elf); \
	  case $$b in fence_i|ma_data|*_xp_*) continue;; esac; \
	  $(PREFIX)objcopy -O binary $$e $(B)/gate/$$b.bin; \
	  $(TB) $(B)/gate/$$b.bin 2000000 > $(B)/gate/$$b.log 2>&1; \
	  if [ $$? = 0 ] && grep -aq "status=1" $(B)/gate/$$b.log; then pass=$$((pass+1)); else fail=$$((fail+1)); echo "FAIL $$b"; fi; \
	done; echo "GATE rv32ui pass=$$pass fail=$$fail"; [ $$fail = 0 ]
	for b in p1_basic_O2 p2_fib_O2 p3_sha3_O2 p1_basic_O2_force_fail; do \
	  $(PREFIX)objcopy -O binary $(SW)/build/$$b.elf $(B)/gate/$$b.bin; \
	  $(TB) $(B)/gate/$$b.bin 20000000 > $(B)/gate/$$b.log 2>&1; echo "GATE $$b rc=$$?"; done

fmax:
	for t in 3.0 3.5; do mkdir -p $(B)/impl_$$t; \
	  ( cd $(B)/impl_$$t && vivado -mode batch -nojournal -source $(CURDIR)/impl_fmax.tcl \
	    -tclargs . $$t > run.log 2>&1 ) & done; wait
	grep -h IMPL_RESULT $(B)/impl_*/run.log
