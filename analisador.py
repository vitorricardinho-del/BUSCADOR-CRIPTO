import os
import sys
import requests

# Token grátis: crie em https://cryptopanic.com/developers/api/keys
# Pode setar via variável de ambiente ou colar direto aqui (não recomendado
# em código versionado - prefira env var no Railway).
CRYPTOPANIC_TOKEN = os.environ.get("CRYPTOPANIC_TOKEN", "")


def buscar_noticias(simbolo, limite=5):
    """
    Busca notícias recentes sobre uma cripto.
    Tenta CryptoPanic primeiro (precisa de token grátis); se não tiver
    token ou a chamada falhar, cai pro CryptoCompare News API (público,
    sem necessidade de chave).
    Retorna sempre uma lista de dicts: [{titulo, fonte, url, data}, ...]
    """
    simbolo = simbolo.upper()
    noticias = []

    # --- Tentativa 1: CryptoPanic ---
    if CRYPTOPANIC_TOKEN:
        try:
            url = "https://cryptopanic.com/api/v2/posts/"
            params = {
                "auth_token": CRYPTOPANIC_TOKEN,
                "currencies": simbolo,
                "public": "true",
            }
            res = requests.get(url, params=params, timeout=10)
            if res.status_code == 200:
                resultados = res.json().get("results", [])[:limite]
                for item in resultados:
                    noticias.append({
                        "titulo": item.get("title"),
                        "fonte": (item.get("source") or {}).get("title", "CryptoPanic"),
                        "url": item.get("url"),
                        "data": item.get("published_at"),
                    })
                if noticias:
                    return noticias
        except requests.exceptions.RequestException:
            pass  # cai pro fallback

    # --- Fallback: CryptoCompare (público, sem token) ---
    try:
        url = "https://min-api.cryptocompare.com/data/v2/news/"

        # Tentativa A: filtro por categoria (só cobre moedas grandes tipo
        # BTC, ETH, XRP, SOL - moedas menores como AAVE não têm categoria
        # dedicada e vêm sempre vazias por esse filtro)
        params = {"categories": simbolo, "excludeCategories": "Sponsored"}
        res = requests.get(url, params=params, timeout=10)
        if res.status_code == 200:
            resultados = res.json().get("Data", [])[:limite]
            for item in resultados:
                noticias.append({
                    "titulo": item.get("title"),
                    "fonte": item.get("source_info", {}).get("name", "CryptoCompare"),
                    "url": item.get("url"),
                    "data": item.get("published_on"),
                })

        # Tentativa B: se a categoria não trouxe nada, busca no feed geral
        # e filtra por palavra-chave no título (cobre moedas menores)
        if not noticias:
            res_geral = requests.get(url, params={"excludeCategories": "Sponsored"}, timeout=10)
            if res_geral.status_code == 200:
                todas = res_geral.json().get("Data", [])
                for item in todas:
                    titulo = item.get("title", "")
                    if simbolo.lower() in titulo.lower():
                        noticias.append({
                            "titulo": titulo,
                            "fonte": item.get("source_info", {}).get("name", "CryptoCompare"),
                            "url": item.get("url"),
                            "data": item.get("published_on"),
                        })
                    if len(noticias) >= limite:
                        break
    except requests.exceptions.RequestException:
        pass

    return noticias


def analisar_cripto_detalhada(simbolo):
    """
    Busca dados detalhados de um protocolo no DefiLlama.
    Retorna sempre um dict (mesmo em erro), pra poder ser usado
    tanto via CLI (monitor.py) quanto via API (app.py).
    """
    resultado = {
        "simbolo": simbolo.upper(),
        "sucesso": False,
        "nome": None,
        "categoria": None,
        "chain": None,
        "site": None,
        "twitter": None,
        "tvl_atual": 0,
        "erro": None,
        "noticias": [],
    }

    try:
        url = f"https://api.llama.fi/protocol/{simbolo.lower()}"
        res = requests.get(url, timeout=10)

        if res.status_code == 200:
            dados = res.json()

            # IMPORTANTE: nesse endpoint (singular /protocol/{slug}),
            # 'tvl' vem como uma LISTA de históricos
            # [{"date": ..., "totalLiquidityUSD": ...}, ...]
            # e não como um número, ao contrário do /protocols (plural).
            tvl_historico = dados.get("tvl", [])
            tvl_atual = 0
            if isinstance(tvl_historico, list) and tvl_historico:
                tvl_atual = tvl_historico[-1].get("totalLiquidityUSD", 0)
            elif isinstance(tvl_historico, (int, float)):
                # fallback, caso a API mude o formato no futuro
                tvl_atual = tvl_historico

            resultado.update({
                "sucesso": True,
                "nome": dados.get("name"),
                "categoria": dados.get("category"),
                "chain": dados.get("chain"),
                "site": dados.get("url"),
                "twitter": dados.get("twitter"),
                "tvl_atual": tvl_atual,
            })
        else:
            resultado["erro"] = f"Métricas não encontradas para '{simbolo}' (status {res.status_code})"

        # Notícias busca independente do sucesso das métricas -
        # às vezes o protocolo não tem TVL mas tem cobertura de notícia
        resultado["noticias"] = buscar_noticias(simbolo)

    except requests.exceptions.RequestException as e:
        resultado["erro"] = f"Erro de conexão: {e}"
    except Exception as e:
        resultado["erro"] = f"Erro inesperado: {e}"

    return resultado


def imprimir_relatorio(dados):
    """Formata e imprime no terminal o dict retornado por analisar_cripto_detalhada."""
    print(f"\n==========================================")
    print(f" 🔍 RAIO-X DETALHADO: {dados['simbolo']}")
    print(f"==========================================\n")

    if dados["sucesso"]:
        print(f"📌 Nome Oficial: {dados['nome']}")
        print(f"📌 Categoria: {dados['categoria']}")
        print(f"📌 Cadeia (Blockchain): {dados['chain']}")
        print(f"📌 Site Oficial: {dados['site']}")
        print(f"📌 Twitter Oficial: {dados['twitter']}")
        print(f"📌 TVL Atual: ${dados['tvl_atual']:,.2f}")
    else:
        print(f"⚠️ {dados['erro']}")

    print("\n[+] Checando Volume Social & Atividade no GitHub...")
    print(f" └─ Status: Pronto para integrar chave de API para {dados['simbolo']}\n")

    print("📰 Últimas Notícias:")
    if dados["noticias"]:
        for n in dados["noticias"]:
            print(f" • {n['titulo']} ({n['fonte']})")
            print(f"   {n['url']}")
    else:
        print(" └─ Nenhuma notícia encontrada (ou CRYPTOPANIC_TOKEN não configurado).\n")


if __name__ == '__main__':
    # Permite executar diretamente pelo terminal: python analisador.py SOL
    if len(sys.argv) > 1:
        cripto_escolhida = sys.argv[1]
    else:
        cripto_escolhida = input("Digite o símbolo/slug da cripto para analisar: ")

    resultado = analisar_cripto_detalhada(cripto_escolhida)
    imprimir_relatorio(resultado)
