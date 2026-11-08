read_liberty /OpenROAD-flow-scripts/flow/platforms/sky130hd/lib/sky130_fd_sc_hd__tt_025C_1v80.lib
read_db /work/build/orfs/results/sky130hd/bitlogic_processor/base/6_final.odb
read_sdc /work/build/orfs/results/sky130hd/bitlogic_processor/base/6_final.sdc
read_spef /work/build/orfs/results/sky130hd/bitlogic_processor/base/6_final.spef
puts "BEGIN_CONSTRAINT_AUDIT"
set checks_passed [check_setup -verbose]
puts "CHECK_SETUP_RESULT=$checks_passed"
if {!$checks_passed} { error "constraint sanity checks failed" }
puts "END_CONSTRAINT_AUDIT"
report_worst_slack -max
report_worst_slack -min
report_check_types -max_slew -max_capacitance -max_fanout -violators
