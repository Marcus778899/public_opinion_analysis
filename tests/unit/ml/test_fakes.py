from radar.common.enums import Polarity
from radar.ml.training.classifier import Classifier
from tests.unit.ml.fakes import FakeClassifier


def test_fake_classifier_satisfies_classifier_interface():
    classifier: Classifier = FakeClassifier()

    result = classifier.predict_proba(["a", "b"])

    assert len(result) == 2
    assert all(set(r) == set(Polarity) and abs(sum(r.values()) - 1) < 1e-9 for r in result)


def test_fake_classifier_empty_input_returns_empty_and_records_call():
    fake = FakeClassifier()

    assert fake.predict_proba([]) == []
    assert fake.calls == [[]]
