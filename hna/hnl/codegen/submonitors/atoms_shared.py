from hna.hnl.codegen.submonitors.atoms_shl import CodeGenCpp as CodeGen_sHL
from hna.hnl.codegen.submonitors.atoms_ehl import CodeGenCpp as CodeGen_eHL

def get_atoms_codegen(logic: str):
    if logic == "shl":
        return CodeGen_sHL
    if logic == "ehl":
        return CodeGen_eHL

    raise RuntimeError(f"Invalid logic: {logic}")
