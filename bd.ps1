$env:FLASK_ENV = "development"
Set-Location  C:\Users\Shacoof\Documents\code\BuildFlaskDocer
try {
    docker stop $(docker ps -q)    
}
catch {
    Write-Output "nothing to stop"
}

docker build -t shacoof/yhw .
docker run -p 5000:5000 shacoof/yhw
docker ps
