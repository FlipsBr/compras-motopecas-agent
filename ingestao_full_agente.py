import os
import glob
import json
import sqlite3
import pandas as pd
import ollama

def criar_banco_normalizado():
    conn = sqlite3.connect("memoria_fornecedores.db")
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS tabelas_normalizadas_ia")
    cursor.execute("""
        CREATE TABLE tabelas_normalizadas_ia (
            fornecedor TEXT,
            codigo TEXT,
            descricao TEXT,
            aplicacao TEXT,
            ano TEXT,
            preco REAL
        )
    """)
    return conn, cursor

def analisar_tabela_com_ia(nome_fornecedor, colunas, amostra_dados):
    """(Fase 1) Mapeia as colunas, igual fazíamos antes."""
    prompt = f"""
    Eu tenho uma tabela de peças de moto do fornecedor '{nome_fornecedor}'.
    Colunas: {colunas}
    Amostra: {amostra_dados}
    
    Retorne um JSON com as chaves exatas: "coluna_descricao", "coluna_aplicacao", "coluna_preco", "coluna_codigo", "coluna_ano".
    Se a coluna não existir, use null.
    """
    resposta = ollama.chat(model='qwen2.5:14b', messages=[{'role': 'user', 'content': prompt}], format='json',options={'num_ctx': 4096})
    return json.loads(resposta['message']['content'])

def limpar_lote_com_ia(lote_dados, nome_fornecedor):
    """(Fase 2) O verdadeiro processamento Agêntico. A IA limpa os dados usando regras estritas."""
    
    # 🧠 INJEÇÃO DE CONHECIMENTO (PEÇAS E MOTOS)
    dicionario_negocio = """
    === 1. DICIONÁRIO DE PADRONIZAÇÃO DE PEÇAS (De -> Para) ===
    - "FR" ou "F" -> "FREIO"
    - "DIR" -> "DIREITO"
    - "ESQ" -> "ESQUERDO"
    - "PT" -> "PRETO"
    - "UND" ou "UN" -> REMOVER COMPLETAMENTE
    - "ANEL T" -> "ANEL TAMPA"
    - "TRAS" ou "T" -> "TRASEIRO"
    - "DIANT" ou "D" -> "DIANTEIRO"
    - "C/" -> "COM"
    - "S/" -> "SEM"
    - "ARVORE COM" -> "ARVORE COMANDO"
    - "CAR INT" -> "CARENAGEM INTERNA"
    - "QUADRI" -> "QUADRICICLO"
    - "SEG" -> "SEGMENTO"
    - "PAD" ou "PASTIL" -> "PASTILHA"
    - "AMORT" -> "AMORTECEDOR"
    - "CAB" -> "CABO"
    - "ACEL" -> "ACELERADOR"
    - "EMB" ou "EMBREAG" -> "EMBREAGEM"
    - "RET" ou "RETENT" -> "RETENTOR"
    - "ROL" ou "ROLAM" -> "ROLAMENTO"
    - "IRON" -> REMOVER COMPLETAMENTE
    - "IRO" -> REMOVER COMPLETAMENTE
    - "IRON PREMIUM" -> REMOVER COMPLETAMENTE
    
    === 2. CATÁLOGO DE MOTOS CONHECIDAS (Para guiar a extração da 'aplicacao') ===
    Famílias Honda: CG, TITAN, FAN, START, CARGO, CB, CBX, NXR, BROS, XRE, BIZ, POP, SH, LEAD, PCX, TRX, NX, FALCON, XR, TORNADO, XLR, SAHARA, HORNET.
    Famílias Yamaha: YBR, XTZ, FAZER, FZ25, YS, CRYPTON, NEO, NMAX, LANDER.
    Outras (Suzuki/Shineray): YES, BURGMAN, AN 125, JET, PHOENIX, SHINERAY 50.
    
    Regras de Extração de Aplicação:
    - ATENÇÃO AOS COMBOS MISTOS: Se encontrar motos diferentes separadas por barra, extraia TUDO JUNTO para a aplicação.
      Exemplos de combos reais: "BIZ/POP 100", "CBX/XR 250/CB/XRE 300", "CB 300F/SAHARA 300", "XLR/NX/XR 200", "NX/200/250/XLR 125", "NXR 150/160/XRE 190".
    - ATENÇÃO AOS SUFIXOS: Preserve letras e nomes que acompanham os números. 
      Exemplos: "BIZ 110I", "CG 160 START", "AN 125 BURGMAN", "JET 50X", "XTZ 250 LANDER".
    - A descrição NÃO DEVE conter o nome da moto. Mova tudo referente à moto para 'aplicacao'.
    """

    prompt = f"""Você é um Engenheiro de Dados especialista em moto peças. Sua missão é limpar e padronizar as tabelas.
    
    Você DEVE obedecer ESTRITAMENTE a estas regras de negócio fornecidas pela empresa:
    {dicionario_negocio}
    
    Para cada peça na lista bruta abaixo, você deve:
    1. 'descricao': Deixar APENAS o nome da peça (aplicando o Dicionário de Padronização).
    2. 'aplicacao': Extrair os modelos/combos das motos guiando-se pelo Catálogo.
    3. 'ano': Extrair o ano da moto no formato YY/YY (ex: "14/15"). Se não tiver, retorne "".
    
    Lista de entrada bruta:
    {json.dumps(lote_dados, ensure_ascii=False)}
    
    Retorne APENAS um JSON válido estritamente neste formato, sem explicações:
    {{
      "pecas_limpas": [
        {{ "id_linha": ID, "descricao": "...", "aplicacao": "...", "ano": "..." }}
      ]
    }}
    """
    
    try:
        print(f"   🤖 Processando lote de {len(lote_dados)} peças do fornecedor {nome_fornecedor} com IA orientada a catálogo...")
        resposta = ollama.chat(
            model='qwen2.5:14b',
            messages=[{'role': 'user', 'content': prompt}],
            format='json'
        )
        return json.loads(resposta['message']['content']).get('pecas_limpas', [])
    except Exception as e:
        print(f"❌ Erro ao processar lote: {e}")
        return []

    
