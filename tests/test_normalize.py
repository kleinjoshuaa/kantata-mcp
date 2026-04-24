from kantata_assist.client import KantataClient


def test_normalize_results_orders_and_merges():
    payload = {
        "count": 1,
        "results": [{"key": "workspaces", "id": "10"}],
        "workspaces": {"10": {"id": "10", "title": "Demo"}},
    }
    rows = KantataClient.items(payload)
    assert len(rows) == 1
    assert rows[0]["title"] == "Demo"
    assert rows[0]["_type"] == "workspaces"
