import subprocess
import sys
import requests
import pandas as pd


def rodar_screener():
    print(" Buscando Top Oportunidades do Mercado...")
    url = "https://api.llama.fi/protocols"

    try:
        res = requests.get(url, timeout=10).json()
    except requests.exceptions.RequestException as e:
        print(f"⚠️ Erro ao buscar dados do DefiLlama: {e}")
        return
    except ValueError as e:
        print(f"⚠️ Resposta inválida da API: {e}")
        return

    lista_dados = []
    for item in res[:15]:
        slug = item.get('slug')
        simbolo = item.get('symbol')
        tvl = item.get('tvl', 0)
        mudanca_7d = item.get('change_7d') or 0
        mcap = item.get('mcap') or 0

        mcap_tvl_ratio = (mcap / tvl) if tvl > 0 else 50
        score = (mudanca_7d * 1.5) - (mcap_tvl_ratio * 0.5)

        lista_dados.append({
            'Slug': slug,
            'Símbolo': simbolo,
            'TVL ($)': f"${tvl:,.0f}",
            'Crescimento 7d (%)': round(mudanca_7d, 2),
            'Score': round(score, 2)
        })

    df = pd.DataFrame(lista_dados)
    df = df.sort_values(by='Score', ascending=False).reset_index(drop=True)

    # Exibe a tabela no terminal
    print("\n--- RANKING DE POTENCIAL ---")
    print(df[['Símbolo', 'Slug', 'Crescimento 7d (%)', 'Score']])
    print("----------------------------\n")

    # Pergunta qual cripto você quer investigar a fundo
    escolha = input("Digite o Slug/Símbolo da moeda que deseja analisar (ou Pressione Enter para sair): ").strip()

    if escolha:
        # sys.executable garante que usa o mesmo interpretador Python que
        # está rodando este script (em vez de "python", que não existe
        # em algumas distros/ambientes onde só há "python3")
        subprocess.run([sys.executable, "analisador.py", escolha])


if __name__ == '__main__':
    rodar_screener()