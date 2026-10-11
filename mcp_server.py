import csv
from glob import glob
import logging
import os
import re
import sqlite3
from typing import List, Dict, Any, Optional
import pandas as pd
from pydantic import BaseModel, Field
from mcp.server.fastmcp import FastMCP

# stdout é reservado para o protocolo JSON-RPC do transporte stdio; logs devem ir para stderr
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("mcp_server")

# Inicializa o MCP Server
mcp = FastMCP("MotopecasProcurementServer")

# Diretório de saída para os CSVs individualizados por fornecedor
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "pedidos_gerados")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# =====================================================================
# 1. GUARDRAIL DE ENTRADA (Pré-sanitização e Filtro de Idioma/Injeção)
# =====================================================================
PALAVRAS_PROIBIDAS = [
    "ignore", "system prompt", "esqueça as regras", "disregard",
    "bypass", "compre tudo", "drop table", "delete from", "override"
]

def sanitizar_texto(texto: str) -> str:
    texto_lower = texto.lower()
    for proibida in PALAVRAS_PROIBIDAS:
        if proibida in texto_lower:
            raise ValueError(f"Alerta de Guardrail: Termo proibido detectado ('{proibida}').")
    
    # Verificação heurística contra injeção em alfabetos não-latinos/estrangeiros
    if re.search(r"[\u0400-\u04FF\u4E00-\u9FFF]", texto):
        raise ValueError("Alerta de Guardrail: Tentativa de injeção em idioma não suportado.")
    return texto.strip()

# =====================================================================
# 2. BANCO DE DADOS SQL (Agentic RAG) + MEMÓRIA SEMÂNTICA
# =====================================================================

# 1. Conexão com o Banco de Dados Normalizado
def obter_conexao():
    return sqlite3.connect("memoria_fornecedores.db")

# Palavras sem valor de busca que só tornam o filtro AND mais restritivo sem ajudar na relevância
STOPWORDS_BUSCA = {
    "de", "da", "do", "das", "dos", "e", "a", "o", "em", "com", "sem", "para", "pra", "ao", "aos"
}

def garantir_indice_fts(conn: sqlite3.Connection) -> None:
    """Cria e popula, uma única vez, o índice FTS5 usado pela busca lexical (evita LIKE '%...%' em full scan)."""
    cursor = conn.cursor()
    existe = cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='tabelas_normalizadas_fts'"
    ).fetchone()
    if existe:
        return

    cursor.execute("""
        CREATE VIRTUAL TABLE tabelas_normalizadas_fts USING fts5(
            descricao, aplicacao,
            fornecedor UNINDEXED, preco UNINDEXED, ano UNINDEXED, codigo UNINDEXED
        )
    """)
    cursor.execute("""
        INSERT INTO tabelas_normalizadas_fts (descricao, aplicacao, fornecedor, preco, ano, codigo)
        SELECT descricao, aplicacao, fornecedor, preco, ano, codigo FROM tabelas_normalizadas_ia
    """)
    conn.commit()

