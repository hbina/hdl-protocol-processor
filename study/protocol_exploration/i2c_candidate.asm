# I2C TX/RX capacity experiment; does NOT fit the current 128-word ASIC.
# uio4=SCL, uio5=SDA. Always drive zero or release. 50 MHz core.
# Valid request: parameter[0]=7-bit address, parameter[1]=0..64 read count.
# Input FIFO contains 1..64 bytes (register pointer followed by write bytes).
# Write address + input; if requested, repeated START + read address + RX.
# Scratch: event 144..159, tx_left160, rx_left161, recovery flag162, bit count163.
# Status: 0 success, 8 NACK, 9 clock/bus timeout. No multi-controller support.
    SETO 0
    SETOE 0
    LDI r1, 162
    LDI r0, 0
    STORE r0, r1
idle:
    LDI r3, 0x22
    PREAD r0, r3
    JFAIL idle
    LDI r1, 144
    STORE r0, r1
    PREAD r0, r3
    ADDI r1, 1
    STORE r0, r1
    LDI r2, 14
record:
    PREAD r0, r3
    DJNZ r2, record
    LDI r1, 146
    LDI r0, 1
    STORE r0, r1
    ADDI r1, 1
    LDI r2, 13
    LDI r0, 0
clear_event:
    STORE r0, r1
    ADDI r1, 1
    DJNZ r2, clear_event
    LDI r3, 2
    PREAD r0, r3
    LDI r1, 148
    STORE r0, r1
    LDI r1, 160
    STORE r0, r1
    LDI r1, 1
    LOAD r0, r1
    LDI r1, 161
    STORE r0, r1
    LDI r2, 0
bus_idle:
    IN r1
    ANDI r1, 0x30
    CMPI r1, 0x30
    JFAIL bus_busy
    WAIT 249
    SETOE 0x20
    WAIT 249
    SETOE 0x30
    LDI r1, 0
    LOAD r0, r1
    SHL r0
    LDI r3, 0
tx_byte:
    LDI r2, 8
tx_bit:
    ROL r0
    OEBITN r0, 5
    WAIT 249
    LDI r1, 163
    STORE r2, r1
    LDI r1, 0
    OEBIT r1, 4
    LDI r2, 0
tx_clock:
    IN r1
    ANDI r1, 0x10
    JZ r1, tx_stretch
    LDI r1, 163
    LOAD r2, r1
    WAIT 249
    LDI r1, 1
    OEBIT r1, 4
    DJNZ r2, tx_bit
    SETOE 0x10
    WAIT 249
    LDI r1, 0
    OEBIT r1, 4
    LDI r2, 0
ack_clock:
    IN r1
    ANDI r1, 0x10
    JZ r1, ack_stretch
    WAIT 249
    LDI r1, 0
    INBIT r1, 5
    LDI r2, 1
    OEBIT r2, 4
    JZ r1, acked
    LDI r2, 8
    JMP nack
tx_stretch:
    DJNZ r2, tx_clock
    JMP timeout
ack_stretch:
    DJNZ r2, ack_clock
    JMP timeout
acked:
    CMPI r3, 2
    JFAIL write_more
    JMP read_byte
write_more:
    LDI r1, 160
    LOAD r0, r1
    JZ r0, write_done
    ADDI r0, 255
    STORE r0, r1
    LDI r1, 0x11
    PREAD r0, r1
    LDI r3, 1
    JMP tx_byte
write_done:
    LDI r1, 161
    LOAD r0, r1
    JZ r0, stop
    SETOE 0x10
    WAIT 249
    LDI r1, 0
    OEBIT r1, 4
    LDI r2, 0
restart_clock:
    IN r1
    ANDI r1, 0x10
    JZ r1, restart_stretch
    WAIT 249
    SETOE 0x20
    WAIT 249
    SETOE 0x30
    LDI r1, 0
    LOAD r0, r1
    SHL r0
    ORI r0, 1
    LDI r3, 2
    JMP tx_byte
