import json
from pathlib import Path

import pytest

from ai_radar.scoring import InfluenceConfigError, load_influence_config


def test_load_influence_config_reads_institutions_people_and_domains(tmp_path: Path):
    path = tmp_path / "influence_sources.json"
    path.write_text(
        json.dumps(
            {
                "institutions": [{"name": "OpenAI", "aliases": ["openai"], "weight": 25}],
                "people": [{"name": "Yann LeCun", "aliases": ["yann lecun"], "weight": 20}],
                "source_domains": [{"domain": "openai.com", "weight": 18}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    config = load_influence_config(path)

    assert config.institutions[0].name == "OpenAI"
    assert config.people[0].aliases == ["yann lecun"]
    assert config.source_domains[0].domain == "openai.com"


def test_load_influence_config_reports_broken_json_path(tmp_path: Path):
    path = tmp_path / "influence_sources.json"
    path.write_text("{broken", encoding="utf-8")

    with pytest.raises(InfluenceConfigError) as error:
        load_influence_config(path)

    assert str(path) in str(error.value)
    assert "JSON" in str(error.value)
