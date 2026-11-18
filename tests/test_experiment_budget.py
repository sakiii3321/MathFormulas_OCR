from concurrent.futures import ThreadPoolExecutor

import pytest

from tools.ocr_experiment import Ledger


def test_reservations_survive_restart_and_count_failures(tmp_path):
    path = tmp_path / 'ledger.db'
    ledger = Ledger(path, 2)
    first = ledger.reserve('first', {})
    ledger.finish(first, 'error', {'error': 'timeout'})
    restarted = Ledger(path, 2)
    assert restarted.reserve('first', {}) is None
    assert restarted.reserve('second', {})
    with pytest.raises(RuntimeError, match='budget'):
        restarted.reserve('third', {})
    assert restarted.counts() == {'error': 1, 'reserved': 1}


def test_concurrent_reservations_cannot_exceed_limit(tmp_path):
    ledger = Ledger(tmp_path / 'ledger.db', 7)
    def reserve(index):
        try:
            return ledger.reserve(str(index), {})
        except RuntimeError:
            return None
    with ThreadPoolExecutor(max_workers=6) as pool:
        assert sum(value is not None for value in pool.map(reserve, range(20))) == 7
    assert ledger.counts() == {'reserved': 7}
