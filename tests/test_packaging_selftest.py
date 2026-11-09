"""The package probe must observe fresh inference, not one final timing sample."""
from types import SimpleNamespace
import pytest
from vision_app.selftest import _observe_current_result


def service(result):
    return SimpleNamespace(latest=lambda: result)


def result(identifier, session='s1', engine='yolox'):
    return SimpleNamespace(id=identifier, metadata={'session': session, 'engine': engine})


def test_probe_counts_distinct_fresh_results_and_tolerates_gap_at_end():
    seen = set()
    for value in (None, result(1), result(1), None, result(2), None):
        _observe_current_result(service(value), seen)
    assert seen == {('s1', 1), ('s1', 2)}


def test_probe_does_not_count_missing_or_non_neural_results():
    seen = set()
    _observe_current_result(service(None), seen)
    assert not seen
    with pytest.raises(RuntimeError, match='non-neural'):
        _observe_current_result(service(result(1, engine='hog')), seen)
    assert not seen


def test_probe_distinguishes_sessions():
    seen = set()
    _observe_current_result(service(result(1)), seen)
    _observe_current_result(service(result(1, session='s2')), seen)
    assert len(seen) == 2
