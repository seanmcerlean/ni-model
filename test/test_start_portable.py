import uuid

from scripts import start_portable


class FakeQuery:
    def __init__(self, pending):
        self.pending = pending

    def filter(self, *_args):
        return self

    def order_by(self, *_args):
        return self

    def all(self):
        return [(run_id,) for run_id in self.pending]


class FakeSession:
    def __init__(self, pending):
        self.pending = pending
        self.closed = False

    def query(self, *_args):
        return FakeQuery(self.pending)

    def close(self):
        self.closed = True


def test_portable_startup_recovers_and_resubmits_pending_runs(monkeypatch):
    pending = [uuid.uuid4(), uuid.uuid4()]
    session = FakeSession(pending)

    def session_factory():
        return session

    monkeypatch.setattr(start_portable, "recover_interrupted_runs", lambda db: 1)
    monkeypatch.setattr(start_portable, "cleanup_expired_runs", lambda db: 0)
    submitted = []
    monkeypatch.setattr(
        start_portable,
        "submit_run",
        lambda run_id, factory: submitted.append((run_id, factory)),
    )

    recovered = start_portable.recover_portable_runtime(session_factory)

    assert recovered == pending
    assert submitted == [(run_id, session_factory) for run_id in pending]
    assert session.closed