restart_stretch:
    DJNZ r2, restart_clock
    JMP timeout
read_byte:
    SETOE 0x10
    LDI r0, 0
    LDI r2, 8
rx_bit:
    WAIT 249
    LDI r1, 163
    STORE r2, r1
    LDI r1, 0
    OEBIT r1, 4
    LDI r2, 0
rx_clock:
    IN r1
    ANDI r1, 0x10
    JZ r1, rx_stretch
    WAIT 249
    SHL r0
    INBIT r0, 5
    LDI r1, 1
    OEBIT r1, 4
    LDI r1, 163
    LOAD r2, r1
    DJNZ r2, rx_bit
    LDI r1, 0x30
    PWRITE r0, r1
    LDI r0, 0
    ADDI r1, 1
    PWRITE r0, r1
    ADDI r1, 1
    PWRITE r0, r1
    LDI r1, 150
    LOAD r0, r1
    ADDI r0, 1
    STORE r0, r1
    LDI r1, 161
    LOAD r0, r1
    ADDI r0, 255
    STORE r0, r1
    JZ r0, final_nack
    SETOE 0x30
    JMP rx_ack
final_nack:
    SETOE 0x10
rx_ack:
    WAIT 249
    LDI r1, 0
    OEBIT r1, 4
    LDI r2, 0
rx_ack_clock:
    IN r1
    ANDI r1, 0x10
    JZ r1, rx_ack_stretch
    WAIT 249
    LDI r1, 1
    OEBIT r1, 4
    LDI r1, 161
    LOAD r0, r1
    JZ r0, stop
    JMP read_byte
rx_stretch:
    DJNZ r2, rx_clock
    JMP timeout
rx_ack_stretch:
    DJNZ r2, rx_ack_clock
    JMP timeout
stop:
    SETOE 0x30
    WAIT 249
    LDI r1, 0
    OEBIT r1, 4
    LDI r2, 0
stop_clock:
    IN r1
    ANDI r1, 0x10
    JZ r1, stop_stretch
    WAIT 249
    SETOE 0
    WAIT 249
    LDI r1, 162
    LDI r0, 0
    STORE r0, r1
    JMP publish
stop_stretch:
    DJNZ r2, stop_clock
    CMPI r3, 3
    JFAIL timeout
    JMP recovery_failed
nack:
    LDI r1, 147
    STORE r2, r1
    LDI r3, 0x11
discard_stop:
    PREAD r0, r3
    JFAIL stop
    JMP discard_stop
bus_busy:
    DJNZ r2, bus_idle
    CMPI r1, 0x10
    JFAIL timeout_status
    LDI r1, 162
    LOAD r2, r1
    JMP timeout_status
timeout:
    LDI r2, 1
timeout_status:
    LDI r1, 147
    LDI r0, 9
    STORE r0, r1
    SETOE 0
    LDI r3, 0x11
discard_release:
    PREAD r0, r3
    JFAIL drained
    JMP discard_release
drained:
    JZ r2, publish
    # A failed in-flight byte can leave a target holding SDA. Allow bounded
    # SCL recovery, then issue nine bus-clear clocks and STOP before retiring.
    LDI r2, 0
recovery_clock:
    IN r0
    ANDI r0, 0x10
    JZ r0, recovery_wait
    WAIT 249
    LDI r2, 9
clear_pulse:
    SETOE 0x10
    WAIT 249
    SETOE 0
    WAIT 249
    DJNZ r2, clear_pulse
    LDI r3, 3
    JMP stop
recovery_wait:
    WAIT 255
    DJNZ r2, recovery_clock
recovery_failed:
    LDI r1, 162
    LDI r0, 1
    STORE r0, r1
release_done:
    SETOE 0
publish:
    LDI r1, 144
    LDI r2, 16
    LDI r3, 0x40
event:
    LOAD r0, r1
    PWRITE r0, r3
    ADDI r1, 1
    DJNZ r2, event
    LDI r0, 0
    ADDI r3, 1
    PWRITE r0, r3
    JMP idle
