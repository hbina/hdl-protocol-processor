from combhdl import And, Component, If, Input, Or, Output, Xor

a = Input("a", width=8)
b = Input("b", width=8)
choose = Input("choose", width=1)
shared = Xor(a, b)
component = Component(
    name="example",
    inputs=[a, b, choose],
    outputs=[Output("result", If(choose, And(shared, a), Or(shared, b)))],
)
