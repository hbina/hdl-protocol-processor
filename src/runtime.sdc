# Runtime v1: 50 MHz core, unchanged board-clocked configuration interface.
# Retain the pinned flow's clock, 4 ns I/O delays, loads and corner derates.
source $::env(SCRIPTS_DIR)/base.sdc

# Runtime request is asynchronous ONLY at its first synchronizer flop.
# Locate the mapped flop through the kept Q net, rather than synthesis cell IDs.
set meta_net [get_nets {bridge.request_meta}]
if {[llength $meta_net] != 1} { error "runtime request synchronizer net missing" }
set meta_d {}
foreach pin [get_pins -of_objects $meta_net] {
    if {[get_property $pin direction] == "output"} {
        set cell [get_cells -of_objects $pin]
        set meta_d [get_pins "[get_property $cell full_name]/D"]
    }
}
if {[llength $meta_d] != 1} { error "runtime request synchronizer D pin missing" }
set_false_path -from [get_ports {ui_in[6]}] -to $meta_d

# Bundled token data must be stable before request toggles and remain held
# through acknowledgement. Two synchronizer stages plus one settling cycle
# precede capture. Keep conservative single-cycle timing on every token path
# (including the legacy loader), instead of cutting the held data bus.
set_max_delay 16 -from [get_ports {ui_in[0] ui_in[1] ui_in[2] ui_in[3] ui_in[4] ui_in[5]}]
