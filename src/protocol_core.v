/* SPDX-License-Identifier: Apache-2.0 */
`default_nettype none

// Autonomous GPIO processor. See docs/pin_processor.md for the ISA contract.
module protocol_core #(
    parameter INPUT_PINS = 15,
    parameter OUTPUT_PINS = 16
)(
    input wire clk, rst_n, enable,
    input wire cfg_mode, cfg_write,
    input wire [5:0] cfg_data,
    input wire [INPUT_PINS-1:0] pin_in,
    output reg [OUTPUT_PINS-1:0] pin_out, pin_oe,
    output wire [7:0] loader_status,
    output reg halted
);
  initial begin
    if (INPUT_PINS < 1 || INPUT_PINS > 256 || OUTPUT_PINS < 1 || OUTPUT_PINS > 256)
      $fatal(1, "pin counts must be 1..256");
  end

  localparam INPUT_INDEX_BITS = INPUT_PINS > 1 ? $clog2(INPUT_PINS) : 1;
  localparam OUTPUT_INDEX_BITS = OUTPUT_PINS > 1 ? $clog2(OUTPUT_PINS) : 1;

  reg [15:0] program_mem [0:255];
  reg [7:0] memory [0:255];
  reg [7:0] registers [0:3];
  reg [7:0] pc, wait_count;
  reg condition_flag, memory_pending, memory_write;
  reg [7:0] memory_address, memory_data;
  reg [1:0] memory_destination;
  (* async_reg = "true", keep = "true" *) reg [INPUT_PINS-1:0] pin_sync_meta;
  (* async_reg = "true", keep = "true" *) reg [INPUT_PINS-1:0] pin_sync;
  reg cfg_mode_d, cfg_write_d;
  reg [7:0] cfg_address;
  reg [1:0] cfg_chunk;
  reg [11:0] cfg_partial;
  wire [15:0] instruction = program_mem[pc];
  wire [3:0] opcode = instruction[15:12];
  wire [3:0] operand = instruction[11:8];
  wire [1:0] operation = operand[3:2];
  wire [1:0] rd = operand[1:0];
  wire [7:0] immediate = instruction[7:0];
  wire [1:0] rs = immediate[1:0];
  wire [7:0] selected_pin = opcode == 4'h5 ? registers[rs] : immediate;
  wire [7:0] waited_pin = operation == 2 ? registers[rs] : immediate;
  reg valid_instruction;
  reg [7:0] input_byte;
  integer i;

  assign loader_status = {cfg_address[5:0], cfg_chunk};
  always @(posedge clk) begin
    if (!rst_n) begin pin_sync_meta <= 0; pin_sync <= 0; end
    else begin pin_sync_meta <= pin_in; pin_sync <= pin_sync_meta; end
  end

  // Configuration is board-clocked, not asynchronous. Upload at most 256 words.
  always @(posedge clk) begin
    if (!rst_n) begin
      cfg_mode_d <= 0; cfg_write_d <= 0; cfg_address <= 0;
      cfg_chunk <= 0; cfg_partial <= 0;
    end else begin
      cfg_mode_d <= cfg_mode; cfg_write_d <= cfg_write;
      if (cfg_mode && !cfg_mode_d) begin
        cfg_address <= 0; cfg_chunk <= 0; cfg_write_d <= 0;
      end else if (cfg_mode && cfg_write && !cfg_write_d) begin
        case (cfg_chunk)
          0: begin cfg_partial[5:0] <= cfg_data; cfg_chunk <= 1; end
          1: begin cfg_partial[11:6] <= cfg_data; cfg_chunk <= 2; end
          2: begin
            program_mem[cfg_address] <= {cfg_data[3:0], cfg_partial};
            cfg_address <= cfg_address + 1'b1; cfg_chunk <= 0;
          end
          default: cfg_chunk <= 0;
        endcase
      end
    end
  end

  // Validate before executing, so malformed words have no partial side effects.
  always @* begin
    valid_instruction = 0;
    input_byte = 0;
    for (integer bit_number = 0; bit_number < INPUT_PINS; bit_number = bit_number + 1)
      if (bit_number / 8 == {24'b0, immediate}) input_byte[bit_number % 8] = pin_sync[bit_number];
    case (opcode)
      4'h0: valid_instruction = instruction == 0;
      4'h1: valid_instruction = operation != 2 || immediate[7:2] == 0;
      4'h2, 4'h3: valid_instruction = operation == 1 && immediate[7:2] == 0;
      4'h4: valid_instruction = operation == 0 ? immediate < (INPUT_PINS+7)/8 :
          (operation == 1 || operation == 2) && immediate < (OUTPUT_PINS+7)/8;
      4'h5, 4'he: valid_instruction = (opcode == 4'he || immediate[7:2] == 0) &&
          (operation == 1 ? selected_pin < INPUT_PINS : selected_pin < OUTPUT_PINS);
      4'h7: valid_instruction = operand == 0;
      4'h8: valid_instruction = operand == 0 || operand == 8;
      4'h9, 4'ha: valid_instruction = operation == 0;
      4'hb: valid_instruction = immediate[7:2] == 0;
      4'hc: valid_instruction = 1;
      4'hd: valid_instruction = immediate == 0;
      4'hf: valid_instruction = instruction == 16'hf000 ||
          ((operand == 4 || operand == 5 || operand == 8 || operand == 9) &&
           (operation != 2 || immediate[7:2] == 0) && waited_pin < INPUT_PINS);
      default: valid_instruction = 0;
    endcase
  end

  always @(posedge clk) begin
    if (!rst_n || cfg_mode) begin
      pc <= 0; wait_count <= 0; halted <= 0; condition_flag <= 0;
      pin_out <= 0; pin_oe <= 0;
      memory_pending <= 0; memory_write <= 0; memory_address <= 0;
      memory_data <= 0; memory_destination <= 0;
      for (i = 0; i < 4; i = i + 1) registers[i] <= 0;
    end else if (memory_pending) begin
      if (memory_write) memory[memory_address] <= memory_data;
      else registers[memory_destination] <= memory[memory_address];
      memory_pending <= 0; condition_flag <= 1; pc <= pc + 1'b1;
    end else if (enable && !halted) begin
      if (wait_count != 0) wait_count <= wait_count - 1'b1;
      else if (!valid_instruction) halted <= 1;
      else begin
        pc <= pc + 1'b1;
        case (opcode)
          4'h0: begin end
          4'h1: case (operation)
            0: registers[rd] <= immediate;
            1: condition_flag <= registers[rd] == immediate;
            2: condition_flag <= registers[rd] < registers[rs];
            3: condition_flag <= registers[rd] < immediate;
          endcase
          4'h2, 4'h3: begin
            memory_pending <= 1; memory_write <= opcode == 3;
            memory_address <= registers[rs]; memory_data <= registers[rd];
            memory_destination <= rd; pc <= pc;
          end
          4'h4: begin
            if (operation == 0) registers[rd] <= input_byte;
            else for (integer pin_number = 0; pin_number < OUTPUT_PINS; pin_number = pin_number + 1)
              if (pin_number / 8 == {24'b0, immediate}) begin
                if (operation == 1) pin_out[pin_number] <= registers[rd][pin_number % 8];
                else pin_oe[pin_number] <= registers[rd][pin_number % 8];
              end
          end
          4'h5, 4'he: case (operation)
            0: pin_out[selected_pin[OUTPUT_INDEX_BITS-1:0]] <= registers[rd][0];
            1: registers[rd] <= {7'b0, pin_sync[selected_pin[INPUT_INDEX_BITS-1:0]]};
            2: pin_oe[selected_pin[OUTPUT_INDEX_BITS-1:0]] <= registers[rd][0];
            3: pin_oe[selected_pin[OUTPUT_INDEX_BITS-1:0]] <= ~registers[rd][0];
          endcase
          4'h7: wait_count <= immediate;
          4'h8: if (operand == 0 || !condition_flag) pc <= immediate;
          4'h9: if (registers[rd] == 0) pc <= immediate;
          4'ha: begin
            registers[rd] <= registers[rd] - 1'b1;
            if (registers[rd] != 1) pc <= immediate;
          end
          4'hb: case (operation)
            0: registers[rd] <= registers[rs];
            1: registers[rd] <= registers[rd] ^ registers[rs];
            2: registers[rd] <= registers[rd] | registers[rs];
            3: registers[rd] <= registers[rd] & registers[rs];
          endcase
          4'hc: case (operation)
            0: registers[rd] <= registers[rd] + immediate;
            1: registers[rd] <= registers[rd] & immediate;
            2: registers[rd] <= registers[rd] | immediate;
            3: registers[rd] <= registers[rd] ^ immediate;
          endcase
          4'hd: case (operation)
            0: registers[rd] <= registers[rd] << 1;
            1: registers[rd] <= registers[rd] >> 1;
            2: registers[rd] <= {registers[rd][6:0], registers[rd][7]};
            3: registers[rd] <= {registers[rd][0], registers[rd][7:1]};
          endcase
          4'hf: if (instruction == 16'hf000) halted <= 1;
            else if (pin_sync[waited_pin[INPUT_INDEX_BITS-1:0]] != operand[0]) pc <= pc;
          default: halted <= 1;
        endcase
      end
    end
  end
endmodule
`default_nettype wire
