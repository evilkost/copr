#!/bin/sh

PYTHONPATH=src:$PYTHONPATH python -B -m pytest \
    --cov-report term-missing --cov src/ \
    ./tests/ $@

#PYTHONPATH=../python/:./copr_cli:$PYTHONPATH python3 -B -m pytest --cov-report term-missing --cov ./copr_cli/ $@
