import json

from backend.adapters.state_store import load_history, save_history
from backend.models import TriageResult


def test_save_history_keeps_newest_500_in_order(tmp_path):
    state_file = tmp_path / "state.json"
    history = [
        {
            "job_id": str(index),
            "result": TriageResult(success=True, source_path=f"/source/{index}", dest_path=f"/dest/{index}"),
        }
        for index in range(510, 0, -1)
    ]

    save_history(state_file, history)
    saved = json.loads(state_file.read_text())["history"]
    loaded = load_history(state_file)

    assert len(saved) == len(loaded) == 500
    assert saved[0]["job_id"] == loaded[0]["job_id"] == "510"
    assert saved[-1]["job_id"] == loaded[-1]["job_id"] == "11"