def inicializar_bd() -> sqlite3.Connection:
    conn = sqlite3.connect("memoria_fornecedores.db")
    cursor = conn.cursor()
    
    # Cria uma tabela genérica para receber dados não normalizados
    cursor.execute("DROP TABLE IF EXISTS tabelas_raw")
    cursor.execute("""
        CREATE TABLE tabelas_raw (
            fornecedor TEXT,
            texto_busca TEXT,
            dados_brutos TEXT
        )
    """)
    
    diretorio_entrada = os.path.join(os.path.dirname(__file__), "tabelas_de_entrada")
    os.makedirs(diretorio_entrada, exist_ok=True)
    
    arquivos = glob(os.path.join(diretorio_entrada, "*.csv")) + glob(os.path.join(diretorio_entrada, "*.xlsx"))
    
    for arquivo in arquivos:
        try:
            nome_fornecedor = os.path.basename(arquivo).split('.')[0]
            df = pd.read_csv(arquivo) if arquivo.endswith('.csv') else pd.read_excel(arquivo)
            
            # Preenche campos vazios e converte tudo para string para facilitar a busca
            df = df.fillna('')
            
            # Cria uma coluna fundindo todo o texto da linha (para busca léxica SQL)
            df['texto_busca'] = df.astype(str).agg(' '.join, axis=1).str.lower()
            
            # Converte a linha inteira em um objeto JSON bruto (não normalizado)
            df['dados_brutos'] = df.apply(lambda row: row.drop('texto_busca').to_json(), axis=1)
            df['fornecedor'] = nome_fornecedor
            
            # Salva no banco de dados
            df[['fornecedor', 'texto_busca', 'dados_brutos']].to_sql('tabelas_raw', conn, if_exists='append', index=False)
            logger.info("✅ Tabela não normalizada importada: %s (%d itens)", nome_fornecedor, len(df))
            
        except Exception as e:
            logger.error("❌ Erro ao importar %s: %s", arquivo, e)

    conn.commit()
    return conn

DB_CONN = inicializar_bd()


# =====================================================================
# 3. FUNÇÃO DE INICIALIZAÇÃO DO BANCO DE DADOS DE TESTE
# =====================================================================
def inicializar_bd_test() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()
    
    # Memória Semântica: Fatos estruturados de intercambialidade de peças
    cursor.execute("""
        CREATE TABLE memoria_semantica (
            sku_canonico TEXT,
            termo_busca TEXT,
            descricao_padrao TEXT
        )
    """)
    equivalencias = [
        ("SKU-VELA-DP8", "vela ngk dp8ea-9", "Vela de Ignição NGK DP8EA-9"),
        ("SKU-VELA-DP8", "vela ignicao dp8ea9 titan 150", "Vela de Ignição NGK DP8EA-9"),
        ("SKU-CABO-CG150", "cabo do acelerador de cg150", "Cabo Acelerador Honda CG 150"),
        ("SKU-CABO-CG150", "cabo acel titan 150", "Cabo Acelerador Honda CG 150"),
        ("SKU-PAST-CB300", "pastilhas de freio aplicáveis a cb300 até ano 2010", "Pastilha Freio Diant. CB300 s/ ABS (até 2010)"),
        ("SKU-PAST-CB300", "pastilha freio cb300", "Pastilha Freio Diant. CB300 s/ ABS (até 2010)"),
    ]
    cursor.executemany("INSERT INTO memoria_semantica VALUES (?, ?, ?)", equivalencias)

    # Tabelas dos N Fornecedores (Contendo colunas extras como NCM e Peso que serão comprimidas)
    cursor.execute("""
        CREATE TABLE tabelas_fornecedores (
            fornecedor TEXT,
            sku_canonico TEXT,
            descricao_fornecedor TEXT,
            preco_unitario REAL,
            ncm TEXT,
            peso_kg REAL
        )
    """)
    dados_fornecedores = [
        # Vela NGK DP8EA-9 (Fornecedor B é o mais barato: R$ 17.50)
        ("Fornecedor_A", "SKU-VELA-DP8", "Vela NGK DP8EA-9 Original", 19.90, "8511.10.00", 0.04),
        ("Fornecedor_B", "SKU-VELA-DP8", "Vela Ign. DP8EA9 NGK", 17.50, "8511.10.00", 0.04),
        ("Fornecedor_C", "SKU-VELA-DP8", "Vela Moto NGK DP8EA-9", 21.00, "8511.10.00", 0.04),
        # Cabo Acelerador CG150 (Fornecedor A é o mais barato: R$ 11.20)
        ("Fornecedor_A", "SKU-CABO-CG150", "Cabo Acel. CG 150 Titan", 11.20, "8714.10.00", 0.15),
        ("Fornecedor_B", "SKU-CABO-CG150", "Cabo do Acelerador CG150", 13.00, "8714.10.00", 0.15),
        ("Fornecedor_D", "SKU-CABO-CG150", "Cabo Comando Acel. Titan 150", 12.50, "8714.10.00", 0.15),
        # Pastilha CB300 até 2010 (Fornecedor C é o mais barato: R$ 28.00)
        ("Fornecedor_A", "SKU-PAST-CB300", "Jogo Pastilha CB300 2009/2010", 32.00, "8714.10.00", 0.22),
        ("Fornecedor_C", "SKU-PAST-CB300", "Past. Freio CB 300 S/ABS ate 10", 28.00, "8714.10.00", 0.22),
        ("Fornecedor_D", "SKU-PAST-CB300", "Pastilha Diant CB300 2010", 29.90, "8714.10.00", 0.22),
    ]
    cursor.executemany("INSERT INTO tabelas_fornecedores VALUES (?, ?, ?, ?, ?, ?)", dados_fornecedores)
    conn.commit()
    return conn


