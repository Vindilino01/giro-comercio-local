"""Regenera os CSVs (limpo e sujo) sem carregar no banco."""

import sys
import time
from pathlib import Path

RAIZ = Path(__file__).parent.parent
sys.path.insert(0, str(RAIZ))
import os
os.chdir(RAIZ)

from src.gerador import ESCALAS, gerar
from src.injetor_defeitos import injetar

t0 = time.time()
resumo = gerar(ESCALAS["padrao"], Path("data/bronze/limpo"), verbose=False)
taxa = resumo.ruins["taxa_ruptura_sku_dia_pct"]
total = sum(resumo.tabelas.values())
print(f"gerado em {time.time() - t0:.0f}s: {total:,} linhas | ruptura {taxa}%")

for tabela, n in resumo.tabelas.items():
    print(f"  {tabela:<24} {n:>10,}")

gab = injetar(Path("data/bronze/limpo"), Path("data/bronze/sujo"))
n_def = sum(len(v) for v in gab.registros.values())
print(f"defeitos: {len(gab.defeitos)} tipos, {n_def:,} registros corrompidos")
