use bitlogic::{Bits, bits, logic};

#[logic]
#[allow(clippy::too_many_arguments)]
pub fn processor_step(
    pc: &Bits<8>,
    wait: &Bits<16>,
    pins: &Bits<8>,
    halted: &bool,
    fault: &bool,
    scratch: &Bits<64>,
    count: &Bits<16>,
    enables: &Bits<8>,
    instruction: &Bits<32>,
    inputs: &Bits<8>,
    next_pc: &mut Bits<8>,
    next_wait: &mut Bits<16>,
    next_pins: &mut Bits<8>,
    next_halted: &mut bool,
    next_fault: &mut bool,
    next_scratch: &mut Bits<64>,
    next_count: &mut Bits<16>,
    next_enables: &mut Bits<8>,
) {
    *next_pc = *pc;
    *next_wait = *wait;
    *next_pins = *pins;
    *next_halted = *halted;
    *next_fault = *fault;
    *next_scratch = *scratch;
    *next_count = *count;
    *next_enables = *enables;
    let opcode = instruction.slice::<4>(28);
    let payload = instruction.slice::<16>(0);
    let reserved = instruction.slice::<12>(16);
    let valid_set = opcode == bits::<4>(1) && reserved == bits::<12>(0);
    let valid_wait =
        opcode == bits::<4>(2) && reserved == bits::<12>(0) && payload != bits::<16>(0);
    let valid_halt = *instruction == bits::<32>(0xf0000000);
    let valid_eval = opcode == bits::<4>(3) && instruction.slice::<6>(22) == bits::<6>(0);
    let valid_capture = *instruction == bits::<32>(0x40000000);
    let valid_write = opcode == bits::<4>(5) && instruction.slice::<19>(9) == bits::<19>(0);
    let valid_jump = opcode == bits::<4>(6) && instruction.slice::<20>(8) == bits::<20>(0);
    let valid_branch = opcode == bits::<4>(7) && instruction.slice::<13>(15) == bits::<13>(0);
    let valid_count = opcode == bits::<4>(8) && reserved == bits::<12>(0);
    let valid_dec = opcode == bits::<4>(9) && instruction.slice::<20>(8) == bits::<20>(0);
    let valid_sample = opcode == bits::<4>(10) && instruction.slice::<19>(9) == bits::<19>(0);
    let valid_config = opcode == bits::<4>(11) && instruction.slice::<4>(24) == bits::<4>(0);
    let valid_sample_set = opcode == bits::<4>(12) && instruction.slice::<3>(25) == bits::<3>(0);
    let valid_parity =
        opcode == bits::<4>(13) && (*instruction & bits::<32>(0x0fc0ffff)) == bits::<32>(0);
    let mut folded = scratch.slice::<32>(32);
    folded = folded ^ (folded >> 16);
    folded = folded ^ (folded >> 8);
    folded = folded ^ (folded >> 4);
    folded = folded ^ (folded >> 2);
    folded = folded ^ (folded >> 1);
    // Bounded decoder expansion implements dynamic selection using only existing
    // DSL operations. Operands are selected from the original scratch bank.
    let mut candidate = bits::<6>(0);
    let mut mask = bits::<64>(1);
    let mut dst_mask = bits::<64>(0);
    let mut src_mask = bits::<64>(0);
    let mut lhs = false;
    let mut rhs = false;
    let mut src = false;
    let mut branch_bit = false;
    for _ in 0..64 {
        if instruction.slice::<6>(16) == candidate {
            dst_mask = mask;
        }
        if instruction.slice::<6>(10) == candidate {
            lhs = (*scratch & mask) != bits::<64>(0);
        }
        if instruction.slice::<6>(4) == candidate {
            rhs = (*scratch & mask) != bits::<64>(0);
        }
        if instruction.slice::<6>(3) == candidate {
            src = (*scratch & mask) != bits::<64>(0);
            src_mask = mask;
        }
        if instruction.slice::<6>(8) == candidate {
            branch_bit = (*scratch & mask) != bits::<64>(0);
        }
        candidate = candidate + bits::<6>(1);
        mask = mask << 1;
    }
    let mut result = instruction.bit(0);
    if lhs {
        if rhs {
            result = instruction.bit(3);
        } else {
            result = instruction.bit(2);
        }
    } else if rhs {
        result = instruction.bit(1);
    }
    let mut pin_candidate = bits::<3>(0);
    let mut pin_mask = bits::<8>(1);
    let mut selected_pin = bits::<8>(0);
    for _ in 0..8 {
        if instruction.slice::<3>(0) == pin_candidate {
            selected_pin = pin_mask;
        }
        pin_candidate = pin_candidate + bits::<3>(1);
        pin_mask = pin_mask << 1;
    }
    let jumps = valid_jump
        || (valid_branch && branch_bit == instruction.bit(14))
        || (valid_dec && *count > bits::<16>(1));
    if !*halted {
        if *wait != bits::<16>(0) {
            *next_wait = *wait - bits::<16>(1);
        } else if !(valid_set
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
            || (!valid_halt && !jumps && *pc == bits::<8>(255))
        {
            *next_halted = true;
            *next_fault = true;
        } else if valid_halt {
            *next_halted = true;
        } else {
            *next_pc = *pc + bits::<8>(1);
            if jumps {
                *next_pc = instruction.slice::<8>(0);
            }
            if valid_set {
                let output_mask = instruction.slice::<8>(8);
                *next_pins = (*pins & !output_mask) | (instruction.slice::<8>(0) & output_mask);
            } else if valid_wait {
                *next_wait = payload - bits::<16>(1);
            } else if valid_capture {
                *next_scratch = bits::<56>(0).concat::<8, 64>(*inputs);
            } else if valid_eval {
                *next_scratch = *scratch & !dst_mask;
                if result {
                    *next_scratch = *next_scratch | dst_mask;
                }
            } else if valid_write {
                *next_pins = *pins & !selected_pin;
                if src {
                    *next_pins = *next_pins | selected_pin;
                }
            } else if valid_count {
                *next_count = payload;
            } else if valid_dec && *count != bits::<16>(0) {
                *next_count = *count - bits::<16>(1);
            } else if valid_sample || valid_sample_set {
                *next_scratch = *scratch & !src_mask;
                if (*inputs & selected_pin) != bits::<8>(0) {
                    *next_scratch = *next_scratch | src_mask;
                }
                if valid_sample_set {
                    let sampled_mask = instruction.slice::<8>(17);
                    *next_pins =
                        (*pins & !sampled_mask) | (instruction.slice::<8>(9) & sampled_mask);
                }
            } else if valid_config {
                let config_mask = instruction.slice::<8>(16);
                *next_pins = (*pins & !config_mask) | (instruction.slice::<8>(0) & config_mask);
                *next_enables =
                    (*enables & !config_mask) | (instruction.slice::<8>(8) & config_mask);
            } else if valid_parity {
                *next_scratch = *scratch & !dst_mask;
                if folded.bit(0) {
                    *next_scratch = *next_scratch | dst_mask;
                }
            }
        }
    }
}