# =====================================================================
# 3. FERRAMENTAS MCP (Com descrição orientada por JSON Schema)
# =====================================================================
class ItemPedidoInput(BaseModel):
    fornecedor: str = Field(..., description="Nome exato do fornecedor vencedor (ex: Fornecedor_A)")
    item: str = Field(..., description="Descrição padronizada ou SKU da peça cotada")
    codigo: Optional[str] = Field(None, description="Código do fornecedor para a peça")
    quantidade: int = Field(..., gt=0, description="Quantidade solicitada pelo comprador")
    preco_unitario: float = Field(..., gt=0, description="Menor preço unitário validado pelo agente")
    aplicacao: str = Field(..., description="Aplicação ou compatibilidade da peça (ex: CB300 até 2010)")
    ano: Optional[str] = Field(None, description="Ano ou intervalo de anos de fabricação da moto (ex: '16/22'), quando disponível")

@mcp.tool(
    name="consultar_tabela_precos_desenvolvimento",
    description=(
        "Ferramenta de busca híbrida (SQL + equivalência semântica). "
        "Recebe uma lista de peças e retorna um JSON comprimido e deduplicado "
        "contendo apenas {fornecedor, preco_unitario} para cada item encontrado."
    )
)



@mcp.tool(
    name="consultar_tabela_precos",
    description="Busca itens estruturados no banco de dados normalizado. Retorna {fornecedor, descricao, aplicacao, preco, ano e codigo}."
)
def consultar_tabela_precos(item_busca: str) -> Dict[str, Any]:
    conn = obter_conexao()
    garantir_indice_fts(conn)
    cursor = conn.cursor()

    # Quebra a busca em palavras-chave, descartando stopwords e caracteres que quebrariam a sintaxe do FTS5
    termos_brutos = item_busca.lower().split()
    termos = [t for t in termos_brutos if t not in STOPWORDS_BUSCA] or termos_brutos
    termos_fts = [tok for t in termos if (tok := re.sub(r"[^a-z0-9À-ú]", "", t))]

    if not termos_fts:
        return {"termo_buscado": item_busca, "ofertas_encontradas": []}

    # Prefix match (termo*) tolera variações de plural/sufixo; OR garante recall mesmo quando
    # a descrição não contém literalmente todos os termos (ex: "CBX250" vs "CBX/CB 250/300")
    consulta_fts = " OR ".join(f'{t}*' for t in termos_fts)

    query = """
        SELECT fornecedor, descricao, aplicacao, preco, ano, codigo,
               bm25(tabelas_normalizadas_fts, 1.0, 3.0) AS relevancia
        FROM tabelas_normalizadas_fts
        WHERE tabelas_normalizadas_fts MATCH ?
        ORDER BY relevancia ASC, preco ASC
        LIMIT 10
    """

    logger.info("Executing FTS query: %s with match expression: %s", query, consulta_fts)

    cursor.execute(query, (consulta_fts,))
    
    resultados = []
    for row in cursor.fetchall():
        resultados.append({
            "fornecedor": row[0],
            "descricao": row[1],
            "aplicacao": row[2],
            "preco": round(row[3], 2) if row[3] else 0.0,
            "ano": row[4] or None,
            "codigo": row[5]
        })
        
    conn.close()
    return {"termo_buscado": item_busca, "ofertas_encontradas": resultados}

