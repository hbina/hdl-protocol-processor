# SWD host, DP only, one-cycle turnaround, overrun data phase disabled.
# uio0=SWCLK, uio1=SWDIO. Generic instructions; no protocol-aware RTL.
# parameter[0]=RnW (1 read, 0 write), parameter[1]=DP address index0..3.
# Valid envelope: read has no input and output_limit4; write has four input bytes.
# Scratch event144..159, attempts160, parity161, data pointer162, bytes164..167.
# Status0 OK,10 WAIT exhausted,11 FAULT/invalid ACK,12 read parity error.
    SETO 2
    SETOE 3
    LDI r2, 56
line_reset:
    WAIT 249
    SETO 3
    WAIT 249
    SETO 2
    DJNZ r2, line_reset
    SETO 0
    LDI r2, 8
boot_idle:
    WAIT 249
    SETO 1
    WAIT 249
    SETO 0
    DJNZ r2, boot_idle
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
    LDI r0, 3
    STORE r0, r1
retry:
    LDI r1, 1
    LOAD r0, r1
    MOV r2, r0
    SHR r2
    XOR r2, r0
    ANDI r2, 1
    LDI r1, 0
    LOAD r1, r1
    XOR r2, r1
    SHL r2
    SHL r2
    SHL r2
    SHL r2
    SHL r2
    SHL r0
    SHL r0
    SHL r0
    SHL r1
    SHL r1
    OR r0, r1
    OR r0, r2
    ORI r0, 0x81
    SETOE 3
    LDI r2, 8
request_bit:
    OUTBIT r0, 1
    SHR r0
    WAIT 249
    LDI r3, 1
    OUTBIT r3, 0
    WAIT 249
    LDI r3, 0
    OUTBIT r3, 0
    DJNZ r2, request_bit
    SETOE 1
    WAIT 249
    SETO 1
    WAIT 249
    SETO 0
    LDI r0, 0
    LDI r2, 3
ack_bit:
    WAIT 249
    SETO 1
    WAIT 249
    INBIT r0, 1
    ROR r0
    SETO 0
    DJNZ r2, ack_bit
    CMPI r0, 32
    JFAIL not_ok
    LDI r1, 0
    LOAD r0, r1
    JZ r0, write_turn
    JMP data_begin
write_turn:
    WAIT 249
    SETO 1
    WAIT 249
    SETO 0
    SETOE 3
data_begin:
    LDI r1, 161
    LDI r0, 0
    STORE r0, r1
    LDI r1, 162
    LDI r0, 164
    STORE r0, r1
data_byte:
    LDI r1, 0
    LOAD r3, r1
    JZ r3, write_byte
    LDI r0, 0
    JMP shift_byte
write_byte:
    LDI r3, 0x11
    PREAD r0, r3
shift_byte:
    LDI r2, 8
data_bit:
    OUTBIT r0, 1
    WAIT 249
    LDI r3, 1
    OUTBIT r3, 0
    WAIT 249
    INBIT r0, 1
    MOV r1, r0
    ANDI r1, 1
    LDI r3, 161
    LOAD r3, r3
    XOR r3, r1
    LDI r1, 161
    STORE r3, r1
    ROR r0
    LDI r3, 0
    OUTBIT r3, 0
    DJNZ r2, data_bit
    LDI r1, 162
    LOAD r1, r1
    STORE r0, r1
    ADDI r1, 1
    MOV r0, r1
    LDI r1, 162
    STORE r0, r1
    CMPI r0, 168
    JFAIL data_byte
    LDI r1, 0
    LOAD r0, r1
    JZ r0, write_parity
    WAIT 249
    SETO 1
    WAIT 249
    LDI r0, 0
    INBIT r0, 1
    SETO 0
    LDI r1, 161
    LOAD r1, r1
    XOR r0, r1
    WAIT 249
    SETO 1
    WAIT 249
    SETO 0
    SETOE 3
    JZ r0, success
    LDI r2, 12
    JMP failure
write_parity:
    LDI r1, 161
    LOAD r0, r1
    OUTBIT r0, 1
    WAIT 249
    LDI r3, 1
    OUTBIT r3, 0
    WAIT 249
    LDI r3, 0
    OUTBIT r3, 0
success:
    LDI r1, 0
    LOAD r0, r1
    JZ r0, finish
    LDI r1, 164
    LDI r2, 4
    LDI r3, 0x30
output:
    LOAD r0, r1
    PWRITE r0, r3
    LDI r0, 0
    ADDI r3, 1
    PWRITE r0, r3
    ADDI r3, 1
    PWRITE r0, r3
    ADDI r3, 254
    ADDI r1, 1
    DJNZ r2, output
    LDI r1, 150
    LDI r0, 4
    STORE r0, r1
    JMP finish
not_ok:
    WAIT 249
    SETO 1
    WAIT 249
    SETO 0
    SETOE 3
    SETO 2
    CMPI r0, 64
    JFAIL fault
    LDI r1, 160
    LOAD r2, r1
    ADDI r2, 255
    STORE r2, r1
    JZ r2, wait_failed
    JMP retry
wait_failed:
    LDI r2, 10
    JMP failure
fault:
    LDI r2, 11
failure:
    LDI r1, 147
    STORE r2, r1
    LDI r3, 0x11
discard:
    PREAD r0, r3
    JFAIL finish
    JMP discard
finish:
    SETO 0
    LDI r2, 8
idle_clock:
    WAIT 249
    SETO 1
    WAIT 249
    SETO 0
    DJNZ r2, idle_clock
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
