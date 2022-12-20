mkdir -p htmlcov/
touch htmlcov/.ignore

pytest --cov=rirb --cov-report html test.py
