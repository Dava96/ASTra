[tool.pytest.ini_options]
addopts = "--cov=src --cov-report=term-missing --cov-fail-under=80"
testpaths = ["tests"]

[tool.coverage.report]
show_missing = true
skip_covered = true
fail_under = 80

[tool.ruff]
line-length = 88
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "S"]
ignore = ["S101"] # Allow asserts in tests