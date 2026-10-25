"""Generic carry shifts/branch added to the frozen leaf-call study.

SHRC: logical right shift, carry=old bit0. RRC: shift right through carry.
JNC: branch if carry0. No CRC polynomial or protocol state is in hardware.
"""

from generic_call_frontier import assemble as base_assemble
from generic_call_frontier import expanded_source as base_source
from generic_frontier import base_assembler, replace


def assemble(source):
    parser = base_assembler()
    parsed, labels = parser._parse_lines(source)
    addresses = {}
    for name, address in labels.items():
        addresses.setdefault(address, []).append(name)
    lowered = []
    for index, (_line, opcode, args) in enumerate(parsed):
        lowered += [f"{name}:" for name in addresses.get(index, [])]
        op = {"SHRC": "SHR", "RRC": "ROR", "JNC": "JFAIL"}.get(opcode, opcode)
        lowered.append(op + " " + ", ".join(args))
    lowered += [f"{name}:" for name in addresses.get(len(parsed), [])]
    words = base_assemble("\n".join(lowered))
    for index, (_line, opcode, _args) in enumerate(parsed):
        if opcode in {"SHRC", "RRC"}:
            words[index] |= 0x20000
        elif opcode == "JNC":
            words[index] |= 0x100
    return words


def expanded_source():
    source = base_source()
    source = replace(
        source, "reg [9:0] return_pc;", "reg [9:0] return_pc;\n  reg carry_flag;"
    )
    source = replace(source, "return_pc <= 0;", "return_pc <= 0; carry_flag <= 0;", 2)
    source = replace(
        source,
        "!operand_a[3] || !condition_flag",
        "!operand_a[3] || !(operand_a[0] ? carry_flag : condition_flag)",
    )
    start, end = source.index("OP_SHIFT: begin"), source.index("OP_BIT: begin")
    block = source[start:end]
    block = replace(
        block,
        "case (operation)",
        """if (instruction[17]) begin
              if (operation == 1 || operation == 3) begin
                carry_flag <= registers[register_d][0];
                registers[register_d] <= {operation == 3 ? carry_flag : 1'b0, registers[register_d][7:1]};
              end else halted <= 1;
            end else case (operation)""",
    )
    return source[:start] + block + source[end:]
