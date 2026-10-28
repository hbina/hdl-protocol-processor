# Pure combinational I/O timing. clk, rst_n and ena have no functional clock role.
# Use a virtual reference; zero external delays allocate 20 ns to input -> output.
create_clock -name comb_reference -period 20
set_input_delay 0 -clock comb_reference [all_inputs]
set_output_delay 0 -clock comb_reference [all_outputs]
set_driving_cell \
    -lib_cell [lindex [split $::env(SYNTH_DRIVING_CELL) "/"] 0] \
    -pin [lindex [split $::env(SYNTH_DRIVING_CELL) "/"] 1] \
    [all_inputs]
set_load [expr $::env(OUTPUT_CAP_LOAD) / 1000.0] [all_outputs]
set_max_fanout $::env(MAX_FANOUT_CONSTRAINT) [current_design]
if {[info exists ::env(MAX_TRANSITION_CONSTRAINT)]} {
    set_max_transition $::env(MAX_TRANSITION_CONSTRAINT) [current_design]
}
if {[info exists ::env(MAX_CAPACITANCE_CONSTRAINT)]} {
    set_max_capacitance $::env(MAX_CAPACITANCE_CONSTRAINT) [current_design]
}
set_clock_uncertainty $::env(CLOCK_UNCERTAINTY_CONSTRAINT) [get_clocks comb_reference]
set_clock_transition $::env(CLOCK_TRANSITION_CONSTRAINT) [get_clocks comb_reference]
set_timing_derate -early [expr 1 - $::env(TIME_DERATING_CONSTRAINT) / 100.0]
set_timing_derate -late [expr 1 + $::env(TIME_DERATING_CONSTRAINT) / 100.0]
