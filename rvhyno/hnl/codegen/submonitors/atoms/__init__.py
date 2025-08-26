from rvhyno.hnl.codegen.submonitors.atoms.ehl import CodeGenCpp as CodeGen_eHL
from rvhyno.hnl.codegen.submonitors.atoms.shl import CodeGenCpp as CodeGen_sHL
from rvhyno.hnl.codegen.submonitors.hltl.codegen import CodeGenCpp as CodeGen_HLTL


def get_atoms_codegen(formula, logic: str):
    if formula.is_hltl():
        return CodeGen_HLTL
    if logic == "shl":
        return CodeGen_sHL
    if logic == "ehl":
        return CodeGen_eHL

    raise RuntimeError(f"Invalid logic: {logic} or formula: {formula}")
