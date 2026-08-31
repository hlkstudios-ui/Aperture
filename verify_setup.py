#!/usr/bin/env python3
"""
Aperture Project Verification Script
Checks that all components are properly set up and ready to run.
"""

import json
from pathlib import Path

def check_python_env():
    """Check Python environment and dependencies."""
    print("\n" + "="*60)
    print("[PYTHON ENVIRONMENT CHECK]")
    print("="*60)

    # Check Python version
    import platform
    py_version = platform.python_version()
    print(f"[OK] Python Version: {py_version}")

    # Check virtual environment
    venv_path = Path("apps/api/venv")
    if venv_path.exists():
        print(f"[OK] Virtual Environment: {venv_path.resolve()}")

        # Check key packages
        try:
            import fastapi
            print(f"  [OK] FastAPI {fastapi.__version__}")
            import sqlalchemy
            print(f"  [OK] SQLAlchemy {sqlalchemy.__version__}")
            import redis
            print(f"  [OK] Redis {redis.__version__}")
            import boto3
            print(f"  [OK] Boto3 (S3) {boto3.__version__}")
            import pydantic
            print(f"  [OK] Pydantic {pydantic.__version__}")
            import jwt
            print(f"  [OK] PyJWT {jwt.__version__}")
        except ImportError as e:
            print(f"  [WARN] Missing: {e}")
            return False
    else:
        print(f"[FAIL] Virtual Environment not found: {venv_path}")
        return False

    return True

def check_node_env():
    """Check Node.js environment and dependencies."""
    print("\n" + "="*60)
    print("[NODE.JS ENVIRONMENT CHECK]")
    print("="*60)

    # Check package.json
    package_json = Path("apps/web/package.json")
    if package_json.exists():
        with open(package_json) as f:
            pkg = json.load(f)
        print(f"[OK] Project: {pkg.get('name')} v{pkg.get('version')}")
        print(f"  Dependencies: {len(pkg.get('dependencies', {}))}")
        print(f"  Dev Dependencies: {len(pkg.get('devDependencies', {}))}")

    # Check node_modules
    node_modules = Path("apps/web/node_modules")
    if node_modules.exists():
        print(f"[OK] node_modules installed: {node_modules.resolve()}")
    else:
        print("[FAIL] node_modules not found")
        return False

    # Check key dependencies
    key_packages = ["next", "react", "react-dom", "typescript"]
    for pkg in key_packages:
        pkg_path = node_modules / pkg / "package.json"
        if pkg_path.exists():
            with open(pkg_path) as f:
                pkg_data = json.load(f)
            print(f"  [OK] {pkg} {pkg_data.get('version')}")

    return True

def check_project_structure():
    """Check project file structure."""
    print("\n" + "="*60)
    print("[PROJECT STRUCTURE CHECK]")
    print("="*60)

    structure = {
        "Backend": [
            "apps/api/app/main.py",
            "apps/api/app/models.py",
            "apps/api/app/config.py",
            "apps/api/app/db.py",
            "apps/api/migrations",
            "apps/api/pyproject.toml",
        ],
        "Frontend": [
            "apps/web/app",
            "apps/web/package.json",
            "apps/web/tsconfig.json",
            "apps/web/next.config.ts",
        ],
        "Configuration": [
            ".env",
            "docker-compose.dev.yml",
        ],
        "Documentation": [
            "PROJECT_STRUCTURE.md",
            "SETUP_GUIDE.md",
            "PROJECT_DEEP_DIVE.md",
        ]
    }

    for category, files in structure.items():
        print(f"\n{category}:")
        for file in files:
            path = Path(file)
            if path.exists():
                print(f"  [OK] {file}")
            else:
                print(f"  [MISSING] {file}")

    return True

def check_python_files():
    """Count and verify Python files."""
    print("\n" + "="*60)
    print("[PYTHON FILES ANALYSIS]")
    print("="*60)

    api_app = Path("apps/api/app")
    py_files = list(api_app.glob("*.py"))
    route_files = list((api_app / "routes").glob("*.py"))

    print(f"Total Python files in app/: {len(py_files)}")
    print(f"Route files: {len(route_files)}")

    # List main files
    print("\nKey files:")
    for f in sorted(py_files)[:15]:
        print(f"  • {f.name}")

    return len(py_files) > 80

def check_typescript_files():
    """Count and verify TypeScript files."""
    print("\n" + "="*60)
    print("[TYPESCRIPT FILES ANALYSIS]")
    print("="*60)

    web_app = Path("apps/web")
    ts_files = list(web_app.glob("**/*.ts")) + list(web_app.glob("**/*.tsx"))

    # Exclude node_modules and build
    ts_files = [f for f in ts_files if "node_modules" not in f.parts and ".next" not in f.parts]

    print(f"TypeScript/TSX files: {len(ts_files)}")

    # Categories
    app_files = [f for f in ts_files if f.parts[2] == "app"]
    component_files = [f for f in ts_files if f.parts[2] == "components"]

    print(f"  • App files: {len(app_files)}")
    print(f"  • Component files: {len(component_files)}")

    return len(ts_files) > 100

def check_database_setup():
    """Check database configuration."""
    print("\n" + "="*60)
    print("[DATABASE SETUP CHECK]")
    print("="*60)

    env_file = Path(".env")
    if env_file.exists():
        labels = set()
        with open(env_file) as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                labels.add(line.partition("=")[0].strip())

        required = (
            "DATABASE_URL",
            "REDIS_URL",
            "S3_ENDPOINT",
            "S3_BUCKET",
            "S3_ACCESS_KEY",
            "S3_SECRET_KEY",
        )
        missing = []
        for label in required:
            if label in labels:
                print(f"  [OK] {label} is present")
            else:
                print(f"  [MISSING] {label}")
                missing.append(label)

        return not missing
    else:
        print("[FAIL] root .env not found")
        return False

def main():
    """Run all checks."""
    print("\n")
    print("="*60)
    print("APERTURE PROJECT - SETUP VERIFICATION")
    print("="*60)

    results = {}

    results["Python"] = check_python_env()
    results["Node.js"] = check_node_env()
    results["Structure"] = check_project_structure()
    results["Python Files"] = check_python_files()
    results["TypeScript Files"] = check_typescript_files()
    results["Database"] = check_database_setup()

    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)

    total = len(results)
    passed = sum(1 for v in results.values() if v)

    for check, result in results.items():
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status} {check}")

    print(f"\n{passed}/{total} checks passed")

    if passed == total:
        print("\n[SUCCESS] PROJECT READY TO RUN!")
        print("\nNext steps:")
        print("1. Start Docker services (or configure PostgreSQL/Redis):")
        print("   docker-compose -f docker-compose.dev.yml up -d")
        print("\n2. Start API (Terminal 1):")
        print("   scripts/run-api-dev.sh")
        print("\n3. Start Frontend (Terminal 2):")
        print("   scripts/run-web-dev.sh")
        print("\n4. Access:")
        print("   Frontend: http://localhost:3000")
        print("   API Docs: http://localhost:8001/docs")
    else:
        print("\n[WARNING] Some checks failed. Please review the output above.")

    print("\nDocumentation:")
    print("   • PROJECT_STRUCTURE.md - Detailed architecture")
    print("   • SETUP_GUIDE.md - Complete setup instructions")
    print("   • PROJECT_DEEP_DIVE.md - In-depth analysis")
    print()

if __name__ == "__main__":
    main()
