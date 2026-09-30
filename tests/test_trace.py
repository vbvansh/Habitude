from habitude.trace import Step, Target, Trace


def test_trace_round_trips_through_json(tmp_path):
    trace = Trace(
        task='Enter "Jerald" and press Submit.',
        source="test",
        steps=[
            Step(index=1, action="type", value="Jerald", target=Target(role="textbox", attrs={"id": "tt"})),
            Step(index=2, action="click", target=Target(role="button", name="Submit")),
        ],
    )
    path = tmp_path / "trace.json"
    trace.save(path)

    loaded = Trace.load(path)

    assert loaded == trace


def test_target_description_prefers_name_then_id():
    assert Target(role="button", name="Submit").describe() == 'button "Submit"'
    assert Target(role="textbox", attrs={"id": "tt"}).describe() == "textbox #tt"
    assert Target(tag="div").describe() == "div"
