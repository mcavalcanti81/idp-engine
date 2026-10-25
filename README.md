# idp-engine

Engine de pipeline portátil do **plat-idplabs**, em [Dagger](https://dagger.io) com SDK Python. O mesmo pipeline roda em qualquer CI e na máquina do desenvolvedor. Modelo descrito na ADR-0006 do plat-idplabs.

## Entradas públicas

| Função | Quando | O que faz |
|---|---|---|
| `check` | PR | Valida `platform.yaml`, descobre componentes afetados e roda os gates do nível de compliance |
| `release` | Merge na `main` | Calcula a versão (Conventional Commits), publica a imagem, fixa o digest no overlay, gera changelog e cria a tag |
| `promote` | — | Ainda não implementado. Hoje a promoção é um PR manual no repositório de ambientes |

## Níveis de compliance

| Nível | Gates |
|---|---|
| 0 | build, test |
| 1 | + conventions, lint, secrets-scan, sast |
| 2 | + dependency-scan, image-scan, sbom (bloqueia CRITICAL) |
| 3 | igual ao 2, bloqueando HIGH e CRITICAL. Proveniência SLSA ainda não implementada |

Modo por repositório: `observe` e `warn` só reportam; `block` reprova o pipeline.

## Stacks suportadas

- `python` (`pipelineTemplate: python-api/...`): uv + pytest, ruff, bandit.

## Uso

No repositório consumidor, um gatilho fino:

```yaml
jobs:
  plataforma:
    uses: mcavalcanti81/idp-engine/.github/workflows/run.yml@v0.1.0
```

Localmente:

```bash
dagger call -m github.com/mcavalcanti81/idp-engine@v0.1.0 check --source .
dagger call -m github.com/mcavalcanti81/idp-engine@v0.1.0 release --source . --repository owner/repo --dry-run
```

## Estrutura

```
src/idp_engine/
  main.py      # check e release: só orquestram
  policy/      # regras puras, sem IO — testadas com pytest
  stacks/      # um módulo por ecossistema
  ops/         # scanners, git, registry
tests/         # testes das políticas
```

A direção de dependência é `main → stacks/ops → policy`.

## Desenvolvimento

```bash
dagger develop          # gera o SDK em sdk/
uv run pytest -q
uv run ruff check src tests
```
