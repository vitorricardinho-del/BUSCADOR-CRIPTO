import os
from dotenv import load_dotenv
load_dotenv()  # carrega .env em dev; no Railway as env vars já vêm setadas

from flask import Flask, render_template, jsonify
import requests
from analisador import analisar_cripto_detalhada, buscar_noticias

app = Flask(__name__)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/screener')
def api_screener():
    try:
        res = requests.get("https://api.llama.fi/protocols", timeout=10).json()
        lista_dados = []
        for item in res[:12]:
            slug = item.get('slug')
            # Nem todo protocolo tem 'symbol' preenchido na API (vem null
            # às vezes, geralmente protocolos sem token próprio). Nesse
            # caso cai pro nome, e em último caso pro slug.
            simbolo = item.get('symbol') or item.get('name') or slug
            tvl = item.get('tvl', 0)
            mudanca_7d = item.get('change_7d') or 0
            mcap = item.get('mcap') or 0

            mcap_tvl_ratio = (mcap / tvl) if tvl > 0 else 50
            score = (mudanca_7d * 1.5) - (mcap_tvl_ratio * 0.5)

            lista_dados.append({
                'slug': slug,
                'simbolo': simbolo,
                'tvl': tvl,
                'crescimento_7d': round(mudanca_7d, 2),
                'score': round(score, 2)
            })

        lista_dados = sorted(lista_dados, key=lambda x: x['score'], reverse=True)
        return jsonify(lista_dados)
    except requests.exceptions.RequestException as e:
        return jsonify({"erro": f"Falha ao consultar DefiLlama: {e}"}), 502
    except Exception as e:
        return jsonify({"erro": str(e)}), 500


@app.route('/api/analisar/<slug>')
def api_analisar(slug):
    # analisar_cripto_detalhada agora retorna um dict de verdade
    # (antes a função só dava print e devolvia None -> jsonify(None))
    dados = analisar_cripto_detalhada(slug)

    if not dados.get("sucesso"):
        return jsonify(dados), 404

    return jsonify(dados)


@app.route('/api/noticias/<simbolo>')
def api_noticias(simbolo):
    try:
        noticias = buscar_noticias(simbolo)
        analise_ia = analisar_sentimento(noticias, simbolo)
        return jsonify({"simbolo": simbolo.upper(), "noticias": noticias, "analise_ia": analise_ia})
    except Exception as e:
        return jsonify({"erro": str(e)}), 500


if __name__ == '__main__':
    # Em produção (Railway) o gunicorn cuida de servir a aplicação -
    # esse bloco só roda quando você executa "python app.py" localmente.
    porta = int(os.environ.get("PORT", 5000))

    # host='0.0.0.0' abre o servidor pra outros dispositivos na sua rede
    # local (ex: testar pelo celular). Com '127.0.0.1' (padrão) só sua
    # própria máquina consegue acessar.
    app.run(host='0.0.0.0', port=porta, debug=True)
