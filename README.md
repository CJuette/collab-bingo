

Push command
```bash
docker buildx build --push --platform linux/arm/v7,linux/arm64/v8,linux/amd64 --tag cjuette/collab-bingo-multiarch:latest .
```

Run
```bash
# Either
python3 collab-bingo-server.py
# Or
docker run -p 8000:8000 cjuette/collab-bingo-multiarch:latest
```