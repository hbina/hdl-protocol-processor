/*
 * Copyright (c) 2026 Protocol Emulator contributors
 * SPDX-License-Identifier: Apache-2.0
 *
 * First-generation programmable protocol engine. Every instruction is one
 * 16-bit word. See docs/design.md for the programmer-visible architecture.
 */

`default_nettype none

module protocol_core (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       enable,
    input  wire       cfg_mode,
    input  wire       cfg_write,
    input  wire [5:0] cfg_data,
    input  wire [1:0] debug_select,
    input  wire [7:0] pin_in,
    output reg  [7:0] pin_out,
    output reg  [7:0] pin_oe,
    output wire [7:0] debug_data,
    output wire [31:0] debug_registers,
    output wire [7:0] loader_status,
    output wire       bus_valid,
    output reg        bus_write,
    output reg [15:0] bus_address,
    output reg [7:0]  bus_data,
    input wire [7:0]  bus_result,
    input wire [3:0]  bus_error,
    output reg        halted
);

  localparam [3:0] OP_NOP    = 4'h0;
  localparam [3:0] OP_LDI    = 4'h1;
  localparam [3:0] OP_IN     = 4'h2;
  localparam [3:0] OP_OUT    = 4'h3;
  localparam [3:0] OP_OE     = 4'h4;
  localparam [3:0] OP_SETO   = 4'h5;
  localparam [3:0] OP_SETOE  = 4'h6;
  localparam [3:0] OP_WAIT   = 4'h7;
  localparam [3:0] OP_JMP    = 4'h8;
  localparam [3:0] OP_JZ     = 4'h9;
  localparam [3:0] OP_DJNZ   = 4'hA;
  localparam [3:0] OP_REG    = 4'hB;
  localparam [3:0] OP_IMM    = 4'hC;
  localparam [3:0] OP_SHIFT  = 4'hD;
  localparam [3:0] OP_BIT    = 4'hE;
  localparam [3:0] OP_SYSTEM = 4'hF;

  reg [15:0] program_mem [0:127];
  reg [7:0] registers [0:3];
  reg [6:0] pc;
  reg [7:0] wait_count;
  reg memory_pending, condition_flag;
  reg [1:0] memory_destination;
  // Enable gates issue, not an already-issued transaction. Drain the fixed
  // commit cycle even if enable falls, avoiding duplicate queue side effects
  // and an external-enable path through the entire peripheral arbiter.
  // Configuration/reset clear the backend and cancel the pending access at
  // the clock edge; they need no combinational path through the arbiter.
  assign bus_valid = memory_pending && !halted;


  reg [7:0] pin_sync_meta;
  reg [7:0] pin_sync;

  reg        cfg_mode_d;
  reg        cfg_write_d;
  reg [6:0]  cfg_address;
  reg [1:0]  cfg_chunk;
  reg [11:0] cfg_partial;

  wire [15:0] instruction = program_mem[pc];
  wire [3:0] opcode = instruction[15:12];
  wire [3:0] operand_a = instruction[11:8];
  wire [7:0] immediate = instruction[7:0];
  wire [1:0] register_d = operand_a[1:0];
  wire [1:0] register_s = immediate[1:0];
  wire [1:0] operation = operand_a[3:2];
  wire [2:0] pin_index = immediate[2:0];

  assign debug_registers = {registers[3], registers[2], registers[1], registers[0]};
  assign debug_data = registers[debug_select];
  assign loader_status = {cfg_address[5:0], cfg_chunk};

  // External inputs pass through a two-flop synchronizer before firmware sees
  // them. This makes asynchronous protocols safe at the cost of two cycles of
  // input latency.
  always @(posedge clk) begin
    if (!rst_n) begin
      pin_sync_meta <= 8'h00;
      pin_sync      <= 8'h00;
    end else begin
      pin_sync_meta <= pin_in;
      pin_sync      <= pin_sync_meta;
    end
  end

  // Transfer each 16-bit program word as three six-bit chunks, least-
  // significant chunk first. The top two bits of the final chunk are ignored.
  always @(posedge clk) begin
    if (!rst_n) begin
      cfg_mode_d  <= 1'b0;
      cfg_write_d <= 1'b0;
      cfg_address <= 7'h00;
      cfg_chunk   <= 2'h0;
      cfg_partial <= 12'h000;
    end else begin
      cfg_mode_d  <= cfg_mode;
      cfg_write_d <= cfg_write;

      if (cfg_mode && !cfg_mode_d) begin
        cfg_write_d <= 1'b0;
        cfg_address <= 7'h00;
        cfg_chunk   <= 2'h0;
        cfg_partial <= 12'h000;
      end else if (cfg_mode && cfg_write && !cfg_write_d) begin
        case (cfg_chunk)
          2'd0: begin
            cfg_partial[5:0] <= cfg_data;
            cfg_chunk <= 2'd1;
          end
          2'd1: begin
            cfg_partial[11:6] <= cfg_data;
            cfg_chunk <= 2'd2;
          end
          default: begin
            program_mem[cfg_address] <= {cfg_data[3:0], cfg_partial};
            cfg_address <= cfg_address + 1'b1;
            cfg_chunk <= 2'd0;
          end
        endcase
      end
    end
  end

  // Fetch and execute one instruction per clock when not waiting. GPIO state
  // changes occur on rising edges and persist until explicitly changed.
  always @(posedge clk) begin
    if (!rst_n) begin
      pc           <= 7'h00;
      wait_count   <= 8'h00;
      registers[0] <= 8'h00;
      registers[1] <= 8'h00;
      registers[2] <= 8'h00;
      registers[3] <= 8'h00;
      pin_out      <= 8'h00;
      pin_oe       <= 8'h00;
      halted       <= 1'b0;
      memory_pending <= 0; condition_flag <= 0;
      memory_destination <= 0; bus_write <= 0; bus_address <= 0; bus_data <= 0;
    end else if (cfg_mode) begin
      pc           <= 7'h00;
      wait_count   <= 8'h00;
      registers[0] <= 8'h00;
      registers[1] <= 8'h00;
      registers[2] <= 8'h00;
      registers[3] <= 8'h00;
      pin_out      <= 8'h00;
      pin_oe       <= 8'h00;
      halted       <= 1'b0;
      memory_pending <= 0; condition_flag <= 0;
      memory_destination <= 0; bus_write <= 0; bus_address <= 0; bus_data <= 0;
    end else if (memory_pending) begin
      condition_flag <= bus_error == 0;
      if (!bus_write && bus_error == 0) registers[memory_destination] <= bus_result;
      memory_pending <= 0;
      pc <= pc + 1'b1;
    end else if (enable && !halted) begin
      if (wait_count != 8'h00) begin
        wait_count <= wait_count - 1'b1;
      end else begin
        case (opcode)
          OP_NOP: begin
            pc <= pc + 1'b1;
          end
          OP_LDI: begin
            if (operation == 1) condition_flag <= registers[register_d] == immediate;
            else if (operation == 2) condition_flag <= registers[register_d] < registers[register_s];
            else if (operation == 3) condition_flag <= registers[register_d] < immediate;
            else registers[register_d] <= immediate;
            pc <= pc + 1'b1;
          end
          OP_IN: begin
            if (operation == 0) begin
              registers[register_d] <= pin_sync;
              pc <= pc + 1'b1;
            end else if ((operation == 1 || operation == 2) && immediate[7:2] == 0) begin
              memory_pending <= 1; memory_destination <= register_d; bus_write <= 0;
              bus_address <= {operation == 2 ? 8'h01 : 8'h00, registers[register_s]};
            end else halted <= 1;
          end
          OP_OUT: begin
            if (operation == 0) begin
              pin_out <= registers[register_d];
              pc <= pc + 1'b1;
            end else if ((operation == 1 || operation == 2) && immediate[7:2] == 0) begin
              memory_pending <= 1; bus_write <= 1; bus_data <= registers[register_d];
              bus_address <= {operation == 2 ? 8'h01 : 8'h00, registers[register_s]};
            end else halted <= 1;
          end
          OP_OE: begin
            pin_oe <= registers[register_d];
            pc <= pc + 1'b1;
          end
          OP_SETO: begin
            pin_out <= immediate;
            pc <= pc + 1'b1;
          end
          OP_SETOE: begin
            pin_oe <= immediate;
            pc <= pc + 1'b1;
          end
          OP_WAIT: begin
            wait_count <= immediate;
            pc <= pc + 1'b1;
          end
          OP_JMP: begin
            if (!operand_a[3] || !condition_flag)
              pc <= operand_a[2] ? immediate[6:0] : {1'b0, immediate[5:0]};
            else pc <= pc + 1'b1;
          end
          OP_JZ: begin
            if (registers[register_d] == 8'h00)
              pc <= operand_a[2] ? immediate[6:0] : {1'b0, immediate[5:0]};
            else
              pc <= pc + 1'b1;
          end
          OP_DJNZ: begin
            registers[register_d] <= registers[register_d] - 1'b1;
            if (registers[register_d] != 8'h01)
              pc <= operand_a[2] ? immediate[6:0] : {1'b0, immediate[5:0]};
            else
              pc <= pc + 1'b1;
          end
          OP_REG: begin
            case (operation)
              2'd0: registers[register_d] <= registers[register_s];
              2'd1: registers[register_d] <= registers[register_d] ^ registers[register_s];
              2'd2: registers[register_d] <= registers[register_d] | registers[register_s];
              2'd3: registers[register_d] <= registers[register_d] & registers[register_s];
            endcase
            pc <= pc + 1'b1;
          end
          OP_IMM: begin
            case (operation)
              2'd0: registers[register_d] <= registers[register_d] + immediate;
              2'd1: registers[register_d] <= registers[register_d] & immediate;
              2'd2: registers[register_d] <= registers[register_d] | immediate;
              2'd3: registers[register_d] <= registers[register_d] ^ immediate;
            endcase
            pc <= pc + 1'b1;
          end
          OP_SHIFT: begin
            case (operation)
              2'd0: registers[register_d] <= registers[register_d] << 1;
              2'd1: registers[register_d] <= registers[register_d] >> 1;
              2'd2: registers[register_d] <= {registers[register_d][6:0], registers[register_d][7]};
              2'd3: registers[register_d] <= {registers[register_d][0], registers[register_d][7:1]};
            endcase
            pc <= pc + 1'b1;
          end
          OP_BIT: begin
            case (operation)
              2'd0: pin_out[pin_index] <= registers[register_d][0];
              2'd1: registers[register_d][0] <= pin_sync[pin_index];
              2'd2: pin_oe[pin_index] <= registers[register_d][0];
              2'd3: pin_oe[pin_index] <= ~registers[register_d][0];
            endcase
            pc <= pc + 1'b1;
          end
          OP_SYSTEM: begin
            if (operation == 2'd1) begin
              if (pin_sync[pin_index] == operand_a[0])
                pc <= pc + 1'b1;
            end else begin
              halted <= 1'b1;
            end
          end
          default: begin
            halted <= 1'b1;
          end
        endcase
      end
    end
  end

endmodule

`default_nettype wire
