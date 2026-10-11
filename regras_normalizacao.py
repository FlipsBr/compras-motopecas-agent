# regras_normalizacao.py

# Lista de padrões para extrair os nomes das motos da descrição
PADROES_MOTOS = [
    # Combos Mistos (COLOQUE ESTES BEM NO TOPO DA LISTA, antes das famílias soltas)
    # Mega Combo Honda (Comando de Válvula)
    r'\bCBX\s*/\s*XR\s*250\s*/\s*CB\s*/\s*XRE\s*300\b',

    # Combo CB 300F Nova / Sahara Nova
    r'\bCB\s*300F\s*/\s*SAHARA\s*300\b',

    # Combo Yamaha Fazer 150 / Crosser 150
    r'\bYS\s*150\s*(?:FZ)?\s*/\s*XTZ\s*150\b',

    # Combo XLR / NX / XR 200
    r'\bXLR\s*/\s*NX\s*/\s*XR\s*200\b',
    
    # O caso maluco da CG (CG125 ano 00 e Titan 150 juntas)
    r'\bCG\s*125\s*00/150\b',
    r'\bBIZ\s*/\s*POP\s*100\b', 
    r'\bNX\s*/\s*200\s*/\s*250\s*/\s*XLR\s*125\b',
    r'\bXLR\s*125\s*/\s*NX\s*150\s*/\s*200\b', # (Esse combo triplo que já tínhamos fica aqui)

    # Família CB / CBX (Adicione a 250F perto da 300R)
    r'\bCB\s*250F?(?:\s*TWISTER)?\b', # Pega "CB 250", "CB 250F" e engole o nome "TWISTER" se tiver

    # Scooters Suzuki (Burgman)
    r'\bAN\s*125(?:I)?(?:\s*BURGMAN)?\b', # Pega "AN 125", "AN 125I" e engole "BURGMAN" junto

    # Shineray
    r'\bJET\s*(?:X\s*/\s*125X|125X|X)\b', # Pega "JET X", "JET 125X" ou o combo "JET X/125X"
    # Família BIZ
    r'\bBIZ\s*\d+[A-Z]*(?:/[0-9A-Z]+)*\b',

    # Família CB / CBX
    r'\bCB\s*300R?\b',
    r'\bCB\s*600\s*(?:F\s*)?HORNET\b',         # Pega "CB 600 HORNET", "CB600 HORNET", e "CB 600F HORNET"
    r'\bCBX\s*250\b',                          # Pega "CBX 250" ou "CBX250"

    # Família CG / Titan / Fan / Start
    # (Atualizado para pegar 125, múltiplas cilindradas e o nome START)
    r'\b(?:CG|TITAN|FAN)\s*(?:125|150|160)(?:\s*/\s*(?:125|150|160))*\s*(?:START|TITAN|FAN|CARGO)?\b',

    # Família CRYPTON
    r'\bCRYPTON\s*(?:105|115)\b',              # Agrupada: Pega "CRYPTON 105" ou "CRYPTON 115"

    # Família FAZER (Separada)
    r'\b(?:FAZER|FZ25)\s*250\b',

    # Família Scooters Honda/Yamaha (LEAD, NMAX, NEO, PCX)
    r'\bLEAD\s*110\b',
    r'\bN-?MAX\s*160\b',             # O hífen -? é opcional. Pega "N-MAX 160" e "NMAX 160"
    r'\bNEO\s*(?:AT\s*)?115\b',      # O (?:AT\s*)? é opcional. Pega tanto "NEO AT 115" quanto "NEO 115"
    r'\bPCX\s*(?:150|160)\b',

    # Família NX / Falcon
    r'\bNX\s*400(?:\s*/\s*400I)?\s*(?:FALCON)?\b', # Pega "NX 400", "NX 400/400I" e até engole o nome "FALCON" se tiver
    r'\bNX\s*(?:150|200)\b',
    # Shineray (JET atualizada para suportar 50X, PHOENIX e SHINERAY genérica)
    r'\bJET\s*(?:50X|125X|X)(?:\s*/\s*(?:50X|125X|X))*\b',
    r'\bPHOENIX\s*50\b',
    r'\bSHINERAY\s*50(?:\s*CC)?\b', # Pega "SHINERAY 50" ou "SHINERAY 50CC"

    # Scooters Honda (SH)
    r'\bSH\s*150I?\b',               # Pega SH 150 ou SH 150I

    # Quadriciclos Honda (TRX)
    r'\bTRX\s*420\b',

    # Yamaha Lander (XTZ 250)
    r'\bXTZ\s*250(?:\s*LANDER)?\b',  # Pega "XTZ 250" e engole o "LANDER" junto

    # Suzuki YES
    r'\bYES\s*125\b',

    # Família NXR / Bros / XRE (Modelos integrados)
    # (ATUALIZADA para engolir a XRE 190 junto, substituindo as versões antigas)
    r'\b(?:NXR|BROS)\s*(?:125|150|160)(?:\s*/\s*(?:125|150|160))*(?:\s*/\s*XRE\s*190)?\b',

    # Família POP
    r'\bPOP\s*(?:100|110(?:I)?)\b',            # Agrupada: Pega "POP 100", "POP 110" ou "POP 110I"

    # Família XLR / Combos Especiais
    # ATENÇÃO: Combos triplos DEVEM vir antes das motos soltas para não quebrar a captura
    r'\bXLR\s*125\s*/\s*NX\s*150\s*/\s*200\b', # Pega o bloco "XLR 125/NX 150/200" tolerando espaços perto das barras
    r'\bXLR\s*125\b',

    # Família XR / Tornado
    r'\bXR\s*200(?:R)?\b',                     # Pega "XR 200" ou "XR 200R" (muito comum nas planilhas)
    r'\bXR\s*250\s*(?:TORNADO)?\b',

    # Família XRE (Separada)
    r'\bXRE\s*300\b',

    # Família YBR / XTZ
    r'\b(?:YBR/XTZ|YBR|XTZ)\s*125\b',

    # Família YS (Yamaha)
    r'\bYS\s*(?:125|150|250)\s*FAZER\b',
]
# Dicionário de padronização de peças (De -> Para)
MAPEAMENTO_TERMOS = {
    r'\bPARAL D\b': 'PARALAMA DIANTEIRO',
    r'\bANEL T\b': 'ANEL TAMPA',
    r'\bDIANT\b|\bD\b(?=\s|$)': 'DIANTEIRO',
    r'\bTRAS\b|\bT\b(?=\s|$)': 'TRASEIRO',
    r'\bC/\b': 'COM ',
    r'\bS/\b': 'SEM ',
    r'\bPAST\b|\bPASTIL\b': 'PASTILHA',
    r'\bAMORT\b': 'AMORTECEDOR',
    r'\bCAB\b': 'CABO',
    r'\bACEL\b': 'ACELERADOR',
    r'\bEMB\b|\bEMBREAG\b': 'EMBREAGEM',
    r'\bRET\b|\bRETENT\b': 'RETENTOR',
    r'\bROL\b|\bROLAM\b': 'ROLAMENTO',
    r'\bFR\b|\bF\b(?=\s|$)': 'FREIO',
    r'\bUN\b|\bUND\b': '',     # Transforma tanto "UN" quanto "UND" em vazio (remove da string)
    r'\bDIR\b': 'DIREITO',     # Limpa o "DIR" (como em Alça Banco Direito)
    r'\bSEG\b': 'SEGMENTO',    # Transforma "ANEIS SEG" em "ANEIS SEGMENTO"
    r'\bESQ\b': 'ESQUERDO',     # Limpa o "ESQ" (como em Alça Banco Esquerdo)
    r'\bIRON\b|\bIRON\b(?=\s|$)': '',      
}

# Padrões para extrair anos com segurança (Não substitui, apenas arranca o dado)
PADROES_ANOS = [
    # Pega intervalos: 2014/2015, 14/2015, 2014/15, 14-15
    r'\b(?:19|20)?(\d{2})\s*(?:/|-)\s*(?:19|20)?(\d{2})\b',
    # Pega anos isolados de 4 dígitos (ex: 2014, 1999)
    r'\b(19\d{2}|20\d{2})\b'
]