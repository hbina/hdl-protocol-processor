`timescale 1ns/1ps
module runtime_units_tb;
  reg clk = 0;
  always #5 clk = ~clk;
  reg clear = 1, valid = 0, host = 1, write = 0;
  reg [15:0] address = 0;
  reg [7:0] data_in = 0;
  wire [7:0] data_out;
  wire [3:0] error;
  runtime_store dut (.clk(clk), .clear(clear), .valid(valid), .host(host),
    .write(write), .address(address), .data_in(data_in), .data_out(data_out),
    .error(error), .debug_registers(32'h12345678));
  task access;
    input actor, wr;
    input [15:0] addr;
    input [7:0] value;
    input [3:0] expected_error;
    input [7:0] expected_data;
    begin
      @(negedge clk);
      host = actor; write = wr; address = addr; data_in = value; valid = 1;
      #1;
      if (error !== expected_error) $fatal(1, "address %h error %d expected %d", addr, error, expected_error);
      if (!wr && error == 0 && data_out !== expected_data)
        $fatal(1, "address %h data %h expected %h", addr, data_out, expected_data);
      @(negedge clk); valid = 0;
    end
  endtask
  integer i, round;
  initial begin
    @(negedge clk); clear = 0;
    access(1,1,16'h0000,42,0,0);
    access(1,1,16'h007f,43,0,0);
    access(0,1,16'h0000,99,4,0);
    access(0,1,16'h007f,99,4,0);
    access(1,0,16'h0000,0,0,42);
    access(1,0,16'h007f,0,0,43);
    access(0,1,16'h0080,99,0,0);
    access(1,1,16'h0080,100,4,0);
    access(0,0,16'h0080,0,0,99);
    access(1,0,16'h0080,0,4,0);
    // Multiple rounds exercise both FIFO pointer wrap and record ownership.
    for (round=0; round<3; round=round+1) begin
      for (i=0; i<64; i=i+1) access(1,1,16'h0110,i[7:0],0,0);
      access(1,1,16'h0110,255,6,0);
      for (i=0; i<15; i=i+1) access(1,1,16'h0120,i[7:0],0,0);
      access(1,1,16'h0121,0,7,0);
      access(0,0,16'h0122,0,5,0);
      access(1,1,16'h0120,15,0,0);
      access(1,1,16'h0121,0,0,0);
      access(1,1,16'h0000,99,8,0);
      access(1,0,16'h0000,0,0,42);
      access(1,1,16'h0100,1,8,0);
      access(1,0,16'h0102,0,0,64);
      for (i=0; i<16; i=i+1) access(0,0,16'h0122,0,0,i[7:0]);
      access(0,0,16'h0122,0,5,0);
      for (i=0; i<64; i=i+1) begin
        access(0,0,16'h0111,0,0,i[7:0]);
        access(0,1,16'h0130,i[7:0],0,0);
        access(0,1,16'h0132,0,7,0);
        access(0,1,16'h0131,8'ha5,0,0);
        access(0,1,16'h0132,0,0,0);
      end
      access(0,0,16'h0111,0,5,0);
      access(0,1,16'h0130,99,0,0);
      access(0,1,16'h0131,99,0,0);
      access(0,1,16'h0132,0,6,0);
      for (i=0; i<15; i=i+1) access(0,1,16'h0140,i[7:0],0,0);
      access(0,1,16'h0141,0,7,0);
      access(1,0,16'h0142,0,5,0);
      access(0,1,16'h0140,15,0,0);
      access(0,1,16'h0141,0,0,0);
      for (i=0; i<15; i=i+1) access(1,0,16'h0142,0,0,i[7:0]);
      access(1,0,16'h0142,0,8,0);
      for (i=0; i<64; i=i+1) begin
        access(1,0,16'h0133,0,0,i[7:0]);
        access(1,0,16'h0134,0,0,8'ha5);
        access(1,1,16'h0135,0,0,0);
      end
      access(1,0,16'h0142,0,0,15);
      access(1,0,16'h0101,0,0,0);
      // The failed full-FIFO push left staging populated. Retirement must
      // discard it even when the next request arrives without an idle flush.
      for (i=0; i<16; i=i+1) access(1,1,16'h0120,0,0,0);
      access(1,1,16'h0121,0,0,0);
      for (i=0; i<16; i=i+1) access(0,0,16'h0122,0,0,0);
      access(0,1,16'h0132,0,7,0);
      access(0,1,16'h0130,55,0,0);
      access(0,1,16'h0132,0,7,0);
      access(0,1,16'h0131,11,0,0);
      access(0,1,16'h0132,0,0,0);
      for (i=0; i<16; i=i+1) access(0,1,16'h0140,0,0,0);
      access(0,1,16'h0141,0,0,0);
      access(1,0,16'h0133,0,0,55);
      access(1,0,16'h0134,0,0,11);
      access(1,1,16'h0135,0,0,0);
      for (i=0; i<16; i=i+1) access(1,0,16'h0142,0,0,0);
      access(1,1,16'h0100,1,0,0);
    end
    $display("runtime storage boundaries passed");
    $finish;
  end
endmodule

module fifo_units_tb;
  parameter DEPTH = 4;
  localparam PTR = DEPTH > 1 ? $clog2(DEPTH) : 1;
  reg clk = 0;
  always #5 clk = ~clk;
  reg clear = 1, push = 0, pop = 0;
  reg [7:0] data_in = 0;
  wire [7:0] data_out;
  wire [PTR:0] count;
  runtime_fifo #(.DEPTH(DEPTH)) dut (.clk(clk), .clear(clear), .push(push),
    .pop(pop), .data_in(data_in), .data_out(data_out), .count(count));
  integer i;
  initial begin
    @(negedge clk); clear = 0;
    // At empty, a simultaneous operation accepts push and rejects pop.
    push = 1; pop = 1; data_in = 7;
    @(negedge clk);
    if (count != 1 || data_out != 7) $fatal;
    push = 0;
    @(negedge clk);
    if (count != 0) $fatal;
    pop = 0; push = 1;
    for (i=0; i<DEPTH; i=i+1) begin data_in = i[7:0]; @(negedge clk); end
    if (count != DEPTH) $fatal;
    // At full, pop succeeds but push is rejected using pre-edge capacity.
    pop = 1; data_in = 99;
    @(negedge clk); push = 0;
    if (count != DEPTH-1) $fatal;
    for (i=1; i<DEPTH; i=i+1) begin
      if (data_out != i[7:0]) $fatal;
      @(negedge clk);
    end
    pop = 0;
    if (count != 0) $fatal;
    if (DEPTH > 1) begin
      push=1; data_in=42;
      @(negedge clk); pop=1; data_in=43;
      @(negedge clk); push=0; pop=0;
      if (count != 1 || data_out != 43) $fatal;
    end
    $display("FIFO simultaneous access passed");
    $finish;
  end
endmodule
