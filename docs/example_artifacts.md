# Example HDL and diagrams

Run any example with no arguments:

```sh
cargo run --locked -p bitlogic --example emit
cargo run --locked -p bitlogic --example set
cargo run --locked -p bitlogic --example crc
cargo run --locked -p bitlogic --example protocol_processor
```

Each invocation creates a unique `/tmp/bitlogic-<module>-<random>` folder and
prints its absolute path on stdout. Cargo build messages stay on stderr.
Directories persist after the process exits, until removed by the user or the
system's temporary-file cleanup. `/tmp` is used even if `TMPDIR` points elsewhere.
Arguments are rejected; no demo, trace, output selection or parameter mode runs.

| File | Contents |
|---|---|
| `<module>.v` | Generated combinational Verilog interface and continuous-assignment implementation |
| `block.svg` | Browser-viewable module block with every input/output port and bit width |
| `circuit.mmd` | Complete Mermaid flowchart of the typed IR: constants, operators, labeled operands, widths and output connections |

The module names are `select_logic`, `set_step`, `crc4` and `processor_step`.
The circuit graph includes all captured nodes, including unused expressions;
it is an unoptimized structural view. Larger graphs may need a Mermaid viewer
that honors the supplied edge/text limits. The SVG remains small and can be
opened directly without network access or rendering dependencies.

The processor additionally writes:

| File | Contents |
|---|---|
| `processor_top.v` | Clocked `protocol_processor` implementation with state registers and synchronous reset |
| `pads.v` | Logical `protocol_pads` tri-state adapter |
| `implementation.v` | Combined core, register wrapper and pad adapter, ready as one Verilog source |
| `processor.mmd` | Integration block diagram: state feedback, clock/reset, external ROM, synchronization and IO boundaries |

Compile either the combined file or the three separate files. External program
memory, input synchronization and physical IO cells remain the integrator's
responsibility. The diagrams do not represent placement, routing or physical
signoff. Protocol program builders and waveform/reference checks remain available
in the processor tests; the example executable only exports hardware artifacts.

Build scripts capture the printed folder and copy the required Verilog into
their established build directories. For example:

```sh
artifacts=$(cargo run --locked -p bitlogic --example protocol_processor)
iverilog -g2012 -s protocol_processor -o /tmp/processor.vvp "$artifacts/implementation.v"
```

`make emit` and `make example` export the select example. `make processor-synth`,
`make processor-mapped-test`, the SKY130 flow and the migration-equivalence script
consume the generated processor files automatically. Historical evidence logs
retain the commands used to produce those original results.
