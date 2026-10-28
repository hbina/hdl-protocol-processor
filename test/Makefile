# Makefile
# See https://docs.cocotb.org/en/stable/quickstart.html for more info

# defaults
.DEFAULT_GOAL := sim
SIM ?= icarus
FST ?= -fst # Use more efficient FST format
TOPLEVEL_LANG ?= verilog
SRC_DIR = $(PWD)/../src
PROJECT_SOURCES = project.v combhdl_demo.v

# Verilator 5 requires an explicit timing mode for testbench delays.
ifeq ($(SIM),verilator)
COMPILE_ARGS += --timing
endif

ifneq ($(GATES),yes)

# RTL simulation:
SIM_BUILD				= sim_build/rtl/$(SIM)
VERILOG_SOURCES += $(addprefix $(SRC_DIR)/,$(PROJECT_SOURCES))

else

# Gate level simulation:
SIM_BUILD				= sim_build/gl
COMPILE_ARGS    += -DGL_TEST
COMPILE_ARGS    += -DFUNCTIONAL
COMPILE_ARGS    += -DSIM
IHP_STDCELL_MODEL = $(PDK_ROOT)/ihp-sg13cmos5l/libs.ref/sg13cmos5l_stdcell/verilog/sg13cmos5l_stdcell.v
IHP_FUNCTIONAL_MODEL = $(SIM_BUILD)/sg13cmos5l_stdcell_functional.v

VERILOG_SOURCES += $(PDK_ROOT)/ihp-sg13cmos5l/libs.ref/sg13cmos5l_io/verilog/sg13cmos5l_io.v
# The standard-cell models instantiate IHP UDP primitives (flip-flops and
# muxes), so the UDP library must be compiled before the cell library.
VERILOG_SOURCES += $(PDK_ROOT)/ihp-sg13cmos5l/libs.ref/sg13cmos5l_stdcell/verilog/sg13cmos5l_udp.v
VERILOG_SOURCES += $(IHP_FUNCTIONAL_MODEL)

# The pinned CMOS5L timing models feed DFFs through delayed_* nets driven by
# timing checks. Icarus does not implement those checks, so for FUNCTIONAL gate
# simulation connect the delayed nets directly to their corresponding inputs.
$(IHP_FUNCTIONAL_MODEL): $(IHP_STDCELL_MODEL)
	@mkdir -p $(dir $@)
	@awk '{ print; if ($$0 ~ /wire delayed_D, delayed_RESET_B, delayed_CLK;/) { print "`ifdef FUNCTIONAL"; print "\tassign delayed_D = D;"; print "\tassign delayed_RESET_B = RESET_B;"; print "\tassign delayed_CLK = CLK;"; print "`endif"; } }' $< > $@

# this gets copied in by the GDS action workflow
VERILOG_SOURCES += $(PWD)/gate_level_netlist.v

endif

# Allow sharing configuration between design and testbench via `include`:
COMPILE_ARGS 		+= -I$(SRC_DIR)

# Include the testbench sources:
VERILOG_SOURCES += $(PWD)/tb.v
TOPLEVEL = tb

# List test modules to run, separated by commas and without the .py suffix:
COCOTB_TEST_MODULES = demo
export GATES

# include cocotb's make rules to take care of the simulator setup
include $(shell cocotb-config --makefiles)/Makefile.sim