def executar_ingestao_full_ia():
    conn, cursor = criar_banco_normalizado()
    arquivos = glob.glob("tabelas_de_entrada/*.csv") + glob.glob("tabelas_de_entrada/*.xlsx")
    
    for arquivo in arquivos:
        fornecedor = os.path.basename(arquivo).split('.')[0]
        df = pd.read_csv(arquivo) if arquivo.endswith('.csv') else pd.read_excel(arquivo)
        df = df.fillna("")
        tamanho_lote = 20
        # ⚠️ LIMITADOR PARA TESTE: Pega apenas as primeiras 50 linhas para você não ficar horas esperando
        df = df.head(500)
        
        colunas_originais = list(df.columns)
        amostra = df.head(tamanho_lote).to_dict(orient='records')
        
        # Passo 1: Descobre quem é quem
        mapa = analisar_tabela_com_ia(fornecedor, colunas_originais, amostra)
        if not mapa: continue
        
        print(f"✅ Mapeamento do Fornecedor {fornecedor} concluído!")
        
        def validar_coluna(chave):
            print(f"Validando coluna {chave}...")
            val = mapa.get(chave)
            return val if val and str(val).lower() not in ['null', 'none', ''] and val in df.columns else None

        col_desc = validar_coluna('coluna_descricao')
        col_app = validar_coluna('coluna_aplicacao')
        col_ano = validar_coluna('coluna_ano')
        col_codigo = validar_coluna('coluna_codigo')
        col_preco = validar_coluna('coluna_preco')
        
        if not col_desc:
            print("Sem coluna de descrição, pulando...")
            continue
            
        dados_finais = []

        
        # Passo 2: Loop Agêntico (Lote por Lote)
        for i in range(0, len(df), tamanho_lote):
            lote_bruto = []
            lote_df = df.iloc[i:i+tamanho_lote]
            
            for index, row in lote_df.iterrows():
                lote_bruto.append({
                    "id_linha": index,
                    "desc_bruta": str(row[col_desc]),
                    "app_bruta": str(row[col_app]) if col_app else "",
                    "ano_bruto": str(row[col_ano]) if col_ano else ""
                })
                
            # Chama a IA para limpar essas 10 linhas
            pecas_limpas = limpar_lote_com_ia(lote_bruto, fornecedor)
            
            # Junta com os dados que a IA não precisava limpar (codigo e preço)
            for peca in pecas_limpas:
                id_linha = peca.get('id_linha')
                row_original = df.loc[id_linha]
                
                preco_bruto = str(row_original[col_preco]) if col_preco else "0"
                # Limpeza simples de número com python pra garantir
                import re
                preco_limpo = re.sub(r'[^\d.,]', '', preco_bruto).replace(',', '.')
                
                dados_finais.append({
                    "fornecedor": fornecedor,
                    "codigo": str(row_original[col_codigo]) if col_codigo else "Desconhecido",
                    "descricao": peca.get('descricao', ''),
                    "aplicacao": peca.get('aplicacao', ''),
                    "ano": peca.get('ano', ''),
                    "preco": float(preco_limpo) if preco_limpo else 0.0
                })

        # Salva no banco de dados
        df_final = pd.DataFrame(dados_finais)
        df_final.to_sql('tabelas_normalizadas_ia', conn, if_exists='append', index=False)
        print(f"💾 {len(df_final)} peças de {fornecedor} salvas usando Agente IA!\n" + "-"*40)

    conn.commit()
    print("🚀 Teste Agentico Finalizado!")

if __name__ == "__main__":
    executar_ingestao_full_ia()