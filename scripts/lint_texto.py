"""Lint de texto: barra o que faz o documento parecer gerado e denso.

POR QUE ESTE ARQUIVO EXISTE
---------------------------
A documentacao chegou a 18.439 palavras e 66 paginas. O problema nao era
vocabulario - medi e havia 3 "nao apenas" e 1 "literalmente" em 18 mil
palavras. O problema era estrutural: frase de 35 palavras com tres ideias
emendadas, e a justificativa sempre depois do fato.

Regras (o edital e a leitura, nao o gosto):

  1. Frase com no maximo 20 palavras. Acima disso, divide.
  2. Paragrafo com no maximo 5 linhas (~90 palavras).
  3. Sem metafora de consultoria: alicerce, coracao, jornada, universo.
  4. Sem muleta de entusiasmo: "de verdade", "na pratica", "simplesmente".
  5. Sem construcao "nao e X, e Y" (a marca mais reconhecivel de texto
     gerado, e a que mais aparece em apresentacao).
  6. Numero sempre com unidade ou contexto.

Uso:
    python scripts/lint_texto.py                 # todos os docs
    python scripts/lint_texto.py docs/01-problema.md
    python scripts/lint_texto.py --silencioso    # so o codigo de saida

Saida: 0 se aprovado, 1 se houver violacao.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).parent.parent

# ---------------------------------------------------------------------
# Limites
# ---------------------------------------------------------------------
MAX_PALAVRAS_FRASE = 20
MAX_PALAVRAS_PARAGRAFO = 90

# ---------------------------------------------------------------------
# Metaforas de consultoria. Cada uma tem um substituto direto.
# ---------------------------------------------------------------------
METAFORAS = {
    "alicerce": "base",
    "coração do": "centro do",
    "coracao do": "centro do",
    "jornada": "processo",
    "universo de": "conjunto de",
    "ecossistema": "conjunto de ferramentas",
    "robusto": "confiável",
    "robusta": "confiável",
    "robustez": "confiabilidade",
    "escalável": "que cresce",
    "escalavel": "que cresce",
    "sinergia": "cooperação",
    "holístico": "completo",
    "holistico": "completo",
    "paradigma": "modelo",
    "disruptivo": "novo",
    "stakeholder": "interessado",
}

# ---------------------------------------------------------------------
# Muletas: nao acrescentam informacao.
# ---------------------------------------------------------------------
MULETAS = [
    "de verdade",
    "na prática",
    "na pratica",
    "simplesmente",
    "literalmente",
    "basicamente",
    "essencialmente",
    "fundamentalmente",
    "vale destacar",
    "é importante notar",
    "e importante notar",
    "cabe ressaltar",
    "não apenas",
    "nao apenas",
    "de certa forma",
    "em suma",
    "resumindo",
    "por assim dizer",
    "sem sombra de dúvida",
    "sem sombra de duvida",
]

# ---------------------------------------------------------------------
# "Nao e X, e Y" - a construcao mais reconhecivel de texto gerado.
# ---------------------------------------------------------------------
PADRAO_NAO_E = re.compile(
    r"\b(?:n[ãa]o|N[ãa]o)\s+(?:é|e)\s+[^.,;]{2,40}[,.]?\s*(?:é|e|mas|e sim)\s+",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------
# Numero sem unidade. Pega "8,62%" solto bem, mas cobra contexto quando o
# numero aparece sozinho como valor de uma metrica.
# ---------------------------------------------------------------------
PADRAO_PORCENTAGEM_SOLTA = re.compile(r"(?<![\w.])\d{1,3},\d{1,2}%(?!\s*\()")

# Isencoes: dentro de tabela, de bloco de codigo e de link, o numero nao
# precisa de contexto - a coluna ja da o contexto.
IGNORAR_LINHAS = re.compile(r"^\s*(?:\||```|>|-\s*\[|!\[|<)")


def dividir_frases(texto: str) -> list[str]:
    """Divide em frases sem quebrar em abreviacoes comuns."""
    texto = re.sub(r"\b(e\.g|i\.e|etc|vs|Sr|Dra|Dr|p\.ex)\.", r"\1<DOT>", texto)
    partes = re.split(r"(?<=[.!?])\s+", texto)
    return [p.replace("<DOT>", ".") for p in partes if p.strip()]


def limpar_markdown(linha: str) -> str:
    """Remove marcacao que nao e texto lido."""
    linha = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", linha)
    linha = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", linha)
    linha = re.sub(r"`([^`]+)`", r"\1", linha)
    linha = re.sub(r"\*\*([^*]+)\*\*", r"\1", linha)
    linha = re.sub(r"\*([^*]+)\*", r"\1", linha)
    linha = re.sub(r"^\s*#{1,6}\s*", "", linha)
    return linha.strip()


def analisar(arquivo: Path) -> list[tuple[int, str, str]]:
    """Devolve [(linha, regra, detalhe)]."""
    problemas: list[tuple[int, str, str]] = []
    texto = arquivo.read_text(encoding="utf-8")
    linhas = texto.splitlines()

    em_codigo = False
    paragrafo: list[str] = []
    linha_inicio = 0

    for numero, bruta in enumerate(linhas, 1):
        if bruta.strip().startswith("```"):
            em_codigo = not em_codigo
            continue
        if em_codigo:
            continue

        limpa = limpar_markdown(bruta)

        # ---- paragrafo: junta linhas consecutivas de prosa ----
        if not limpa or IGNORAR_LINHAS.match(bruta):
            if paragrafo:
                _fechar_paragrafo(paragrafo, linha_inicio, problemas)
                paragrafo = []
            # Linhas de tabela e lista ainda passam pelo lint de frase,
            # porque a celula tambem e lida.
            if limpa and IGNORAR_LINHAS.match(bruta) and not bruta.strip().startswith(("|", ">", "-", "*")):
                _checar_linha(limpa, numero, problemas)
            continue

        if bruta.strip().startswith(("-", "*", "+", "|", ">")) or re.match(r"^\d+[.)]\s", bruta.strip()):
            if paragrafo:
                _fechar_paragrafo(paragrafo, linha_inicio, problemas)
                paragrafo = []
            _checar_linha(limpa, numero, problemas)
            continue

        if not paragrafo:
            linha_inicio = numero
        paragrafo.append(limpa)

    if paragrafo:
        _fechar_paragrafo(paragrafo, linha_inicio, problemas)

    return problemas


def _fechar_paragrafo(partes: list[str], linha: int, saida: list) -> None:
    texto = " ".join(partes)
    palavras = len(texto.split())
    if palavras > MAX_PALAVRAS_PARAGRAFO:
        saida.append((linha, "paragrafo-longo", f"{palavras} palavras"))
    _checar_linha(texto, linha, saida)


def _checar_linha(texto: str, linha: int, saida: list) -> None:
    # 1. frase longa
    for frase in dividir_frases(texto):
        n = len(frase.split())
        if n > MAX_PALAVRAS_FRASE:
            saida.append((linha, "frase-longa", f"{n} palavras: {frase[:70]}..."))

    baixo = texto.lower()

    # 2. metafora
    for termo, troca in METAFORAS.items():
        if termo in baixo:
            saida.append((linha, "metafora", f"{termo!r} -> use {troca!r}"))

    # 3. muleta
    for muleta in MULETAS:
        if muleta in baixo:
            saida.append((linha, "muleta", f"{muleta!r} nao acrescenta informacao"))

    # 4. "nao e X, e Y"
    m = PADRAO_NAO_E.search(texto)
    if m:
        saida.append((linha, "nao-e-mas-e", m.group(0)[:60]))

    # 5. porcentagem solta
    for m in PADRAO_PORCENTAGEM_SOLTA.finditer(texto):
        saida.append((linha, "numero-sem-contexto", m.group(0)))


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    silencioso = "--silencioso" in sys.argv

    if args:
        alvos = [Path(a) for a in args]
    else:
        alvos = sorted((RAIZ / "docs").glob("0*.md"))

    total = 0
    por_regra: dict[str, int] = {}

    for arquivo in alvos:
        if not arquivo.exists():
            print(f"ausente: {arquivo}")
            continue
        problemas = analisar(arquivo)
        total += len(problemas)

        if problemas and not silencioso:
            print(f"\n{arquivo.name}  ({len(problemas)} problemas)")
            vistos = set()
            for linha, regra, detalhe in problemas:
                chave = (regra, detalhe[:40])
                if chave in vistos:
                    continue
                vistos.add(chave)
                print(f"  L{linha:<5} {regra:<22} {detalhe}")

        for _, regra, _ in problemas:
            por_regra[regra] = por_regra.get(regra, 0) + 1

    if not silencioso:
        print(f"\n{'=' * 58}")
        print(f"total de violacoes: {total}")
        for regra, n in sorted(por_regra.items(), key=lambda x: -x[1]):
            print(f"  {regra:<24} {n}")

    return 0 if total == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
