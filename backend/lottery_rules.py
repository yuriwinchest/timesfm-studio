"""
Regras oficiais de aposta das modalidades da Caixa.

Modulo sem dependencias: e consultado tanto pela leitura optica (para filtrar o que
pode ou nao ser dezena) quanto pela conferencia (para recusar aposta invalida).
"""

# Regras de aposta por modalidade: (minimo de dezenas, maximo de dezenas)
BET_SIZE_RULES = {
    "megasena": (6, 20),
    "quina": (5, 15),
    "lotofacil": (15, 20),
    "lotomania": (50, 50),
}

NUMBER_RANGE_RULES = {
    "megasena": (1, 60),
    "quina": (1, 80),
    "lotofacil": (1, 25),
    "lotomania": (0, 99),
}
