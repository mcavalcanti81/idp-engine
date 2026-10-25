import pytest

from idp_engine.policy import compliance, components, config, manifests, versioning
from idp_engine.policy.compliance import Gate, GateResult
from idp_engine.policy.versioning import Bump

REPO = """
apiVersion: plat-idplabs/v1
kind: Repository
metadata: {system: exemplo, owner: marquinho}
spec:
  compliance: {level: 2, mode: block}
  engine: {version: v0.1.0}
  layout: {components: [apps/*]}
  delivery:
    environmentsRepo: github.com/x/ambientes
    environments:
      - {name: dev, namespace: "{system}-dev", autoPromote: true}
      - {name: prod, namespace: "{system}", approvers: [marquinho]}
  overrides:
    components:
      - {path: apps/legado, compliance: {level: 0}}
"""


class TestConfig:
    def test_parse_repository(self):
        repo = config.parse_repository(REPO)
        assert repo.level == 2
        assert repo.environments[0].namespace == "exemplo-dev"
        assert repo.environments[0].auto_promote
        assert repo.level_for("apps/legado/") == 0
        assert repo.level_for("apps/api") == 2

    def test_reports_every_problem(self):
        bad = REPO.replace("level: 2", "level: 7").replace("v0.1.0", "latest").replace("kind: Repository", "kind: X")
        with pytest.raises(config.ConfigError) as err:
            config.parse_repository(bad)
        msg = str(err.value)
        assert "level" in msg and "latest" in msg and "kind" in msg

    def test_stack_from_pipeline_template(self):
        svc = config.parse_service(
            "apiVersion: plat-idplabs/v1\nkind: Service\n"
            "metadata: {name: a, owner: b, system: c}\n"
            "spec: {type: backend-api, pipelineTemplate: python-api/release@v1}\n"
        )
        assert svc.stack == "python"


class TestComponents:
    def test_discover_respects_globs(self):
        paths = ["apps/a/service.yaml", "apps/b/service.yaml", "tools/x/service.yaml", "apps/a/README.md"]
        assert components.discover(paths, ("apps/*",)) == ["apps/a", "apps/b"]

    def test_affected(self):
        comps = ["apps/a", "apps/b"]
        assert components.affected(comps, ["apps/a/main.py"]) == ["apps/a"]
        assert components.affected(comps, ["platform.yaml"]) == comps
        assert components.affected(comps, None) == comps


class TestCompliance:
    def test_levels_are_cumulative(self):
        for lvl in (1, 2, 3):
            assert set(compliance.gates_for_level(lvl - 1)) <= set(compliance.gates_for_level(lvl))
        assert Gate.SBOM not in compliance.gates_for_level(1)
        assert Gate.SBOM in compliance.gates_for_level(2)

    def test_verdict_by_mode(self):
        results = [GateResult("a", Gate.TEST, False)]
        assert compliance.verdict(results, "block")[0] is False
        assert compliance.verdict(results, "warn")[0] is True
        assert compliance.verdict(results, "observe")[0] is True


class TestVersioning:
    @pytest.mark.parametrize(
        "messages,bump",
        [
            (["fix: a"], Bump.PATCH),
            (["fix: a", "feat(api): b"], Bump.MINOR),
            (["feat!: c"], Bump.MAJOR),
            (["chore: x\n\nBREAKING CHANGE: y"], Bump.MAJOR),
            (["docs: x", "chore(release): v1 [skip ci]", "não convencional"], Bump.NONE),
        ],
    )
    def test_bump(self, messages, bump):
        commits = [c for c in map(versioning.parse_commit, messages) if c]
        assert versioning.bump_for(commits) is bump

    @pytest.mark.parametrize(
        "current,bump,expected",
        [
            (None, Bump.PATCH, "0.1.0"),
            ("1.2.3", Bump.PATCH, "1.2.4"),
            ("1.2.3", Bump.MINOR, "1.3.0"),
            ("1.2.3", Bump.MAJOR, "2.0.0"),
            ("0.4.1", Bump.MAJOR, "0.5.0"),
            ("1.2.3", Bump.NONE, None),
        ],
    )
    def test_next_version(self, current, bump, expected):
        assert versioning.next_version(current, bump) == expected

    def test_tags(self):
        assert versioning.tag_name("api", "1.0.0", single_component=True) == "v1.0.0"
        assert versioning.tag_name("api", "1.0.0", single_component=False) == "api/v1.0.0"
        assert versioning.version_from_tag("api/v1.0.0") == "1.0.0"

    def test_conventions(self):
        assert versioning.is_valid_branch("feat/nova-rota")
        assert not versioning.is_valid_branch("minha-branch")
        assert versioning.is_valid_title("feat(api): adiciona rota")
        assert not versioning.is_valid_title("Adiciona rota")


def test_pin_image_replaces_existing_entry():
    text = "resources: [deployment.yaml]\nimages:\n- name: api\n  newName: old\n  newTag: '1'\n"
    out = manifests.pin_image(text, "api", "ghcr.io/x/api", "sha256:abc")
    assert "sha256:abc" in out and "old" not in out and "deployment.yaml" in out
