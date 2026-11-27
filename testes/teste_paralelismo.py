"""Teste unitário sem dependências externas."""
import importlib.util
from pathlib import Path
spec=importlib.util.spec_from_file_location('benchmark_paralelo',Path(__file__).with_name('benchmark_paralelo.py'))
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def test_igualdade_resultados():
    jobs=[(i,100) for i in range(4)]
    seq=list(map(module.processar_lote,jobs))
    assert seq==[module.processar_lote(j) for j in jobs]
    assert len(set(seq))==4
