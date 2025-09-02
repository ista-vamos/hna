"""
Code generation for hypernode logic.

In this package, there two main parts:
 - generating the top-level monitor
 - generating the propositional structure of the quantifier-free body of the formula,
   this is represented as an BDD.
"""

from .codegen import CodeGenCppTopLevel
