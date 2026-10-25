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
  wire [31:0] debug_registers;
  wire [7:0] loader_status;
  wire       halted;
  wire cpu_valid, cpu_write, host_valid, host_write;
  wire [15:0] cpu_address, host_address;
  wire [7:0] cpu_data, host_data, bus_result, runtime_response;
  wire [3:0] bus_error;
  wire host_ready = !cpu_valid;
  runtime_bridge bridge (.clk(clk), .clear(!rst_n || ui_in[7]),
      .request(ui_in[6]), .token(ui_in[5:0]), .response(runtime_response),
      .valid(host_valid), .write(host_write), .address(host_address),
      .data_in(host_data), .ready(host_ready), .data_out(bus_result), .error(bus_error));
  runtime_store store (.clk(clk), .clear(!rst_n || ui_in[7]),
      .valid(cpu_valid || host_valid), .host(!cpu_valid), .debug_registers(debug_registers),
      .write(cpu_valid ? cpu_write : host_write),
      .address(cpu_valid ? cpu_address : host_address),
      .data_in(cpu_valid ? cpu_data : host_data), .data_out(bus_result), .error(bus_error));

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
      .debug_registers(debug_registers),
      .loader_status(loader_status),
      .bus_valid    (cpu_valid),
      .bus_write    (cpu_write),
      .bus_address  (cpu_address),
      .bus_data     (cpu_data),
      .bus_result   (bus_result),
      .bus_error    (bus_error),
      .halted       (halted)
  );

  // Configuration keeps the legacy status; execution reports runtime tokens.
  assign uo_out = ui_in[7] ? loader_status : runtime_response;

  // Halt remains visible in simulation and can be assigned to a pin later.
  wire _unused = &{halted, debug_data, 1'b0};

endmodule

`default_nettype wire
