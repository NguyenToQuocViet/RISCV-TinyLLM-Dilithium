#-------------------------------------------------------------------------------
# File        : core_top_ooc.tcl
# Description : Vivado out-of-context synthesis of core_top with the CORE-D3
#               pass check (0 errors, 0 critical warnings, 0 latches).
# Author      : Claude Code (Anthropic)
# Reviewer    : Viet Nguyen To Quoc
# Date        : 2026-11-10
#-------------------------------------------------------------------------------
# Normal use: make synth [PART=...] [PROFILE=...]
# Direct use: vivado -mode batch -source core_top_ooc.tcl \
#                    -tclargs <out_dir> [part] [core_profile]
# Exit 0 only when the run meets CORE-D3.

if {$argc < 1} {
    puts "ERROR: usage: -tclargs <out_dir> \[part\] \[core_profile\]"
    exit 2
}
set out_dir [file normalize [lindex $argv 0]]
set part    [expr {$argc > 1 ? [lindex $argv 1] : "xczu7ev-ffvc1156-2-e"}]
set profile [expr {$argc > 2 ? [lindex $argv 2] : 0}]
file mkdir $out_dir

# sources come from core_top.f, found from this script, so the run may start
# in any directory; paths in the list are relative to the list
set root [file normalize [file join [file dirname [info script]] .. ..]]
set fh [open $root/core_top.f]
set files {}
foreach line [split [read $fh] "\n"] {
    set line [string trim $line]
    if {$line ne ""} { lappend files [file join $root $line] }
}
close $fh
read_verilog -sv $files

# a failed profile check must stop the run with a non-zero exit
if {[catch {
    synth_design -top core_top -part $part -mode out_of_context \
                 -generic CORE_PROFILE=$profile
} err]} {
    puts "SYNTH_FAILED: $err"
    exit 1
}

report_utilization -file $out_dir/utilization.rpt
report_utilization -hierarchical -file $out_dir/utilization_hier.rpt
write_checkpoint -force $out_dir/core_top_synth.dcp

# estimated timing, report only: a nominal clock after synthesis, no target
set period 10.000
create_clock -period $period -name clk [get_ports clk]
set path [lindex [get_timing_paths -max_paths 1 -setup] 0]
set wns  [get_property SLACK $path]
puts "CORE_TIMING est_fmax_mhz=[format %.0f [expr {1000.0 / ($period - $wns)}]]\
 levels=[get_property LOGIC_LEVELS $path]\
 from=[get_property STARTPOINT_PIN $path] to=[get_property ENDPOINT_PIN $path]"
report_timing -max_paths 10 -file $out_dir/timing.rpt

# CORE-D3 pass check
set n_err  [get_msg_config -count -severity {ERROR}]
set n_crit [get_msg_config -count -severity {CRITICAL WARNING}]
set n_ltch [llength [get_cells -hier -quiet -filter {REF_NAME =~ LD*}]]
set verdict [expr {$n_err == 0 && $n_crit == 0 && $n_ltch == 0 ? "PASS" : "FAIL"}]
puts "CORE_SYNTH $verdict: errors=$n_err critical=$n_crit latches=$n_ltch part=$part profile=$profile"
puts "CORE_SYNTH utilization: $out_dir/utilization.rpt"
exit [expr {$verdict eq "PASS" ? 0 : 1}]
