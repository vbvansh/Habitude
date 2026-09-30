from habitude.params import detect_params, task_template
from habitude.trace import Step, Target, Trace


def _trace(task, *steps):
    return Trace(task=task, source="test", steps=[s.model_copy(update={"index": i}) for i, s in enumerate(steps, 1)])


def test_typed_value_from_task_becomes_parameter():
    trace = _trace(
        'Enter "Jerald" into the text field and press Submit.',
        Step(index=0, action="type", value="Jerald", target=Target(role="textbox", attrs={"id": "tt"})),
        Step(index=0, action="click", target=Target(role="button", name="Submit")),
    )
    [param] = detect_params(trace)

    assert (param.name, param.example, param.field, param.steps) == ("text", "Jerald", "value", [1])


def test_quoted_click_label_becomes_parameter_but_unquoted_does_not():
    trace = _trace(
        'Click on the "Ok" button, then press Submit.',
        Step(index=0, action="click", target=Target(role="button", name="Ok")),
        Step(index=0, action="click", target=Target(role="button", name="Submit")),
    )
    [param] = detect_params(trace)

    assert (param.name, param.example, param.field) == ("button", "Ok", "name")


def test_names_come_from_field_attributes_and_stay_unique():
    trace = _trace(
        "Send mail to a@example.com and b@example.com",
        Step(index=0, action="type", value="a@example.com", target=Target(attrs={"name": "to"})),
        Step(index=0, action="type", value="b@example.com", target=Target(attrs={"placeholder": "E-mail CC"})),
        Step(index=0, action="type", value="a@example.com", target=Target(attrs={"name": "to"})),
    )
    params = detect_params(trace)

    assert [(p.name, p.steps) for p in params] == [("to", [1, 3]), ("e_mail_cc", [2])]


def test_values_not_in_task_and_secrets_stay_fixed():
    trace = _trace(
        "Log in",
        Step(index=0, action="type", value="admin", target=Target(role="textbox")),
        Step(index=0, action="type", value="{{secret:password}}", target=Target(role="textbox")),
    )
    assert detect_params(trace) == []


def test_task_template_replaces_whole_words_only():
    trace = _trace(
        'Click "Ok" to book it',
        Step(index=0, action="click", target=Target(role="button", name="Ok")),
    )
    assert task_template(trace.task, detect_params(trace)) == 'Click "{button}" to book it'
