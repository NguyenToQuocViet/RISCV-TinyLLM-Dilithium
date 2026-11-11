PART      ?= xczu7ev-ffvc1156-2-e
PROFILE   ?= 0
SYNTH_OUT  = build/synth/$(PART)_p$(PROFILE)

.PHONY: lint synth

lint:
	@verilator --lint-only --Wall --top-module core_top -F core_top.f

# Vivado runs inside SYNTH_OUT, so vivado.log and .Xil/ stay there
synth:
	@mkdir -p $(SYNTH_OUT)
	@cd $(SYNTH_OUT) && \
	vivado -mode batch -nojournal -log vivado.log \
	       -source $(CURDIR)/scripts/synth/core_top_ooc.tcl \
	       -tclargs $(CURDIR)/$(SYNTH_OUT) $(PART) $(PROFILE) > /dev/null 2>&1; \
	status=$$?; \
	grep -E '^(CORE_SYNTH|CORE_TIMING|SYNTH_FAILED|ERROR|CRITICAL WARNING)' vivado.log; \
	exit $$status
