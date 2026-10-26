`timescale 1ns/1ps
module pin_core_tb #(
    parameter INPUT_PINS=15, OUTPUT_PINS=16
);
  reg clk=0, rst_n=0, enable=1, cfg_mode=1, cfg_write=0;
  reg [5:0] cfg_data=0;
  reg [INPUT_PINS-1:0] pin_in=0;
  wire [OUTPUT_PINS-1:0] pin_out, pin_oe;
  wire [7:0] loader_status;
  wire halted;
  protocol_core #(.INPUT_PINS(INPUT_PINS), .OUTPUT_PINS(OUTPUT_PINS)) core (
    .clk(clk),.rst_n(rst_n),.enable(enable),.cfg_mode(cfg_mode),
    .cfg_write(cfg_write),.cfg_data(cfg_data),.pin_in(pin_in),
    .pin_out(pin_out),.pin_oe(pin_oe),.loader_status(loader_status),.halted(halted)
  );
endmodule
