/*
 * Copyright (c) 2026 Protocol Emulator contributors
 * SPDX-License-Identifier: Apache-2.0
 */

`default_nettype none

module tt_um_protocol_emulator (
    input  wire [7:0] ui_in,
    output wire [7:0] uo_out,
    input  wire [7:0] uio_in,
    output wire [7:0] uio_out,
    output wire [7:0] uio_oe,
    input  wire       ena,
    input  wire       clk,
    input  wire       rst_n
);

  wire [7:0] debug_data;
  wire [7:0] loader_status;
  wire       halted;

  protocol_core core (
      .clk          (clk),
      .rst_n        (rst_n),
      .enable       (ena),
      .cfg_mode     (ui_in[7]),
      .cfg_write    (ui_in[6]),
      .cfg_data     (ui_in[5:0]),
      .debug_select (ui_in[1:0]),
      .pin_in       (uio_in),
      .pin_out      (uio_out),
      .pin_oe       (uio_oe),
      .debug_data   (debug_data),
      .loader_status(loader_status),
      .halted       (halted)
  );

  // During configuration this reports {word address, chunk number}. During
  // execution ui_in[1:0] selects one of the four register values to inspect.
  assign uo_out = ui_in[7] ? loader_status : debug_data;

  // Halt remains visible in simulation and can be assigned to a pin later.
  wire _unused = &{halted, ui_in[5:2], 1'b0};

endmodule

`default_nettype wire
