/* SPDX-License-Identifier: Apache-2.0 */
`default_nettype none
module tt_um_protocol_emulator (
    input wire [7:0] ui_in,
    output wire [7:0] uo_out,
    input wire [7:0] uio_in,
    output wire [7:0] uio_out,
    output wire [7:0] uio_oe,
    input wire ena, clk, rst_n
);
  wire [15:0] outputs, enables;
  wire [7:0] loader_status;
  wire halted;
  protocol_core #(.INPUT_PINS(15), .OUTPUT_PINS(16)) core (
      .clk(clk), .rst_n(rst_n), .enable(ena),
      .cfg_mode(ui_in[7]), .cfg_write(ui_in[6]), .cfg_data(ui_in[5:0]),
      .pin_in({ui_in[6:0], uio_in}), .pin_out(outputs), .pin_oe(enables),
      .loader_status(loader_status), .halted(halted)
  );
  assign uio_out = outputs[7:0];
  assign uio_oe = enables[7:0];
  assign uo_out = ui_in[7] ? loader_status : outputs[15:8];
  wire _unused = &{enables[15:8], halted, 1'b0};
endmodule
`default_nettype wire
