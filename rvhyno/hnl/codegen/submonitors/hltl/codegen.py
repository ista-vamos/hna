from ..shared import CodeGenCpp

class CodeGenCpp(CodeGenCpp):
    """
    Class for generating monitors in C++.
    The main function to be called is `generate`.
    """

    def __init__(
        self,
        name,
        args,
        fixed_quantifiers=None,
        out_dir: str = None,
        namespace: str = None,
        embedded: bool = False,
    ):
        super().__init__(name, args, fixed_quantifiers, out_dir, namespace, embedded)

    def generate(self, formula):
        raise NotImplementedError(f"HLTL here: {formula}")