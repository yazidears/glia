from glia.pioneer_training import EVAL_SIZE, TRAIN_SIZE, split_examples


def test_training_examples_have_literal_spans_and_holdout() -> None:
    training, evaluation = split_examples()

    assert len(training) == TRAIN_SIZE
    assert len(evaluation) == EVAL_SIZE
    assert {row["text"] for row in training}.isdisjoint({row["text"] for row in evaluation})
    assert sum(str(row["text"]).startswith("Vull ") for row in evaluation) == 8
    assert sum(str(row["text"]).startswith("Quiero ") for row in evaluation) == 8
    assert sum(str(row["text"]).startswith("Create ") for row in evaluation) == 8

    for row in [*training, *evaluation]:
        text = row["text"]
        assert isinstance(text, str)
        structures = row["json_structures"]
        assert isinstance(structures, list)
        direction = structures[0]["visual_direction"]
        for value in direction.values():
            spans = value if isinstance(value, list) else [value]
            assert all(span in text for span in spans)