# Ferramenta de consulta de tabela de preços para ambiente de teste
def consultar_tabela_precos_desenvolvimento(itens: List[str]) -> Dict[str, Any]:
    cursor = DB_CONN.cursor()
    resultado_comprimido = {}

    for item_bruto in itens:
        item_limpo = sanitizar_texto(item_bruto).lower()
        
        # 1. Busca Híbrida: Resolve equivalência na Memória Semântica
        cursor.execute("""
            SELECT DISTINCT sku_canonico, descricao_padrao 
            FROM memoria_semantica 
            WHERE ? LIKE '%' || termo_busca || '%' OR termo_busca LIKE '%' || ? || '%'
        """, (item_limpo, item_limpo))
        match_semantico = cursor.fetchone()

        if not match_semantico:
            # Regra da Memória Procedural: Não retornar dados se não achar SKU correspondente
            resultado_comprimido[item_bruto] = {"status": "SKU_NAO_ENCONTRADO", "ofertas": []}
            continue

        sku_canonico, desc_padrao = match_semantico

        # 2. Context Engineering: Seleção (MMR por fornecedor) + Compressão (ignora NCM e Peso)
        cursor.execute("""
            SELECT fornecedor, MIN(preco_unitario) as menor_preco_fornecedor
            FROM tabelas_fornecedores
            WHERE sku_canonico = ?
            GROUP BY fornecedor
            ORDER BY menor_preco_fornecedor ASC
        """, (sku_canonico,))
        
        ofertas = [
            {"fornecedor": row[0], "preco_unitario": round(row[1], 2)}
            for row in cursor.fetchall()
        ]

        resultado_comprimido[item_bruto] = {
            "sku_canonico": sku_canonico,
            "descricao_padrao": desc_padrao,
            "ofertas": ofertas
        }

    return resultado_comprimido


@mcp.tool(
    name="escrever_pedido_compra",
    description=(
        "Ferramenta de escrita transacional. Recebe uma lista validada de itens (em lote ou unitária) "
        "e grava linhas no arquivo CSV exclusivo de cada fornecedor com o valor total calculado."
    )
)
def escrever_pedido_compra(itens_aprovados: List[ItemPedidoInput]) -> Dict[str, Any]:
    arquivos_atualizados = []

    for pedido in itens_aprovados:
        fornecedor_limpo = re.sub(r"[^a-zA-Z0-9_-]", "", pedido.fornecedor)
        caminho_csv = os.path.join(OUTPUT_DIR, f"pedido_{fornecedor_limpo}.csv")
        arquivo_existe = os.path.isfile(caminho_csv)
        valor_total_linha = round(pedido.quantidade * pedido.preco_unitario, 2)

        with open(caminho_csv, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if not arquivo_existe:
                writer.writerow(["fornecedor", "item", "codigo", "quantidade", "preco_unitario", "valor_total"])
            writer.writerow([
                pedido.fornecedor,
                pedido.item,
                pedido.codigo or "",
                pedido.quantidade,
                f"{pedido.preco_unitario:.2f}",
                f"{valor_total_linha:.2f}"
            ])
        
        if caminho_csv not in arquivos_atualizados:
            arquivos_atualizados.append(caminho_csv)

    return {
        "status": "SUCESSO",
        "itens_gravados": len(itens_aprovados),
        "arquivos_csv_gerados": arquivos_atualizados,
        "status_hitl": "AGUARDANDO_CONFERENCIA_HUMANA_FINAL"
    }

if __name__ == "__main__":
    mcp.run()




