"""Tests for the AST parser."""


import pytest

from astra.ingestion.parser import ASTParser, get_language_for_file

# Mark for integration tests requiring tree-sitter
pytest_integration = pytest.mark.skipif(
    False,  # Enabled now that tree-sitter-language-pack is compatible
    reason="Integration test - requires tree-sitter-language-pack compatibility"
)


class TestLanguageDetection:
    """Test language detection from file extensions."""

    def test_typescript_detection(self):
        assert get_language_for_file("app.ts") == "typescript"
        assert get_language_for_file("component.tsx") == "tsx"

    def test_javascript_detection(self):
        assert get_language_for_file("index.js") == "javascript"
        assert get_language_for_file("app.jsx") == "javascript"

    def test_python_detection(self):
        assert get_language_for_file("main.py") == "python"

    def test_php_detection(self):
        assert get_language_for_file("Controller.php") == "php"

    def test_unsupported_extension(self):
        assert get_language_for_file("data.csv") is None
        assert get_language_for_file("image.png") is None


class TestASTParser:
    """Test AST parsing functionality."""

    @pytest.fixture
    def parser(self):
        return ASTParser()

    @pytest.fixture
    def temp_ts_file(self, tmp_path):
        code = '''
export function greet(name: string): string {
    return `Hello, ${name}!`;
}

export class User {
    constructor(public name: string) {}
    
    sayHello() {
        return greet(this.name);
    }
}
'''
        file = tmp_path / "example.ts"
        file.write_text(code)
        return file

    @pytest.fixture
    def temp_py_file(self, tmp_path):
        code = '''
def greet(name: str) -> str:
    """Greet a person."""
    return f"Hello, {name}!"

class User:
    def __init__(self, name: str):
        self.name = name
    
    def say_hello(self) -> str:
        return greet(self.name)
'''
        file = tmp_path / "example.py"
        file.write_text(code)
        return file

    @pytest_integration
    def test_parse_typescript_file(self, parser, temp_ts_file):
        nodes = parser.parse_file(temp_ts_file)

        assert len(nodes) > 0

        # Check for function
        func_nodes = [n for n in nodes if "function" in n.type]
        assert len(func_nodes) >= 1

        # Check for class
        class_nodes = [n for n in nodes if "class" in n.type]
        assert len(class_nodes) >= 1

    @pytest_integration
    def test_parse_python_file(self, parser, temp_py_file):
        nodes = parser.parse_file(temp_py_file)

        assert len(nodes) > 0

        # Check for function
        func_nodes = [n for n in nodes if n.type == "function_definition"]
        assert len(func_nodes) >= 1

        # Check for class
        class_nodes = [n for n in nodes if n.type == "class_definition"]
        assert len(class_nodes) >= 1

    def test_parse_nonexistent_file(self, parser):
        nodes = parser.parse_file("/nonexistent/file.ts")
        assert nodes == []

    def test_parse_unsupported_file(self, parser, tmp_path):
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("a,b,c\n1,2,3")

        nodes = parser.parse_file(csv_file)
        assert nodes == []


class TestDirectoryParsing:
    """Test directory parsing functionality."""

    @pytest.fixture
    def parser(self):
        return ASTParser()

    @pytest.fixture
    def project_dir(self, tmp_path):
        # Create a mini project structure
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "index.ts").write_text("export const VERSION = '1.0.0';")
        (tmp_path / "src" / "utils.ts").write_text("export function add(a: number, b: number) { return a + b; }")
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "lib.ts").write_text("export const LIB = true;")
        return tmp_path

    @pytest_integration
    def test_parse_directory(self, parser, project_dir):
        nodes = list(parser.parse_directory(project_dir))

        # Should find nodes in src, but not in node_modules (if ignored)
        assert len(nodes) >= 1

    def test_parse_directory_with_ignore(self, parser, project_dir):
        nodes = list(parser.parse_directory(
            project_dir,
            ignore_patterns=["node_modules"]
        ))

        # Check that node_modules files are excluded
        nm_nodes = [n for n in nodes if "node_modules" in n.file_path]
        assert len(nm_nodes) == 0

    def test_parse_directory_with_max_depth(self, parser, project_dir):
        # Create a deep structure
        (project_dir / "l1").mkdir()
        (project_dir / "l1" / "f1.ts").write_text("export const L1 = 1;")
        (project_dir / "l1" / "l2").mkdir()
        (project_dir / "l1" / "l2" / "f2.ts").write_text("export const L2 = 2;")

        # Parse with depth 1 (should include root and l1, but not l2)
        # Depth 0 = root files
        # Depth 1 = root files + l1 files
        # Files in l1/l2 are at depth 2

        nodes = list(parser.parse_directory(project_dir, max_depth=1))

        paths = [n.file_path for n in nodes]
        assert any("l1" in str(p) and "l2" not in str(p) for p in paths)
        assert not any("l2" in str(p) for p in paths)

