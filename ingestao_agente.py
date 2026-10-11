import os
import glob
import json
import sqlite3
import pandas as pd
import ollama
import re

# Importa os dicionários do arquivo externo
from regras_normalizacao import PADROES_MOTOS, MAPEAMENTO_TERMOS, PADROES_ANOS

def criar_banco_normalizado():
    conn = sqlite3.connect("memoria_fornecedores.db")
    cursor = conn.cursor()
    # Cria a tabela definitiva e normalizada
    cursor.execute("DROP TABLE IF EXISTS tabelas_normalizadas")
    cursor.execute("""
        CREATE TABLE tabelas_normalizadas (
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
    """Usa o Qwen2.5 local para mapear as colunas bagunçadas para o padrão"""
    
    prompt = f"""Você é um Engenheiro de Dados.
    Eu tenho uma tabela de peças de moto do fornecedor '{nome_fornecedor}'.
    As colunas disponíveis nesta tabela são: {colunas}
    
    Aqui estão as 3 primeiras linhas de exemplo:
    {amostra_dados}
    
    Sua tarefa é identificar quais colunas originais correspondem aos seguintes campos padronizados:
    1. 'descricao' (nome do produto)
    2. 'aplicacao' (modelos de moto que a peça serve)
    3. 'preco' (valor numérico)
    4. 'codigo' (código ou SKU)
    5. 'ano' (coluna com o ano da moto. Se não houver coluna exclusiva para ano, retorne null)
    
    Responda APENAS com um JSON válido com as chaves exatas: "coluna_descricao", "coluna_aplicacao", "coluna_preco", "coluna_codigo", "coluna_ano".
    """

    print(f"🧠 Agente analisando a estrutura do fornecedor: {nome_fornecedor}...")
    resposta = ollama.chat(
        model='qwen2.5:14b',
        messages=[{'role': 'user', 'content': prompt}],
        format='json' # Força o modelo a retornar um JSON perfeito
    )
    
    try:
        mapeamento = json.loads(resposta['message']['content'])
        return mapeamento
    except Exception as e:
        print(f"❌ Erro ao entender o JSON da LLM: {e}")
        return None


def extrair_ano(texto_original):
    """Procura o ano na string, extrai no formato YY/YY e remove da string original."""
    if not isinstance(texto_original, str):
        return texto_original, ""
        
    texto_limpo = texto_original
    ano_encontrado = ""

    # 1. Tenta achar intervalo (ex: 14/15)
    match_intervalo = re.search(PADROES_ANOS[0], texto_limpo)
    if match_intervalo:
        ano_encontrado = f"{match_intervalo.group(1)}/{match_intervalo.group(2)}"
        texto_limpo = re.sub(PADROES_ANOS[0], '', texto_limpo).strip()
        return texto_limpo, ano_encontrado
    
    # 2. Tenta achar ano isolado (ex: 2014)
    match_isolado = re.search(PADROES_ANOS[1], texto_limpo)
    if match_isolado:
        ano_completo = match_isolado.group(1)
        ano_encontrado = ano_completo[-2:] # Pega só os 2 últimos dígitos (ex: 14)
        texto_limpo = re.sub(PADROES_ANOS[1], '', texto_limpo).strip()

    # Remove barras ou traços soltos que podem ter sobrado
    texto_limpo = re.sub(r'(?:/|-)\s*$', '', texto_limpo).strip()
    return texto_limpo, ano_encontrado








def executar_ingestao():
    conn, cursor = criar_banco_normalizado()
    diretorio = "tabelas_de_entrada"
    arquivos = glob.glob(f"{diretorio}/*.csv") + glob.glob(f"{diretorio}/*.xlsx")
    
    if not arquivos:
        print("Nenhuma tabela encontrada na pasta de entrada.")
        return

    for arquivo in arquivos:
        fornecedor = os.path.basename(arquivo).split('.')[0]
        
        # Carrega a tabela bruta (lida com CSV ou Excel)
        df = pd.read_csv(arquivo) if arquivo.endswith('.csv') else pd.read_excel(arquivo)
        df = df.fillna("")
        
        # Pega as colunas e as 3 primeiras linhas para o Agente analisar
        colunas_originais = list(df.columns)
        amostra = df.head(3).to_dict(orient='records')
        
        # Pede para a IA mapear a tabela
        mapa = analisar_tabela_com_ia(fornecedor, colunas_originais, amostra)
        
        if mapa:
            print(f"✅ Mapeamento concluído: {mapa}")
                
            df_normalizado = pd.DataFrame()
            df_normalizado['fornecedor'] = [fornecedor] * len(df)
            
            def validar_coluna(chave):
                val = mapa.get(chave)
                if not val or str(val).strip().lower() in ['null', 'none', 'falso', 'false', '']:
                    return None
                if val not in df.columns:
                    return None
                return val

            col_desc = validar_coluna('coluna_descricao')
            col_app = validar_coluna('coluna_aplicacao')
            col_preco = validar_coluna('coluna_preco')
            col_ano = validar_coluna('coluna_ano')
            col_codigo = validar_coluna('coluna_codigo')
            col_ano = validar_coluna('coluna_ano')

            df_normalizado['codigo'] = df[col_codigo] if col_codigo else "Desconhecido"
            descricoes_originais = df[col_desc] if col_desc else ["Desconhecido"] * len(df)
            
            novas_descricoes = []
            novas_aplicacoes = []
            novos_anos = []

            for index, desc_orig in enumerate(descricoes_originais):
                app_orig = str(df[col_app].iloc[index]).strip() if col_app else ""
                ano_orig = str(df[col_ano].iloc[index]).strip() if col_ano else ""
                desc = str(desc_orig).strip()
                
                ano_final = ""
                app_final = ""
                
                # --- 1. TRATA O ANO ---
                if ano_orig:
                    _, ano_final = extrair_ano(ano_orig)
                    if not ano_final: ano_final = ano_orig # Fallback se não bater o regex
                
                # Tenta achar ano escondido na aplicacao
                app_sem_ano, ano_na_app = extrair_ano(app_orig)
                if not ano_final and ano_na_app:
                    ano_final = ano_na_app
                app_orig = app_sem_ano
                    
                # Tenta achar ano escondido na descricao
                desc_sem_ano, ano_na_desc = extrair_ano(desc)
                if not ano_final and ano_na_desc:
                    ano_final = ano_na_desc
                desc = desc_sem_ano # Remove o ano da descrição
                
                # --- 2. TRATA A APLICAÇÃO ---
                if app_orig:
                    app_final = app_orig
                else:
                    desc_sem_app, app_na_desc = separar_descricao_aplicacao(desc)
                    app_final = app_na_desc
                    desc = desc_sem_app # Remove a moto da descrição
                    
                # --- 3. PADRONIZA A DESCRIÇÃO FINAL ---
                desc_final = padronizar_descricao(desc)
                
                novas_descricoes.append(desc_final)
                novas_aplicacoes.append(app_final)
                novos_anos.append(ano_final)
            
            # Adiciona as listas limpas ao banco
            df_normalizado['descricao'] = novas_descricoes
            df_normalizado['aplicacao'] = novas_aplicacoes
            df_normalizado['ano'] = novos_anos
                
            # Trata a coluna de preço (mantido igual)
            if col_preco:
                df_normalizado['preco'] = df[col_preco].astype(str).str.replace(r'[^\d.,]', '', regex=True)
                df_normalizado['preco'] = df_normalizado['preco'].str.replace(',', '.')
                df_normalizado['preco'] = pd.to_numeric(df_normalizado['preco'], errors='coerce')
            else:
                df_normalizado['preco'] = 0.0

            df_normalizado.to_sql('tabelas_normalizadas', conn, if_exists='append', index=False)
            print(f"💾 Fornecedor {fornecedor} salvo no banco com sucesso!\n" + "-"*40)

    conn.commit()
    print("🚀 Ingestão Agentica Finalizada! O Banco de Dados está normalizado e pronto para uso.")

import re

def separar_descricao_aplicacao(descricao_original):
    if not isinstance(descricao_original, str):
        return "Desconhecido", ""

    descricao = descricao_original.strip().upper()
    aplicacao_encontrada = ""
    descricao_limpa = descricao
    
    # Consome a lista importada do arquivo externo
    for padrao in PADROES_MOTOS:
        match = re.search(padrao, descricao)
        if match:
            aplicacao_encontrada = match.group(0)
            descricao_limpa = re.sub(padrao, '', descricao).strip()
            descricao_limpa = re.sub(r'(-|/|P/|PARA)\s*$', '', descricao_limpa).strip()
            break

    return descricao_limpa, aplicacao_encontrada

def padronizar_descricao(descricao_limpa):
    if not isinstance(descricao_limpa, str) or descricao_limpa == "":
        return "Desconhecido"

    desc_padronizada = descricao_limpa
    
    # Consome o dicionário importado do arquivo externo
    for padrao, substituto in MAPEAMENTO_TERMOS.items():
        desc_padronizada = re.sub(padrao, substituto, desc_padronizada)

    desc_padronizada = re.sub(r'\s+', ' ', desc_padronizada).strip()

    return desc_padronizada




if __name__ == "__main__":
    executar_ingestao()