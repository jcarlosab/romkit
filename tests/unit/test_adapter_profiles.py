import pytest
from romkit_core.adapters.registry import enabled_adapters, adapter_for_archive


@pytest.mark.parametrize('profile,expected', [('base',[]),('all',['pokapoka','digimon']),('digimon',['digimon']),('pokapoka',['pokapoka'])])
def test_profiles_enable_only_selected_adapters(monkeypatch, profile, expected):
    monkeypatch.setenv('ROMKIT_PROFILE',profile)
    assert [a.id for a in enabled_adapters()] == expected
    assert bool(adapter_for_archive('PSP_GAME/USRDIR/ARCVINFO.BIN')) == ('digimon' in expected)


def test_invalid_profile_rejected(monkeypatch):
    monkeypatch.setenv('ROMKIT_PROFILE','typo')
    with pytest.raises(ValueError):
        enabled_adapters()
