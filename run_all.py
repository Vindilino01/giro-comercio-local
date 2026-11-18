"""
Orquestrador do projeto Giro.

Recria o ambiente do zero em um comando. Cada etapa e independente e
pode ser executada sozinha, o que importa em duas situacoes:
  - durante o desenvolvimento (nao queremos regenerar 4M de linhas a
    cada ajuste de consulta);
  - no pitch (se algo falhar, da para refazer so a etapa quebrada).

Uso:
    python run_all.py --reset          # tudo, do zero
    python run_all.py --etapa db       # so migrations
    python run_all.py --etapa dados    # geracao + carga
    python run_all.py --etapa marts    # star schema e views
    python run_all.py --etapa testes   # validacao
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).parent
sys.path.insert(0, str(RAIZ))

PG_BIN = Path(r"C:\Program Files\PostgreSQL\18\bin")
PG_SERVICO = "postgresql-giro-5433"
DSN = os.environ.get("GIRO_DSN", "host=127.0.0.1 port=5433 dbname=giro user=postgres")


# =====================================================================
# Utilidades de console
# =====================================================================

class C:
    OK = "\033[92m"
    ERRO = "\033[91m"
    AVISO = "\033[93m"
    INFO = "\033[96m"
    DIM = "\033[2m"
    FIM = "\033[0m"


def titulo(texto: str) -> None:
    print(f"\n{C.INFO}{'=' * 70}\n  {texto}\n{'=' * 70}{C.FIM}")


def passo(texto: str) -> None:
    print(f"  {C.DIM}->{C.FIM} {texto}")


def ok(texto: str) -> None:
    print(f"  {C.OK}OK{C.FIM} {texto}")


def aviso(texto: str) -> None:
    print(f"  {C.AVISO}!{C.FIM}  {texto}")


def erro(texto: str) -> None:
    print(f"  {C.ERRO}X{C.FIM}  {texto}")


# =====================================================================
# Banco
# =====================================================================

def psql(*args: str, dsn: str | None = None, capturar: bool = False) -> str:
    """Executa psql.

    O DSN precisa ser quebrado em flags (-h -p -U -d). Passar a string
    connessione inteira como um argumento faz o psql ignora-la e cair no
    default (porta 5432), porque ele espera flags, nao uma URI.
    """
    exe = PG_BIN / "psql.exe"
    if dsn:
        partes = dict(kv.split("=", 1) for kv in dsn.split())
        con = ["-h", partes.get("host", "127.0.0.1"),
               "-p", partes.get("port", "5433"),
               "-U", partes.get("user", "postgres"),
               "-d", partes.get("dbname", "giro")]
    else:
        con = ["-h", "127.0.0.1", "-p", "5433", "-U", "postgres", "-d", "giro"]

    cmd = [str(exe), *con, "-v", "ON_ERROR_STOP=1", "-X", "-q", *args]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"psql falhou: {r.stderr.strip()[:800]}")
    return r.stdout if capturar else ""


def servico_ativo() -> bool:
    """Testa se ha um PostgreSQL respondendo na porta do projeto.

    POR QUE NAO CONSULTAR O SERVICO DO WINDOWS
    ------------------------------------------
    A primeira versao fazia `sc query postgresql-giro-5433` e
    `net start postgresql-giro-5433`. Em maquina limpa esse servico nao
    existe: o `scripts/pg.ps1` cria o cluster com `initdb` + `pg_ctl`
    start e nunca registra servico. O comando que o README manda rodar
    falhava imediatamente com "servico nao iniciou".
    Aqui o criterio e o que importa de fato: existe um servidor
    respondendo em 127.0.0.1:5433?
    """
    r = subprocess.run([str(PG_BIN / "pg_isready.exe"), "-h", "127.0.0.1",
                        "-p", "5433"], capture_output=True, text=True)
    return r.returncode == 0


def garantir_servico() -> None:
    """Garante um PostgreSQL na porta 5433, subindo o cluster se preciso.

    ORDEM DAS TENTATIVAS
    --------------------
    1. `scripts/pg.ps1 start` - o caminho portatil, que funciona em
       qualquer maquina com PostgreSQL 18 instalado.
    2. Servico do Windows `postgresql-giro-5433` - so existe na maquina
       do autor do projeto. Fica como segundo porque exige privilegio de
       administrador e nao e reproduzivel.

    A versao anterior tentava o servico PRIMEIRO. Numa maquina limpa ele
    nao existe e o comando do README falhava; na maquina do autor, o
    servico apontava para um data dir diferente do que o pg.ps1 gerencia,
    produzindo dois clusters concorrentes na mesma porta.
    """
    if servico_ativo():
        return

    passo("PostgreSQL nao esta respondendo na porta 5433; iniciando")

    # 1) Cluster gerenciado por scripts/pg.ps1 (portatil)
    pg_script = RAIZ / "scripts" / "pg.ps1"
    if pg_script.exists():
        r = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", str(pg_script), "start"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=RAIZ)
        for _ in range(60):
            time.sleep(0.5)
            if servico_ativo():
                ok("cluster do projeto no ar")
                return
        detalhe = (r.stderr or r.stdout).strip()[-500:]
        if detalhe:
            aviso(f"pg.ps1 nao subiu o cluster: {detalhe}")

    # 2) Servico do Windows (ambiente do autor do projeto)
    svc = subprocess.run(["sc", "query", PG_SERVICO], capture_output=True,
                         text=True, encoding="cp850", errors="replace")
    if "SERVICE_NAME" in svc.stdout.upper():
        subprocess.run(["net", "start", PG_SERVICO], capture_output=True)
        for _ in range(30):
            time.sleep(0.5)
            if servico_ativo():
                ok("servico do Windows no ar")
                return

    raise RuntimeError(
        "PostgreSQL nao respondeu na porta 5433.\n"
        "  Opcoes:\n"
        "    .\\scripts\\pg.ps1 start\n"
        "    ou instale o PostgreSQL 18 e crie um cluster em 127.0.0.1:5433\n"
        "       com usuario 'postgres' e autenticacao trust.")


def banco_existe() -> bool:
    out = psql("-tAc",
               "SELECT 1 FROM pg_database WHERE datname='giro'",
               dsn="host=127.0.0.1 port=5433 dbname=postgres user=postgres",
               capturar=True)
    return out.strip() == "1"


def schema_existe() -> bool:
    """Verifica se o schema ja foi aplicado (evita reaplicar migrations)."""
    try:
        out = psql("-tAc",
                   "SELECT count(*) FROM pg_type WHERE typname='ean13'",
                   capturar=True)
        return int(out.strip() or 0) > 0
    except RuntimeError:
        return False


def recriar_banco() -> None:
    dsn_admin = "host=127.0.0.1 port=5433 dbname=postgres user=postgres"
    passo("encerrando conexoes e dropando o banco giro")
    psql("-d", "postgres", "-c", f"""
        SELECT pg_terminate_backend(pid) FROM pg_stat_activity
         WHERE datname = 'giro' AND pid <> pg_backend_pid()
    """, dsn=dsn_admin)
    psql("-d", "postgres", "-c", "DROP DATABASE IF EXISTS giro", dsn=dsn_admin)
    psql("-d", "postgres", "-c",
         "CREATE DATABASE giro WITH ENCODING 'UTF8' TEMPLATE template0",
         dsn=dsn_admin)
    ok("banco giro recriado")


# =====================================================================
# Etapas
# =====================================================================

def etapa_db(forcar: bool = False) -> None:
    titulo("ETAPA 1/7 - Migrations")
    garantir_servico()
    if not banco_existe():
        recriar_banco()
    elif schema_existe() and not forcar:
        aviso("schema ja aplicado (use --reset para recriar do zero)")
        return
    elif schema_existe() and forcar:
        recriar_banco()

    build = RAIZ / "db" / "build.sql"
    psql("-f", str(build))
    ok("schema criado")

    # Conferencia rapida de que os objetos existem
    n_tabelas = psql(dsn=DSN, capturar=True, *[
        "-tAc", """SELECT count(*) FROM pg_tables
                    WHERE schemaname IN ('prata','ouro','gov')"""])
    n_indices = psql(dsn=DSN, capturar=True, *[
        "-tAc", """SELECT count(*) FROM pg_indexes
                    WHERE schemaname IN ('prata','ouro','gov')"""])
    n_particoes = psql(dsn=DSN, capturar=True, *[
        "-tAc", """SELECT count(*) FROM pg_class c
                     JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname='prata' AND c.relispartition"""])
    ok(f"{n_tabelas.strip()} tabelas, {n_indices.strip()} indices, "
       f"{n_particoes.strip()} particoes")


def etapa_dados(escala: str = "padrao", subset: int | None = None,
                pular_geracao: bool = False) -> None:
    titulo("ETAPA 2/7 - Geracao e carga de dados")

    from src.gerador import ESCALAS, gerar
    from src.injetor_defeitos import injetar
    from src.ingestao import Ingestor
    import psycopg

    bronze = RAIZ / "data" / "bronze"
    limpo = bronze / "limpo"
    sujo = bronze / "sujo"

    if not pular_geracao:
        passo(f"gerando dataset '{escala}' (limpo)")
        t0 = time.time()
        resumo = gerar(ESCALAS[escala], limpo, verbose=True)
        ok(f"gerado em {time.time() - t0:.1f}s "
           f"({sum(resumo.tabelas.values()):,} linhas)")

        (bronze / "_resumo_geracao.json").write_text(
            json.dumps(resumo.como_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8")

        passo("injetando defeitos de qualidade (dataset 'sujo')")
        gab = injetar(limpo, sujo)
        n_def = sum(len(v) for v in gab.registros.values())
        ok(f"{len(gab.defeitos)} tipos de defeito, {n_def:,} registros corrompidos")
    else:
        if not limpo.exists():
            raise SystemExit("CSVs nao encontrados; rode sem --pular-geracao")

    passo("carregando dataset LIMPO no banco")
    with psycopg.connect(DSN) as conn:
        ing = Ingestor(conn, limpo)
        resultados = ing.executar_tudo()

    _imprimir_carga(resultados)
    (RAIZ / "docs" / "evidencias").mkdir(parents=True, exist_ok=True)
    (RAIZ / "docs" / "evidencias" / "carga_limpa.json").write_text(
        json.dumps([r.como_dict() for r in resultados],
                   ensure_ascii=False, indent=2), encoding="utf-8")
    ok("carga limpa concluida")


def etapa_sujo() -> None:
    titulo("ETAPA 3/7 - Carga do dataset sujo e metricas de qualidade")
    from src.ingestao import Ingestor
    from src.metricas_qualidade import analisar
    import psycopg

    sujo = RAIZ / "data" / "bronze" / "sujo"
    if not sujo.exists():
        raise SystemExit("dataset sujo nao existe; rode --etapa dados primeiro")

    # ------------------------------------------------------------------
    # Por que um banco separado?
    #
    # Se carregassemos o dataset sujo em cima do limpo, as rejeicoes
    # corromperiam as series historicas usadas nas consultas de negocio
    # (falta um dia inteiro de vendas, ha cupons cancelados sem data,
    # etc.). Os resultados de Q01..Q10 deixariam de refletir o modelo.
    #
    # Carregando num banco isolado (`giro_qualidade`), medimos a
    # eficacia das regras sobre um conjunto com defeitos CONHECIDOS,
    # sem tocar na base de negocio. Isso tambem deixa o experimento
    # reproduzivel: o banco de qualidade pode ser recriado sozinho.
    # ------------------------------------------------------------------
    dsn_q = DSN.replace("dbname=giro ", "dbname=giro_qualidade ")
    if "dbname=giro_qualidade" not in dsn_q:
        dsn_q = DSN + " dbname=giro_qualidade"
    dsn_admin = "host=127.0.0.1 port=5433 dbname=postgres user=postgres"

    passo("recriando banco isolado giro_qualidade")
    psql("-d", "postgres", "-c", """
        SELECT pg_terminate_backend(pid) FROM pg_stat_activity
         WHERE datname = 'giro_qualidade' AND pid <> pg_backend_pid()
    """, dsn=dsn_admin)
    psql("-d", "postgres", "-c", "DROP DATABASE IF EXISTS giro_qualidade",
         dsn=dsn_admin)
    psql("-d", "postgres", "-c",
         "CREATE DATABASE giro_qualidade WITH ENCODING 'UTF8' TEMPLATE template0",
         dsn=dsn_admin)
    psql("-f", str(RAIZ / "db" / "build.sql"), dsn=dsn_q)
    ok("schema aplicado no banco de qualidade")

    passo("carregando dataset SUJO (as rejeicoes vao para quarentena)")
    with psycopg.connect(dsn_q) as conn:
        ing = Ingestor(conn, sujo)
        resultados = ing.executar_tudo()
    _imprimir_carga(resultados)

    (RAIZ / "docs" / "evidencias" / "carga_suja.json").write_text(
        json.dumps([r.como_dict() for r in resultados],
                   ensure_ascii=False, indent=2), encoding="utf-8")

    passo("cruzando gabarito com a quarentena")
    gabarito = json.loads((sujo / "_gabarito.json").read_text(encoding="utf-8"))
    with psycopg.connect(dsn_q) as conn:
        metricas = analisar(conn, gabarito)

    destino = RAIZ / "docs" / "evidencias" / "metricas_qualidade.json"
    destino.write_text(json.dumps(metricas, ensure_ascii=False, indent=2),
                       encoding="utf-8")

    print()
    print(f"  {'REGRA':<7} {'TABELA':<22} {'INJ':>7} {'REJ':>7} "
          f"{'RECALL':>8} {'PREC':>7} {'F1':>6}")
    print("  " + "-" * 76)
    for m in metricas["por_regra"]:
        print(f"  {m['regra']:<7} {m['tabela']:<22} {m['injetados']:>7,} "
              f"{m['rejeitados']:>7,} {m['recall_pct']:>7.1f}% "
              f"{m['precisao_pct']:>6.1f}% {m['f1_pct']:>5.1f}")

    r = metricas["resumo"]
    print("  " + "-" * 76)
    ok(f"recall global {r['recall_global_pct']}% "
       f"({r['registros_detectados']:,}/{r['registros_injetados']:,} registros)")
    ok(f"evidencia: {destino.relative_to(RAIZ)}")


def etapa_gerar_somente(escala: str = "padrao") -> None:
    """Gera os CSVs e o dataset sujo sem carregar no banco."""
    from src.gerador import ESCALAS, gerar
    from src.injetor_defeitos import injetar

    titulo("Geracao de dados (sem carga)")
    bronze = RAIZ / "data" / "bronze"
    limpo = bronze / "limpo"
    sujo = bronze / "sujo"

    passo(f"gerando dataset '{escala}'")
    t0 = time.time()
    resumo = gerar(ESCALAS[escala], limpo, verbose=True)
    ok(f"gerado em {time.time() - t0:.1f}s")

    (bronze / "_resumo_geracao.json").write_text(
        json.dumps(resumo.como_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8")

    passo("injetando defeitos")
    gab = injetar(limpo, sujo)
    n = sum(len(v) for v in gab.registros.values())
    ok(f"{len(gab.defeitos)} tipos, {n:,} registros corrompidos")


def _imprimir_carga(resultados) -> None:
    print()
    print(f"  {'TABELA':<24} {'LIDAS':>10} {'ACEITAS':>10} "
          f"{'REJ':>8} {'ACEITE':>8} {'TEMPO':>8} {'LIN/S':>10}")
    print("  " + "-" * 84)
    for r in resultados:
        print(f"  {r.tabela:<24} {r.lidas:>10,} {r.aceitas:>10,} "
              f"{r.rejeitadas:>8,} {r.taxa_aceite:>7.2f}% "
              f"{r.segundos:>7.1f}s {r.linhas_por_segundo:>10,.0f}")
    total_s = sum(r.segundos for r in resultados)
    total_n = sum(r.lidas for r in resultados)
    print("  " + "-" * 84)
    print(f"  {'TOTAL':<24} {total_n:>10,} "
          f"{sum(r.aceitas for r in resultados):>10,} "
          f"{sum(r.rejeitadas for r in resultados):>8,} "
          f"{'':>8} {total_s:>7.1f}s "
          f"{total_n / total_s if total_s else 0:>10,.0f}")


def etapa_marts() -> None:
    titulo("ETAPA 4/7 - Camada ouro (star schema e views)")
    from src.marts import construir

    with __import__("psycopg").connect(DSN) as conn:
        construir(conn)
    ok("marts materializados")


def etapa_consultas() -> None:
    """Executa as 11 consultas de negocio e exporta as evidencias.

    Esta etapa faltava no fluxo principal: o README prometia que
    `run_all.py --reset` exportava as evidencias, mas o script nunca
    chamava src/consultas.py. Depois de um reset limpo, os arquivos em
    docs/evidencias/ eram saida de uma execucao antiga - ou ausentes.
    Isso ataca diretamente a prova de conceito: o professor abre uma
    evidencia que o comando documentado nao produziu.
    """
    titulo("ETAPA 5/7 - Consultas de negocio")
    from src.consultas import executar_todas
    import psycopg

    with psycopg.connect(DSN) as conn:
        indice = executar_todas(conn, RAIZ)

    erros = [c for c in indice["consultas"] if "erro" in c]
    if erros:
        for e in erros:
            erro(f"{e['numero']} falhou: {e['erro'][:120]}")
        sys.exit(1)
    ok(f"{len(indice['consultas'])} consultas exportadas em docs/evidencias/")


def etapa_painel() -> None:
    """Gera o painel estatico e verifica cada numero contra o banco.

    Duas coisas acontecem aqui, e a segunda e a que importa:
      1. dashboard/gerar.py produz docs/painel.html;
      2. dashboard/verificar.py relê cada valor do HTML e compara com
         uma consulta independente.

    Sem o passo 2, "o painel mostra o dado do banco" seria promessa.
    Com ele, e teste que falha quando alguem muda a consulta e esquece
    de regerar.
    """
    titulo("ETAPA 6/7 - Painel estatico")
    falhas = 0

    passo("gerando docs/painel.html")
    r = subprocess.run([sys.executable, str(RAIZ / "dashboard" / "gerar.py")],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=RAIZ,
                       env={**os.environ, "GIRO_DSN": DSN})
    if r.returncode != 0:
        erro(f"geracao falhou: {r.stderr.strip()[:400]}")
        sys.exit(1)
    for linha in r.stdout.strip().splitlines()[-4:]:
        print(f"    {linha}")

    painel = RAIZ / "docs" / "painel.html"
    kb = painel.stat().st_size / 1024
    ok(f"painel gerado ({kb:.0f} KB, arquivo unico, abre offline)")

    passo("conferindo cada numero do painel contra o banco")
    r = subprocess.run([sys.executable, str(RAIZ / "dashboard" / "verificar.py")],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=RAIZ,
                       env={**os.environ, "GIRO_DSN": DSN})
    saida = r.stdout.strip().splitlines()
    for linha in saida[-6:]:
        print(f"    {linha}")
    if r.returncode != 0:
        falhas += 1
        erro("divergencia entre painel e banco")
    else:
        aprovados = sum(1 for l in saida if " ok " in l)
        ok(f"{aprovados} verificacoes painel x banco aprovadas")

    # Runtime do painel: sintaxe valida nao garante que a pagina funciona.
    # Um erro como `esc is not defined` passa pelo node --check e quebra a
    # renderizacao inteira. Este passo abre o HTML num browser de verdade.
    node = subprocess.run(["node", "--version"], capture_output=True, text=True)
    if node.returncode == 0:
        passo("verificando o painel em runtime (browser)")
        r = subprocess.run(
            ["node", str(RAIZ / "scripts" / "verificar_painel.js")],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", cwd=RAIZ)
        for linha in r.stdout.strip().splitlines()[-4:]:
            print(f"    {linha}")
        if r.returncode != 0:
            falhas += 1
            erro("painel falhou na verificacao em runtime")
        else:
            ok("painel renderiza, imprime e passa acessibilidade")

        # Gate de confianca: o relatorio promete que, abaixo de 85% na
        # pior dimensao, a sugestao e bloqueada. Sem este teste, a
        # promessa era so texto.
        passo("testando o bloqueio por baixa confianca")
        r = subprocess.run(
            ["node", str(RAIZ / "scripts" / "testar_gate_confianca.js")],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", cwd=RAIZ)
        for linha in r.stdout.strip().splitlines()[-4:]:
            print(f"    {linha}")
        if r.returncode != 0:
            falhas += 1
            erro("gate de confianca nao bloqueia a sugestao")
        else:
            ok("loja abaixo de 85% tem a sugestao bloqueada")

    # PDFs entregues: procura afirmacoes que a documentacao ja corrigiu.
    # O relatorio e um retrato do estado; numero velho impresso no PDF
    # desmente o markdown atual e nao aparece em nenhum teste.
    if (RAIZ / "docs" / "relatorio-final.pdf").exists():
        passo("conferindo se o PDF entregue tem afirmacao obsoleta")
        r = subprocess.run(
            [sys.executable, str(RAIZ / "scripts" / "conferir_pdf_obsoleto.py")],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", cwd=RAIZ)
        for linha in r.stdout.strip().splitlines()[-3:]:
            print(f"    {linha}")
        if "0 afirmacao" not in r.stdout:
            falhas += 1
            erro("o PDF entregue tem numero que o texto ja corrigiu")
        else:
            ok("PDF sem afirmacao obsoleta")
    else:
        aviso("node nao encontrado; verificacao de runtime do painel pulada")

    if falhas:
        sys.exit(1)


def etapa_testes() -> None:
    titulo("ETAPA 7/7 - Validacao")
    falhas = 0

    passo("constraints do modelo OLTP")
    r = subprocess.run([sys.executable, str(RAIZ / "tests" / "test_constraints.py")],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=RAIZ,
                       env={**os.environ, "GIRO_DSN": DSN})
    print(r.stdout)
    if r.returncode != 0:
        falhas += 1

    passo("integridade dos dados carregados")
    r = subprocess.run([sys.executable, str(RAIZ / "tests" / "test_integridade.py")],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=RAIZ,
                       env={**os.environ, "GIRO_DSN": DSN})
    print(r.stdout)
    if r.returncode != 0:
        falhas += 1

    if falhas:
        erro(f"{falhas} suite(s) falharam")
        sys.exit(1)
    ok("todas as suites passaram")


# =====================================================================
# Main
# =====================================================================

def main() -> int:
    ap = argparse.ArgumentParser(description="Orquestrador do projeto Giro")
    ap.add_argument("--reset", action="store_true",
                    help="recria o banco do zero antes de rodar")
    ap.add_argument("--etapa",
                    choices=["db", "dados", "sujo", "marts", "consultas",
                             "painel", "testes"],
                    help="executa apenas esta etapa")
    ap.add_argument("--escala", default="padrao",
                    choices=["rapida", "padrao", "completa"],
                    help="escala do dataset sintetico")
    ap.add_argument("--pular-geracao", action="store_true",
                    help="reaproveita os CSVs ja gerados em data/bronze")
    args = ap.parse_args()

    t0 = time.time()

    if args.reset:
        garantir_servico()
        recriar_banco()

    if args.etapa == "db":
        etapa_db()
    elif args.etapa == "dados":
        etapa_db()
        etapa_dados(args.escala)
    elif args.etapa == "sujo":
        etapa_sujo()
    elif args.etapa == "marts":
        etapa_marts()
    elif args.etapa == "consultas":
        etapa_consultas()
    elif args.etapa == "painel":
        etapa_painel()
    elif args.etapa == "testes":
        etapa_testes()
    else:
        etapa_db()
        if args.pular_geracao:
            # Reaproveita os CSVs; ainda injeta defeitos se faltarem
            if not (RAIZ / "data" / "bronze" / "sujo" / "_gabarito.json").exists():
                etapa_gerar_somente(args.escala)
            else:
                aviso("reaproveitando CSVs existentes em data/bronze")
            etapa_dados(args.escala, pular_geracao=True)
        else:
            etapa_dados(args.escala)
        etapa_sujo()
        etapa_marts()
        etapa_consultas()
        etapa_painel()
        etapa_testes()

    titulo(f"CONCLUIDO em {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
