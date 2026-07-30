import os
import sys


def test_project_structure():
    """Test that project structure is correct"""
    assert os.path.exists("src/ni_model/__init__.py")
    assert os.path.exists("test/__init__.py")
    assert os.path.exists("pyproject.toml")


def test_package_import():
    """Test that package can be imported"""
    sys.path.insert(0, "src")
    try:
        import ni_model

        assert ni_model is not None
    except ImportError:
        assert False, "Failed to import ni_model package"


def test_pyproject_toml_exists():
    """Test that pyproject.toml exists and is valid"""
    assert os.path.exists("pyproject.toml")

    with open("pyproject.toml", "r") as f:
        content = f.read()
        assert "[tool.black]" in content
        assert "[tool.isort]" in content
        assert "[tool.pytest.ini_options]" in content
