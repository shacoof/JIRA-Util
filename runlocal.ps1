cd C:\Users\Shacoof\Documents\code\BuildFlaskDocer
$env:FLASK_APP = "app.py"
$env:FLASK_ENV = "development"
$env:FLASK_DEBUG = "1"
python -m flask run --host=0.0.0.0