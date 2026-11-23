#-------------------------------------------------------------------------------
# File        : impl_fmax.tcl
# Description : Out-of-context synth + place + route of core_top at one clock
#               period; prints post-route WNS, fmax and utilization.
#               Reg-to-reg paths only (no IO constraints).
# Author      : Claude Code (Anthropic)
# Date        : 2026-11-20
#-------------------------------------------------------------------------------
# Use: vivado -mode batch -source impl_fmax.tcl -tclargs <out_dir> <period_ns> [part]

set out_dir [file normalize [lindex $argv 0]]
set period  [lindex $argv 1]
set part    [expr {$argc > 2 ? [lindex $argv 2] : "xczu7ev-ffvc1156-2-e"}]
file mkdir $out_dir

set root [file normalize [file join [file dirname [info script]] .. .. ..]]
set fh [open $root/core_top.f]
set files {}
foreach line [split [read $fh] "\n"] {
    set line [string trim $line]
    if {$line ne ""} { lappend files [file join $root $line] }
}
close $fh
read_verilog -sv $files

synth_design -top core_top -part $part -mode out_of_context
create_clock -period $period -name clk [get_ports clk]
opt_design
place_design
phys_opt_design
route_design

set path [lindex [get_timing_paths -max_paths 1 -setup] 0]
set wns  [get_property SLACK $path]
report_timing_summary -file $out_dir/timing_summary.rpt
report_timing -max_paths 5 -file $out_dir/timing.rpt
report_utilization -file $out_dir/utilization.rpt
puts "IMPL_RESULT period_ns=$period wns_ns=$wns fmax_mhz=[format %.1f [expr {1000.0 / ($period - $wns)}]]\
 levels=[get_property LOGIC_LEVELS $path] part=$part (LUT/FF: utilization.rpt)"
exit 0
