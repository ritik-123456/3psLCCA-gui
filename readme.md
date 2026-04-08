# 3psLCCA — Life Cycle Cost Analysis for Bridge Projects

A desktop application built with Python and PySide6 for performing Life Cycle Cost Analysis (LCCA) on bridge infrastructure projects.

---

## Requirements

- Python >= 3.12
- Git

---

## Installation

**1. Clone the repository**

```bash
git clone https://github.com/swas02/3psLCCA-gui.git
cd 3psLCCA-gui
```

**2. Clone the core engine inside the project root**

```bash
git clone https://github.com/swas02/3psLCCA-core.git
```

This places `3psLCCA-core/` inside `3psLCCA-gui/`, which is where `requirements.txt` expects it.

---

**3. Create and activate a virtual environment**

```bash
python -m venv venv
```

### ▶ Windows (PowerShell)

```bash
venv\Scripts\activate
```

⚠️ **If you get an execution policy error**, run:

```bash
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Then try activating again:

```bash
venv\Scripts\activate
```

> This error occurs because PowerShell restricts running scripts by default.

---

### ▶ Windows (Command Prompt)

```bash
venv\Scripts\activate
```

---

### ▶ macOS / Linux

```bash
source venv/bin/activate
```

---

**4. Install dependencies**

```bash
pip install -r requirements.txt
```

---

## Running the Application

Make sure your virtual environment is activated, then run from the project root (the folder containing `gui/`):

```bash
python -m gui.main
```

> The app must be launched from the project root. It loads assets (stylesheet, icons) using paths relative to that directory — running it from any other location will cause missing resource warnings.

---

## Project Structure

```
3psLCCA-gui/
├── 3psLCCA-core/       # Core LCCA engine (cloned separately)
├── gui/
│   ├── main.py         # Application entry point
│   ├── components/     # UI components
│   ├── assets/         # Icons and resources
│   ├── project_controller.py
│   ├── project_manager.py
│   └── project_window.py
├── core/
├── data/
├── scripts/
├── user_projects/      # Saved LCCA project files
└── requirements.txt    # pip dependencies
```
