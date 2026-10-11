---
name: cotacao-motopecas
description: Realiza cotação autônoma de moto-peças em múltiplos fornecedores via MCP, aplicando Plan-and-Solve, ReAct, Reflexion e geração de CSV individualizado por fornecedor.
---

# Skill: Agente Único de Cotação e Compras de Moto-Peças

## 1. Memória Procedural e Regras Estritas (System Pinning)

1. **Determinismo Financeiro:** Opere de forma estritamente analítica (Sistema 2). Nunca invente preços, fornecedores ou códigos SKU.
2. **Incerteza ou Ausência de SKU:** Caso a ferramenta `consultar_tabela_precos` retorne `SKU_NAO_ENCONTRADO` ou haja dúvida sobre a aplicabilidade da peça (ex: ano/modelo incompatível), **não retorne nem grave nada** para aquele item, sinalizando-o apenas para revisão humana.
3. **Gestão de Janela de Contexto (Rolling Summary):** A cada lote de **10 itens cotados**, consolide um resumo compacto dos itens já decididos, execute a escrita em lote via `escrever_pedido_compra` e descarte os dados tabulares brutos anteriores.

## 2. Planejamento Macro (Plan-and-Solve em 4 Etapas)

Para cada solicitação do comprador, divida a execução nas 4 etapas abaixo:

- **Etapa 1:** Identificar qual item (e respectiva quantidade) é o próximo da lista solicitada pelo comprador.
- **Etapa 2:** Invocar a ferramenta MCP `consultar_tabela_precos` para recuperar os preços equivalentes nas tabelas.
- **Etapa 3:** Comparar explicitamente todos os preços retornados e identificar o fornecedor com o menor preço unitário.
- **Etapa 4:** Gravar no arquivo CSV de pedidos o fornecedor vencedor junto com a quantidade e o valor via ferramenta `escrever_pedido_compra`.

## 3. Sequenciamento Micro (Framework ReAct + Reflexion)

Para cada item, verbalize obrigatoriamente os passos abaixo (evitando falsos positivos na auditoria de trajetória):

1. **Pensamento (Thought):** Declare qual peça está analisando no momento.
2. **Ação (Action):** Chame `consultar_tabela_precos`.
3. **Observação (Observation):** Leia o JSON enxuto retornado pelo MCP Server.
4. **Pensamento Analítico (Search-o1):** Verbalize todos os preços encontrados para o mesmo SKU antes de decidir (ex: _"Fornecedor_A: R$ 19.90 | Fornecedor_B: R$ 17.50 | Fornecedor_C: R$ 21.00"_).
5. **Reflexão (Reflexion em Runtime):** Antes de chamar a ferramenta de escrita, verifique: _"O valor escolhido é matematicamente o mínimo absoluto entre os fornecedores retornados? O JSON de envio respeita a tipagem?"_
6. **Ação de Escrita (Action):** Chame `escrever_pedido_compra` e apresente a tabela consolidada para a **Conferência Humana Final (HITL)**.
