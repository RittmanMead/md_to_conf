# Contribution Guidelines


## Virtual Development Environment

It is recommended that you use a virtual environment for development.

### VENV

Create a new python virtualenv and activate it:

```less
python3 -m venv venv
source venv/bin/activate
```

### Anaconda 

[Installation Guide](https://conda.io/projects/conda/en/latest/user-guide/install/download.html)

```bash
  conda create --name md_to_conf python=3.11 --yes
  conda activate md_to_conf
```

## Requirements

Install the requirements for the application:

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

Install the module in an editable mode:

```bash
pip install -e .
```

Run `md-to-conf -h` and verify that the help is displayed.