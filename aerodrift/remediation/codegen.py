"""AST-based remediation code generator.

Filled in during Week 3, after the drift-to-remediation contract
with Person B is locked (Week 1 Day 3-4 sync, refined Week 3).
"""


def generate_remediation_code(drift: dict) -> str:
    """Given a drift object, return generated remediation source code.

    Args:
        drift: dict shaped per the agreed contract
            (type, affected_node, offending_edge/rule).

    Returns:
        Generated Python source as a string (not implemented yet).
    """
    raise NotImplementedError("codegen: implemented in Week 3")
