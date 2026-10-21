# RST-D1 — Asynchronous Reset Assertion with Synchronous Release

**Type:** Technical architecture decision, not a coding-style preference.
**Decision owner:** Nguyễn Tô Quốc Việt — RISC-V subsystem owner.
**Decision:** Selected by the owner on 2026-10-21 after reviewing alternatives and trade-offs.
**Applies to:** R2 CPU-boundary contracts; RTL implementation and physical verification are pending.
**Supersedes:** The synchronous-reset choice in BASE R1, dated 2026-10-15.
**Behavioral authority:** [BASE reset architecture](../designs/5-stage-baseline-core.md#reset-architecture).

## Context and objective

Việt requires reset to invalidate core control state even when the core clock
has not started or is stopped. A synchronous reset cannot update that state
without a clock edge; a source pulse entirely within a clock stop could be
missed unless the system retains it and sequences clock restart and reset.
Direct asynchronous release avoids that dependency on assertion, but can
violate recovery/removal at many registers when release occurs near a clock edge.

## Selected approach

- Use asynchronous assertion and synchronous release for required reset state.
- Keep selective reset: reset validity, transaction/serialization ownership and
  other state needed for correctness; do not reset datapath payload just to
  obtain known waveforms. Exact reset values remain in the owning contracts.
- Write a portable SystemVerilog `reset_synchronizer`, outside the core, once
  per clock domain requiring this reset. Initially use two synchronization
  stages. Pipeline registers receive the conditioned `rst_n`; they do not each
  synchronize it independently.
- Keep vendor macros out of the core dependency. An AMD XPM implementation is
  an alternative integration implementation only if its contract is preserved
  and the responsible owner reviews the substitution.

This records the RISC-V owner's CPU/environment requirement, not project-level
acceptance of a concrete reset tree, PLL/clock-gate sequence, reset supervisor,
or reset implementation for another subsystem. Those remain shared review work.
The generic pipeline-register hold/flush interface, priority between those
controls and payload-update policy have not been selected by this reset decision.

## Alternatives and trade-offs

| Alternative | Benefit | Reason for the selection / accepted cost |
| --- | --- | --- |
| Synchronous reset throughout | Valid approach with favorable FPGA resource mapping in many cases | Does not itself reset state without a clock. Meeting the selected requirement would need additional source retention and clock/reset sequencing. |
| Asynchronous reset with direct source release | Resets without a clock and needs no release synchronizer | Arbitrary release timing exposes the functional reset network to recovery/removal failures; rejected for the chosen boundary. |
| Asynchronous assertion, synchronized release | Resets without a clock and controls release relative to the destination clock | Selected. Adds synchronization FFs per domain, release latency and implementation/verification obligations. |
| AMD `XPM_CDC_ASYNC_RST` | Vendor-provided synchronizer with FPGA integration support | Not the initial implementation: a small owned RTL module keeps the core environment portable and inspectable. Owning it also means owning its verification and target constraints. |

The selection prioritizes reset without a running clock, not a claim that
asynchronous reset always has better timing, area or FPGA inference. Synchronous
release does not eliminate metastability absolutely: the synchronizer reduces
failure probability, while placement and distribution timing still matter.

## Consequences, evidence limits and revisit conditions

The raw source release time need not be known. The synchronizer holds the core
in reset until its release sequence completes with a running, stable clock.
Clock availability is still required to resume execution. Source pulse width
and conditioning, recovery/removal, appropriate synchronizer attributes and
CDC/RDC checks remain target-specific responsibilities. An RC filter is not a
substitute for release synchronization.

Two stages are the initial structure, not an MTBF signoff. Revisit stage count
when target clock/library and reliability requirements are available; revisit
the implementation when adding clock domains, clock gating, a different FPGA
or ASIC flow. No PPA or metastability measurement was performed for this decision.

Reset does not undo accepted writes, prove DMA quiescence or make CPU-only reset
safe with live accelerator jobs. The existing OBI shared-reset flush and CI
coordinated-reset obligations remain in force.

Required regression includes assertion between clock edges and with the clock
stopped, source release while stopped, restart/release sequencing, assertion
during stalls and pending transfers, and no stale work after reset. The existing
EX harness uses synchronous reset and its prior pass is not R2 reset evidence.
This decision authorizes documentation updates, not RTL/test implementation.

## Reference evidence considered

- [Ibex IF-stage RTL](https://github.com/lowRISC/ibex/blob/master/rtl/ibex_if_stage.sv): asynchronous reset of pipeline-valid state, with selective payload reset depending on configuration.
- [CV32E40P IF-stage RTL](https://github.com/openhwgroup/cv32e40p/blob/master/rtl/cv32e40p_if_stage.sv): asynchronous reset of IF/ID registers.
- [PicoRV32 RTL](https://github.com/YosysHQ/picorv32/blob/main/picorv32.v): synchronous reset of CPU state and PC; evidence that synchronous reset is also a practical core implementation choice.
- [AMD UG949: reset alternatives](https://docs.amd.com/r/2023.1-English/ug949-vivado-design-methodology/Synchronous-Reset-vs.-Asynchronous-Reset): FPGA mapping trade-offs and the need to synchronize asynchronous-reset release.
- [AMD XPM asynchronous reset synchronizer](https://docs.amd.com/r/2021.1-English/ug1344-versal-architecture-libraries/XPM_CDC_ASYNC_RST): vendor implementation of asynchronous assertion and synchronous release.
- [AMD ASYNC_REG](https://docs.amd.com/r/en-US/ug912-vivado-properties/ASYNC_REG): preservation and placement support for synchronization chains.

These sources were inspected during the discussion; they establish available
mechanisms and trade-offs, not implementation signoff for this core.
