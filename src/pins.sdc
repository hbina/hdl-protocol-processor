# Pin processor: 50 MHz, board-clocked configuration and asynchronous GPIO.
source $::env(SCRIPTS_DIR)/base.sdc

# Except only pad -> first synchronizer D. Keep stage-to-stage timing intact.
set first_stage_nets [get_nets -hierarchical *pin_sync_meta*]
set first_stage_count 0
foreach net $first_stage_nets {
    foreach pin [get_pins -of_objects $net] {
        if {[get_property $pin direction] == "output"} {
            set cell [get_cells -of_objects $pin]
            set d_pin [get_pins "[get_property $cell full_name]/D"]
            if {[llength $d_pin] == 1} {
                set_false_path -from [get_ports {ui_in[*] uio_in[*]}] -to $d_pin
                incr first_stage_count
            }
        }
    }
}
if {$first_stage_count != 15} { error "expected 15 first-stage GPIO synchronizers, found $first_stage_count" }
# Configuration paths retain base.sdc clock and I/O constraints.
