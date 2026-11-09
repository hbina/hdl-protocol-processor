use bitlogic::{Bits, LogicValue, bits, logic};

#[derive(Clone, Copy, LogicValue)]
pub struct ProcessorState {
    pub pc: Bits<8>,
    pub wait: Bits<16>,
    pub pins: Bits<8>,
    pub halted: bool,
    pub fault: bool,
    pub scratch: Bits<64>,
    pub count: Bits<16>,
    pub enables: Bits<8>,
}
#[derive(Clone, Copy, LogicValue)]
pub struct StepInput {
    pub state: ProcessorState,
    pub instruction: Bits<32>,
    pub inputs: Bits<8>,
}
#[derive(Clone, Copy, LogicValue)]
struct Decode {
    mask: Bits<64>,
    dst_mask: Bits<64>,
    src_mask: Bits<64>,
    lhs: bool,
    rhs: bool,
    src: bool,
    branch_bit: bool,
}
#[derive(Clone, Copy, LogicValue)]
struct PinDecode {
    mask: Bits<8>,
    selected: Bits<8>,
}

#[logic]
#[allow(
    dead_code,
    reason = "Artifact export uses the IR; native evaluation remains available to tests."
)]
pub fn processor_step(input: StepInput) -> ProcessorState {
    let state = input.state;
    let instruction = input.instruction;
    let inputs = input.inputs;
    let opcode = instruction.slice::<4>(28);
    let payload = instruction.slice::<16>(0);
    let reserved = instruction.slice::<12>(16);
    let valid_set = opcode == bits::<4>(1) && reserved == bits::<12>(0);
    let valid_wait =
        opcode == bits::<4>(2) && reserved == bits::<12>(0) && payload != bits::<16>(0);
    let valid_halt = instruction == bits::<32>(0xf0000000);
    let valid_eval = opcode == bits::<4>(3) && instruction.slice::<6>(22) == bits::<6>(0);
    let valid_capture = instruction == bits::<32>(0x40000000);
    let valid_write = opcode == bits::<4>(5) && instruction.slice::<19>(9) == bits::<19>(0);
    let valid_jump = opcode == bits::<4>(6) && instruction.slice::<20>(8) == bits::<20>(0);
    let valid_branch = opcode == bits::<4>(7) && instruction.slice::<13>(15) == bits::<13>(0);
    let valid_count = opcode == bits::<4>(8) && reserved == bits::<12>(0);
    let valid_dec = opcode == bits::<4>(9) && instruction.slice::<20>(8) == bits::<20>(0);
    let valid_sample = opcode == bits::<4>(10) && instruction.slice::<19>(9) == bits::<19>(0);
    let valid_config = opcode == bits::<4>(11) && instruction.slice::<4>(24) == bits::<4>(0);
    let valid_sample_set = opcode == bits::<4>(12) && instruction.slice::<3>(25) == bits::<3>(0);
    let valid_parity =
        opcode == bits::<4>(13) && (instruction & bits::<32>(0x0fc0ffff)) == bits::<32>(0);
    let folded = state.scratch.slice::<32>(32);
    let folded = folded ^ (folded >> 16);
    let folded = folded ^ (folded >> 8);
    let folded = folded ^ (folded >> 4);
    let folded = folded ^ (folded >> 2);
    let folded = folded ^ (folded >> 1);
    let decoded = Decode {
        mask: bits::<64>(1),
        dst_mask: bits::<64>(0),
        src_mask: bits::<64>(0),
        lhs: false,
        rhs: false,
        src: false,
        branch_bit: false,
    }
    .fold::<64>(|acc, index| {
        let candidate = index.slice::<6>(0);
        Decode {
            dst_mask: if instruction.slice::<6>(16) == candidate {
                acc.mask
            } else {
                acc.dst_mask
            },
            lhs: if instruction.slice::<6>(10) == candidate {
                (state.scratch & acc.mask) != bits::<64>(0)
            } else {
                acc.lhs
            },
            rhs: if instruction.slice::<6>(4) == candidate {
                (state.scratch & acc.mask) != bits::<64>(0)
            } else {
                acc.rhs
            },
            src: if instruction.slice::<6>(3) == candidate {
                (state.scratch & acc.mask) != bits::<64>(0)
            } else {
                acc.src
            },
            src_mask: if instruction.slice::<6>(3) == candidate {
                acc.mask
            } else {
                acc.src_mask
            },
            branch_bit: if instruction.slice::<6>(8) == candidate {
                (state.scratch & acc.mask) != bits::<64>(0)
            } else {
                acc.branch_bit
            },
            mask: acc.mask << 1,
        }
    });
    let result = if decoded.lhs {
        if decoded.rhs {
            instruction.bit(3)
        } else {
            instruction.bit(2)
        }
    } else if decoded.rhs {
        instruction.bit(1)
    } else {
        instruction.bit(0)
    };
    let pin = PinDecode {
        mask: bits::<8>(1),
        selected: bits::<8>(0),
    }
    .fold::<8>(|acc, index| PinDecode {
        selected: if instruction.slice::<3>(0) == index.slice::<3>(0) {
            acc.mask
        } else {
            acc.selected
        },
        mask: acc.mask << 1,
    });
    let jumps = valid_jump
        || (valid_branch && decoded.branch_bit == instruction.bit(14))
        || (valid_dec && state.count > bits::<16>(1));
    let invalid = !(valid_set
        || valid_wait
        || valid_halt
        || valid_eval
        || valid_capture
        || valid_write
        || valid_jump
        || valid_branch
        || valid_count
        || valid_dec
        || valid_sample
        || valid_config
        || valid_sample_set
        || valid_parity)
        || (!valid_halt && !jumps && state.pc == bits::<8>(255));
    if state.halted {
        state
    } else if state.wait != bits::<16>(0) {
        ProcessorState {
            pc: state.pc,
            wait: state.wait - bits::<16>(1),
            pins: state.pins,
            halted: state.halted,
            fault: state.fault,
            scratch: state.scratch,
            count: state.count,
            enables: state.enables,
        }
    } else if invalid {
        ProcessorState {
            pc: state.pc,
            wait: state.wait,
            pins: state.pins,
            halted: true,
            fault: true,
            scratch: state.scratch,
            count: state.count,
            enables: state.enables,
        }
    } else if valid_halt {
        ProcessorState {
            pc: state.pc,
            wait: state.wait,
            pins: state.pins,
            halted: true,
            fault: state.fault,
            scratch: state.scratch,
            count: state.count,
            enables: state.enables,
        }
    } else {
        let pin_mask = instruction.slice::<8>(8);
        let config_mask = instruction.slice::<8>(16);
        let sampled_mask = instruction.slice::<8>(17);
        let scratch = if valid_capture {
            bits::<56>(0).concat::<8, 64>(inputs)
        } else if valid_eval {
            (state.scratch & !decoded.dst_mask)
                | if result {
                    decoded.dst_mask
                } else {
                    bits::<64>(0)
                }
        } else if valid_sample || valid_sample_set {
            (state.scratch & !decoded.src_mask)
                | if (inputs & pin.selected) != bits::<8>(0) {
                    decoded.src_mask
                } else {
                    bits::<64>(0)
                }
        } else if valid_parity {
            (state.scratch & !decoded.dst_mask)
                | if folded.bit(0) {
                    decoded.dst_mask
                } else {
                    bits::<64>(0)
                }
        } else {
            state.scratch
        };
        let pins = if valid_set {
            (state.pins & !pin_mask) | (instruction.slice::<8>(0) & pin_mask)
        } else if valid_write {
            (state.pins & !pin.selected)
                | if decoded.src {
                    pin.selected
                } else {
                    bits::<8>(0)
                }
        } else if valid_sample_set {
            (state.pins & !sampled_mask) | (instruction.slice::<8>(9) & sampled_mask)
        } else if valid_config {
            (state.pins & !config_mask) | (instruction.slice::<8>(0) & config_mask)
        } else {
            state.pins
        };
        ProcessorState {
            pc: if jumps {
                instruction.slice::<8>(0)
            } else {
                state.pc + bits::<8>(1)
            },
            wait: if valid_wait {
                payload - bits::<16>(1)
            } else {
                state.wait
            },
            pins,
            halted: state.halted,
            fault: state.fault,
            scratch,
            count: if valid_count {
                payload
            } else if valid_dec && state.count != bits::<16>(0) {
                state.count - bits::<16>(1)
            } else {
                state.count
            },
            enables: if valid_config {
                (state.enables & !config_mask) | (instruction.slice::<8>(8) & config_mask)
            } else {
                state.enables
            },
        }
    }
}

/// Preserve the established external HDL ABI; logical schemas retain state paths.
pub fn processor_ir() -> Result<bitlogic::Logic, bitlogic::Error> {
    processor_step::ir()?.rename_ports(
        &[
            "pc",
            "wait",
            "pins",
            "halted",
            "fault",
            "scratch",
            "count",
            "enables",
            "instruction",
            "inputs",
        ],
        &[
            "next_pc",
            "next_wait",
            "next_pins",
            "next_halted",
            "next_fault",
            "next_scratch",
            "next_count",
            "next_enables",
        ],
    )
}
