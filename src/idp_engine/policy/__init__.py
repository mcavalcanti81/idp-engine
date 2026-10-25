"""Regras da plataforma como lógica pura: sem Dagger, sem rede, sem disco.

Tudo aqui é testável com pytest comum. O código que faz IO fica em
`ops/` e `stacks/`, e só chama estas funções para decidir o que fazer.
"""
