from rvhyno.hnl.codegen.submonitors.atoms.ehl import CodeGenCpp as CodeGen_eHL
from rvhyno.hnl.codegen.submonitors.atoms.shl import CodeGenCpp as CodeGen_sHL


def get_atoms_codegen(logic: str):
    if logic == "shl":
        return CodeGen_sHL
    if logic == "ehl":
        return CodeGen_eHL

    raise RuntimeError(f"Invalid logic: {logic}")
