use super::*;

fn check(
    bytes: &[u8],
    period: usize,
    start: usize,
    bad_stop: Option<usize>,
    ir: &bitlogic::Logic,
    hdl: &mut ClockedVectors,
) {
    let words = uart::receive_frames(Pin::new(7).unwrap(), period as u32, 16, bytes.len() as u8)
        .unwrap()
        .words();
    let mut state = State::default();
    hdl.load(&words);
    hdl.edge(true, 0, state);
    for edge in 0..(12 * period * bytes.len() + 100) {
        let high = if edge < start {
            true
        } else {
            let position = (edge - start) / period;
            let frame = position / 10;
            if frame >= bytes.len() {
                true
            } else {
                match position % 10 {
                    0 => false,
                    9 => Some(frame) != bad_stop,
                    bit => bytes[frame] & (1 << (bit - 1)) != 0,
                }
            }
        };
        let inputs = if high { 128 } else { 0 };
        let word = words[usize::from(state.pc)];
        let next = state.tick(word, inputs, false);
        assert_eq!(native_step(state, word, inputs, false), next);
        assert_eq!(ir_step(ir, state, word, inputs, false), next);
        hdl.edge(false, inputs, next);
        state = next;
        if state.halted {
            break;
        }
    }
    assert!(state.halted && !state.fault);
    assert_eq!(state.scratch >> 60, if bad_stop.is_some() { 8 } else { 4 });
    let received = bad_stop.map(|frame| frame + 1).unwrap_or(bytes.len());
    for (frame, &byte) in bytes[..received].iter().enumerate() {
        assert_eq!(
            (state.scratch >> (8 + frame * 8)) & 255,
            u64::from(byte),
            "frame {frame}"
        );
    }
}

#[test]
fn uart_receive_complete_back_to_back_batches() {
    let ir = processor_step::ir().unwrap();
    let mut hdl = ClockedVectors::new();
    let mut cases = 0;
    for byte in 0..=255_u8 {
        for phase in 0..3 {
            check(
                &[byte, byte.reverse_bits() ^ 0x69],
                8,
                10 + phase,
                None,
                &ir,
                &mut hdl,
            );
            cases += 1;
        }
    }
    for period in [8, 16, 32] {
        for phase in 0..3 {
            check(
                &[0, 255, 0x55, 0xaa, 0x96, 0xa5],
                period,
                10 + phase,
                None,
                &ir,
                &mut hdl,
            );
            cases += 1;
        }
    }
    for phase in 0..3 {
        check(&[0xa5, 0x69, 0x96], 8, 10 + phase, Some(1), &ir, &mut hdl);
        cases += 1;
    }
    println!("{cases} complete adjacent-frame UART batch scenarios");
    hdl.finish();
    for count in [0, 7, 255] {
        assert!(uart::receive_frames(Pin::new(0).unwrap(), 8, 16, count).is_err());
    }
}
