import subprocess
import sys
from pathlib import Path

def main():
    projektordner = Path(__file__).resolve().parent
    app_py = projektordner / "app.py"

    p = subprocess.Popen([sys.executable, "-m", "streamlit", "run", str(app_py)])
    p.wait()

if __name__ == "__main__":
    main()
