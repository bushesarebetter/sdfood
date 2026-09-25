"""deploy_api.py: an image goes only to a registry whose privacy is checked or explicitly confirmed."""
import pytest

import deploy_api as d


def test_registry_host_follows_dockers_rules():
    assert d.registry_host("someone/sdfood-api") == ("docker.io", "someone/sdfood-api")
    assert d.registry_host("docker.io/someone/sdfood-api") == ("docker.io", "someone/sdfood-api")
    assert d.registry_host("ghcr.io:443/owner/sdfood-api") == ("ghcr.io", "owner/sdfood-api")
    assert d.registry_host("GHCR.IO/owner/x")[0] == "ghcr.io"
    assert d.github_package("ghcr.io:443/owner/sdfood-api") == ("owner", "sdfood-api")


@pytest.mark.parametrize("image", ["someone/sdfood-api", "docker.io/someone/sdfood-api", "registry.example.com/x/y"])
def test_unverifiable_registries_are_refused_unless_confirmed(image, capsys):
    with pytest.raises(d.Refused, match="cannot check"):
        d.ensure_private(image, pushed=False)
    d.ensure_private(image, pushed=False, confirmed_private=True)
    assert "you confirmed" in capsys.readouterr().out


def test_ghcr_with_a_port_is_still_checked_on_github():
    calls = []

    def gh(args):
        calls.append(args)
        return "owner\n" if args[1] == "user" else "public\n"
    with pytest.raises(d.Refused, match="public"):
        d.ensure_private("ghcr.io:443/owner/sdfood-api", pushed=True, gh=gh)
    assert calls, "the visibility was looked up"
