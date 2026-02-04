from pathlib import Path

from astra.tools.browser.models import A11yNode, DOMElement, ScreenshotResult


def test_screenshot_result_to_dict():
    res = ScreenshotResult(
        path=Path("shot.png"),
        url="http://foo",
        viewport=(800, 600),
        full_page=True,
        timestamp="now",
        title="Title",
        load_time_ms=100,
    )
    d = res.to_dict()
    assert d["path"] == "shot.png"
    assert d["viewport"] == [800, 600]
    assert d["load_time_ms"] == 100


def test_dom_element_to_dict():
    child = DOMElement(tag="span", text="hi")
    el = DOMElement(
        tag="div",
        id="main",
        classes=["c1", "c2"],
        role="main",
        attributes={"k": "v"},
        children=[child],
    )
    d = el.to_dict()
    assert d["tag"] == "div"
    assert d["id"] == "main"
    assert d["classes"] == ["c1", "c2"]
    assert d["attributes"] == {"k": "v"}
    assert d["children"][0]["tag"] == "span"
    assert d["children"][0]["text"] == "hi"


def test_a11y_node_to_dict():
    child = A11yNode(role="text", name="txt")
    node = A11yNode(
        role="button",
        name="Submit",
        value="val",
        description="desc",
        states=["focused"],
        children=[child],
    )
    d = node.to_dict()
    assert d["role"] == "button"
    assert d["value"] == "val"
    assert d["states"] == ["focused"]
    assert d["children"][0]["role"] == "text"
