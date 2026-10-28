from combhdl import And, Component, If, Input, Or, Output, Xor

a = Input("a", width=4)
b = Input("b", width=4)
choose = Input("choose", width=1)
shared = Xor(a, b)
demo = Component(
    name="combhdl_demo",
    inputs=[a, b, choose],
    outputs=[
        Output("shared", shared),
        Output("result", If(choose, And(shared, a), Or(shared, b))),
    ],
)
