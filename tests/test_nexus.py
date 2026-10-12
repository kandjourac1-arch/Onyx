from brain.nexus import FlashRouter


def test_flash_router_arithmetic_without_eval():
    result = FlashRouter().route("2 + 3 * 4")
    assert result and "14" in result["content"]


def test_flash_router_rejects_python_expression():
    assert FlashRouter().route("__import__('os').system('whoami')") is None
