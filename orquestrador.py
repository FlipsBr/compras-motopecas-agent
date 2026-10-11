import asyncio
import ollama
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def executar_agente():
    print("🔌 Iniciando MCP Client e conectando ao MCP Server...")
    
    # 1. Configura a conexão isolada com o seu servidor de ferramentas
    server_params = StdioServerParameters(command="python", args=["mcp_server.py"])
    
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # Descobre as ferramentas dinamicamente (consultar_tabela e escrever_pedido)
            mcp_tools = await session.list_tools()
            
            # Converte o Schema do MCP para o padrão de Tool Calling que o Ollama entende
            ollama_tools = []
            for t in mcp_tools.tools:
                ollama_tools.append({
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.inputSchema
                    }
                })

            print("📚 Carregando Memória Procedural (SKILL.md)...")
            with open("skills/cotacao-motopecas/SKILL.md", "r", encoding="utf-8") as f:
                skill_prompt = f.read()

            # Define a janela de contexto inicial
            prompt_comprador = "Cote para mim em qual fornecedor devo comprar 10 ANEL DE ESCAPE CBX250 TWISTER, 5 AMORTECEDOR PCX150 2016e 3 Pastilhas de freio aplicáveis a CB300 até ano 2010."
            
            mensagens = [
                {"role": "system", "content": f"Você é o Agente Único de Compras de Moto-Peças.\nREGRAS:\n{skill_prompt}"},
                {"role": "user", "content": prompt_comprador}
            ]

            print("\n🧠 Motor Cognitivo ativado. Iniciando Loop ReAct...\n")
            print("-" * 50)

            # 2. Inicia o Loop de Raciocínio (Pensamento -> Ação -> Observação)
            while True:
                # Chama o modelo Qwen2.5 de 14B (ou o DeepSeek-R1 que você baixou)
                resposta = ollama.chat(
                    model="qwen2.5:14b",
                    messages=mensagens,
                    tools=ollama_tools
                )
                
                msg = resposta["message"]
                mensagens.append(msg)

                # Se o modelo gerou texto (Pensamento / Reflexão), imprimimos na tela
                if msg.get("content"):
                    print(f"💭 Pensamento/Reflexão:\n{msg['content']}\n")

                # Condição de parada: Se o modelo não pediu para usar nenhuma ferramenta, o loop acaba
                if not msg.get("tool_calls"):
                    print("✅ Ciclo concluído. O agente encerrou as operações.")
                    break

                # 3. Se o modelo chamou uma ferramenta, o orquestrador executa via MCP
                for tool_call in msg["tool_calls"]:
                    nome_ferramenta = tool_call["function"]["name"]
                    argumentos = tool_call["function"]["arguments"]
                    
                    print(f"⚡ Ação (Tool Call): {nome_ferramenta}")
                    print(f"📦 Argumentos enviados: {argumentos}")
                    
                    # Chama o MCP Server e aguarda o processamento (Agentic RAG / Escrita)
                    resultado = await session.call_tool(nome_ferramenta, arguments=argumentos)
                    
                    # Extrai o texto do retorno do MCP
                    texto_retorno = "\n".join([c.text for c in resultado.content if c.type == "text"])
                    
                    # Adiciona a "Observação" na memória de curto prazo (Working Memory)
                    mensagens.append({
                        "role": "tool",
                        "name": nome_ferramenta,
                        "content": texto_retorno
                    })
                    print(f"👁️ Observação: Dados recebidos do MCP Server.\n")
                    print("-" * 50)

if __name__ == "__main__":
    # Garante que o loop assíncrono rode corretamente no Windows/Linux/Mac
    asyncio.run(executar_agente())