# Copyright 2023 The Regents of the University of California
# released under BSD 3-Clause License
# author: Kevin Laeufer <laeufer@cs.berkeley.edu>
#
# Code for concrete execution
import llvmlite.binding as llvm
import ctypes
import random
from metalift.analysis_new import AnalysisResult
from metalift.ir import Type

# All these initializations are required for code generation!
llvm.initialize()
llvm.initialize_native_target()
llvm.initialize_native_asmprinter()  # yes, even this one

_MaxInt = (1 << (32 - 1)) - 1
_MinInt = -(1 << (32 - 1))
_SpecialInt = [-1, 1, 0, _MinInt, _MaxInt]
_SmallIntMin = -13
_SmallIntMax = 13


class Generator:
    def __init__(self, rnd: random.Random):
        self.rnd = rnd

    def sample_args(self, analysis: AnalysisResult):
        return [self.sample_tpe(arg.type) for arg in analysis.arguments]

    def sample_tpe(self, tpe: Type):
        if tpe.name == "Int":
            return self.sample_int()
        raise NotImplementedError(f"TODO: {tpe}")

    def sample_int(self):
        choice = self.rnd.choice(["All", "Small", "Special"])
        if choice == "All":
            return self.rnd.randint(_MinInt, _MaxInt)
        if choice == "Small":
            return self.rnd.randint(_SmallIntMin, _SmallIntMax)
        if choice == "Special":
            return self.rnd.choice(_SpecialInt)


def gen_traces(cfunc, analysis: AnalysisResult, rnd: random.Random, count: int):
    assert count >= 0
    traces = []
    gen = Generator(rnd)
    for _ in range(count):
        args = gen.sample_args(analysis)
        ret = cfunc(*args)
        traces.append((ret, args))
    return traces


def compile_function(filename: str, analysis: AnalysisResult):
    global _engine
    with open(filename) as ff:
        llvm_ir = ff.read()
    # Create a LLVM module object from the IR
    mod = llvm.parse_assembly(llvm_ir)
    mod.verify()
    # load engine
    if _engine is None:
        _engine = create_execution_engine()
    engine = _engine
    # Now add the module and make sure it is ready for execution
    engine.add_module(mod)
    engine.finalize_object()
    engine.run_static_constructors()

    # access function
    fn_name = analysis.name
    func_ptr = engine.get_function_address(fn_name)
    cfunc = _analysis_to_c_func(analysis)(func_ptr)
    return cfunc


def _analysis_to_c_func(analysis: AnalysisResult):
    types = [analysis.return_type] + [a.type for a in analysis.arguments]
    c_types = [_meta_tpe_to_c_tpe(tpe) for tpe in types]
    return ctypes.CFUNCTYPE(*c_types)


def _meta_tpe_to_c_tpe(tpe: Type):
    if tpe.name == "Int":
        return ctypes.c_int
    raise NotImplementedError(f"TODO: {tpe}")


_engine = None


def create_execution_engine():
    """
    Create an ExecutionEngine suitable for JIT code generation on
    the host CPU.  The engine is reusable for an arbitrary number of
    modules.
    """
    # Create a target machine representing the host
    target = llvm.Target.from_default_triple()
    target_machine = target.create_target_machine()
    # And an execution engine with an empty backing module
    backing_mod = llvm.parse_assembly("")
    engine = llvm.create_mcjit_compiler(backing_mod, target_machine)
    return engine
