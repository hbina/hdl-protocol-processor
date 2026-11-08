# Study assumptions at the processor block boundary. No external ROM, pads or
# synchronizers are implemented here. Integrators must budget those separately.
create_clock -name execution -period 20.0 [get_ports clk]
set_clock_uncertainty 0.2 [get_clocks execution]
set_clock_transition 0.1 [get_clocks execution]
set signal_inputs [get_ports {reset instruction* inputs*}]
if {[llength $signal_inputs] != 41} { error "expected all 41 non-clock input bits" }
if {[llength [all_outputs]] != 122} { error "expected all 122 state output bits" }
set_input_delay -clock execution -max 5.0 $signal_inputs
set_input_delay -clock execution -min 0.5 $signal_inputs
set_input_transition 0.1 $signal_inputs
set_output_delay -clock execution -max 5.0 [all_outputs]
set_output_delay -clock execution -min 0.5 [all_outputs]
set_load 0.01 [all_outputs]
