import os
import sys
import time
import requests
from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai.errors import ClientError, ServerError

load_dotenv()

# --- Configurações de API & Variáveis de Ambiente ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# Cliente oficial do Google GenAI
client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

MODELO_GEMINI = "gemini-3.6-flash"
GEMINI_TIMEOUT_MS = 25_000


def chamar_gemini_com_retry(prompt, tentativas=3):
    """Executa a chamada ao Gemini com suporte a retry e backoff exponencial."""
    ultimo_erro = None
    for tentativa in range(tentativas):
        try:
            return client.models.generate_content(
                model=MODELO_GEMINI,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    http_options=types.HttpOptions(timeout=GEMINI_TIMEOUT_MS),
                )
            )
        except (ClientError, ServerError) as e:
            ultimo_erro = e
            if tentativa < tentativas - 1:
                espera = 2 ** tentativa
                print(f"⚠️ Gemini falhou (tentativa {tentativa + 1}/{tentativas}). Aguardando {espera}s... Erro: {e}")
                time.sleep(espera)
            else:
                print(f"❌ Gemini indisponível após {tentativas} tentativas: {e}")

    raise ultimo_erro


def buscar_noticias(simbolo, limite=5):
    """Busca notícias recentes sobre a criptomoeda via CryptoCompare."""
    simbolo = simbolo.upper()
    noticias = []

    try:
        url = "https://min-api.cryptocompare.com/data/v2/news/"
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


def analisar_sentimento(noticias, simbolo):
    """Analisa o sentimento das manchetes e resume em português via Gemini."""
    if not noticias:
        return {
            "sentimento": "indisponivel",
            "resumo": "Sem notícias suficientes para análise.",
            "fonte_ia": None
        }

    titulos = "\n".join(f"- {n['titulo']}" for n in noticias if n.get("titulo"))
    prompt = (
        f"Analise estas manchetes recentes sobre {simbolo.upper()} e responda "
        f"APENAS um objeto JSON válido, sem texto antes ou depois, exatamente no formato:\n"
        f'{{"sentimento": "bullish|bearish|neutro", "resumo": "1-2 frases em português explicando o porquê"}}\n\n'
        f"Manchetes:\n{titulos}"
    )

    if client:
        try:
            response = chamar_gemini_com_retry(prompt)
            parsed = _parsear_json_ia(response.text)
            if parsed:
                parsed["fonte_ia"] = "gemini"
                return parsed
        except Exception as e:
            print(f"❌ Erro ao analisar sentimento via Gemini: {e}")

    return {
        "sentimento": "indisponivel",
        "resumo": "Serviço do Gemini indisponível no momento.",
        "fonte_ia": None
    }


def _parsear_json_ia(texto):
    """Trata e extrai a estrutura JSON da resposta da IA."""
    import json
    limpo = texto.strip()
    if "```" in limpo:
        limpo = limpo.split("```")[1]
        if limpo.startswith("json"):
            limpo = limpo[4:]
    limpo = limpo.strip()
    try:
        dados = json.loads(limpo)
        return {
            "sentimento": dados.get("sentimento", "neutro"),
            "resumo": dados.get("resumo", ""),
        }
    except (json.JSONDecodeError, AttributeError):
        return None


def analisar_cripto_detalhada(simbolo):
    """Consulta DefiLlama, notícias e gera análise completa."""
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
        "analise_ia": None,
    }

    try:
        url = f"https://api.llama.fi/protocol/{simbolo.lower()}"
        res = requests.get(url, timeout=10)

        if res.status_code == 200:
            dados = res.json()
            tvl_historico = dados.get("tvl", [])
            tvl_atual = 0
            if isinstance(tvl_historico, list) and tvl_historico:
                tvl_atual = tvl_historico[-1].get("totalLiquidityUSD", 0)
            elif isinstance(tvl_historico, (int, float)):
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

        resultado["noticias"] = buscar_noticias(simbolo)
        resultado["analise_ia"] = analisar_sentimento(resultado["noticias"], simbolo)

    except requests.exceptions.RequestException as e:
        resultado["erro"] = f"Erro de conexão: {e}"
    except Exception as e:
        resultado["erro"] = f"Erro inesperado: {e}"

    return resultado


def imprimir_relatorio(dados):
    """Imprime o raio-x formatado no terminal."""
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

    print("\n📰 Últimas Notícias:")
    if dados["noticias"]:
        for n in dados["noticias"]:
            print(f" • {n['titulo']} ({n['fonte']})")
            print(f"   {n['url']}")
    else:
        print(" └─ Nenhuma notícia encontrada.\n")

    if dados.get("analise_ia"):
        ia = dados["analise_ia"]
        emoji = {"bullish": "🟢", "bearish": "🔴", "neutro": "🟡"}.get(ia["sentimento"], "⚪")
        print(f"\n{emoji} Sentimento (IA - {ia.get('fonte_ia') or 'indisponível'}): {ia['sentimento'].upper()}")
        print(f"   {ia['resumo']}")


if __name__ == '__main__':
    if len(sys.argv) > 1:
        cripto_escolhida = sys.argv[1]
    else:
        cripto_escolhida = input("Digite o símbolo/slug da cripto para analisar: ")

    resultado = analisar_cripto_detalhada(cripto_escolhida)
    imprimir_relatorio(resultado)
