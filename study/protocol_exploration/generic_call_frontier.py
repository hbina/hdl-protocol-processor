"""One-level generic CALL/RET extension of the frozen eight-register study.

CALL uses opcode0,bit10 plus a10-bit target; RET is0x0800. A10-bit link
register saves PC+1. No protocol state or arithmetic is implemented in RTL.
"""

from generic_frontier import replace
from isa_variants import assemble_call_frontier
from generic_frontier import expanded_source as base_source


def assemble(source):
    return assemble_call_frontier(source)


def expanded_source():
    source = base_source()
    source = replace(source, "reg [9:0] pc;", "reg [9:0] pc;\n  reg [9:0] return_pc;")
    source = replace(
        source, "registers[7] <= 8'h00;", "registers[7] <= 8'h00; return_pc <= 0;", 2
    )
    source = replace(
        source,
        """OP_NOP: begin
            pc <= pc + 1'b1;
          end""",
        """OP_NOP: begin
            if (instruction[11]) pc <= return_pc;
            else if (instruction[10]) begin
              return_pc <= pc + 1'b1;
              pc <= instruction[9:0];
            end else pc <= pc + 1'b1;
          end""",
    )
    return source
