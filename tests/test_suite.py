"""Camada pytest sobre as suites de script.

POR QUE ESTE ARQUIVO EXISTE
---------------------------
`python -m pytest` coletava ZERO testes: `tests/test_constraints.py` e
`tests/test_integridade.py` sao scripts com `main()` e classes que nao
comecam com `Test`, entao o pytest nao as reconhece. O README prometia
"22 + 25 + 17 testes" e o comando canonico de qualquer projeto Python
(`pytest`) dizia "no tests ran" - exit code 5.

Aqui cada suite e exposta como um teste que chama o script e verifica o
codigo de saida. Nao reimplementa a logica: executa a mesma coisa que o
`run_all.py` executa, para que nao existam duas verdades.

Requer o banco no ar (o mesmo requisito das suites originais).
"""

import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).parent.parent
DSN = "host=127.0.0.1 port=5433 dbname=giro user=postgres"


def rodar(script: Path, timeout: int = 900) -> subprocess.CompletedProcess:
    """Executa um dos scripts de teste e devolve o processo."""
    return subprocess.run(
        [sys.executable, str(script)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=RAIZ, timeout=timeout,
        env={**__import__("os").environ, "GIRO_DSN": DSN,
             "PYTHONIOENCODING": "utf-8"},
    )


def test_constraints_do_modelo() -> None:
    """23 casos de constraint: cada um deveria ser recusado pelo banco."""
    r = rodar(RAIZ / "tests" / "test_constraints.py")
    assert r.returncode == 0, f"saida:\n{r.stdout[-2000:]}\n{r.stderr[-1000:]}"
    assert "23/23" in r.stdout, f"esperado 23/23:\n{r.stdout[-1500:]}"


def test_integridade_dos_dados() -> None:
    """25 invariantes sobre os dados carregados."""
    r = rodar(RAIZ / "tests" / "test_integridade.py")
    assert r.returncode == 0, f"saida:\n{r.stdout[-2000:]}\n{r.stderr[-1000:]}"
    assert "25/25" in r.stdout, f"esperado 25/25:\n{r.stdout[-1500:]}"


def test_invariantes_do_gerador() -> None:
    """As invariantes do gerador rodam sobre uma amostra pequena."""
    r = rodar(RAIZ / "tests" / "test_gerador.py", timeout=1800)
    assert r.returncode == 0, f"saida:\n{r.stdout[-2000:]}\n{r.stderr[-1000:]}"


def test_painel_bate_com_o_banco() -> None:
    """Cada numero exibido no painel confere com a consulta no banco."""
    r = rodar(RAIZ / "dashboard" / "verificar.py", timeout=600)
    assert r.returncode == 0, f"saida:\n{r.stdout[-2000:]}"
    assert "0 falha" in r.stdout, f"divergencias:\n{r.stdout[-1500:]}"


@pytest.mark.skipif(
    subprocess.run(["node", "--version"], capture_output=True).returncode != 0,
    reason="Node ausente; verificacao de runtime do painel nao roda",
)
def test_painel_em_runtime() -> None:
    """Abre o painel num browser: JS sem erro, grafico, impressao, a11y."""
    r = subprocess.run(
        ["node", str(RAIZ / "scripts" / "verificar_painel.js")],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=RAIZ, timeout=600,
    )
    assert r.returncode == 0, f"saida:\n{r.stdout[-2500:]}"
