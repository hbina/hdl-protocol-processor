"""Compare a fixed construction loop with an input-controlled bounded loop.

Both loops build finite, acyclic hardware graphs. They do not run one iteration
per clock: all stages exist together as combinational logic.
"""

from combhdl import Add, Component, Const, If, Input, Lt, Output

value = Input("value", 8)
count = Input("count", 2)  # Runtime input: 0, 1, 2, or 3 increments.
one = Const(1, 8)

# The Python loop runs during construction, creating three Add nodes in a chain.
# Reassigning this Python name does not change any previously constructed node.
fixed_result = value
for _ in range(3):
    fixed_result = Add(fixed_result, one)

# This loop also creates three stages, but each has an input-controlled If node.
# Stage 0 increments if count > 0, stage 1 if count > 1, and so on.
# Follow each If's false edge in graph.html to see how a stage is bypassed.
bounded_result = value
for step in range(3):
    bounded_result = If(
        Lt(Const(step, 2), count),
        Add(bounded_result, one),
        bounded_result,
    )

component = Component(
    "loop_example",
    [value, count],
    [
        Output("fixed_three", fixed_result),
        Output("bounded_count", bounded_result),
    ],
)
