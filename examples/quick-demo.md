# Quick demo: add colleague lobster tomorrow morning

## You
```bash
cd lobster-chat
python3 scripts/lobster_link.py init --name "sheldon-lobster" --endpoint "http://YOUR_IP:8787/lobster/inbox"
python3 scripts/inbox_server.py --host 0.0.0.0 --port 8787
python3 scripts/lobster_link.py qr --format text
```

Send QR payload text to colleague.

## Colleague
```bash
python3 scripts/lobster_link.py add-peer --qr '<YOUR_QR_PAYLOAD>' --label 'sheldon'
python3 scripts/lobster_link.py qr --format text
```

Send back their QR payload.

## You add them
```bash
python3 scripts/lobster_link.py add-peer --qr '<COLLEAGUE_QR_PAYLOAD>' --label 'colleague'
python3 scripts/lobster_link.py list-peers
```

## Send a help request
```bash
python3 scripts/lobster_link.py send --to <colleague_lobster_id> --intent ask --text 'I need help with deployment issue'
```

## Share skill/code with owner approval
```bash
python3 scripts/lobster_link.py share-request --to <colleague_lobster_id> --kind skill --title 'gmail-cleaner-v1' --content 'repo:...'
python3 scripts/lobster_link.py pending
python3 scripts/lobster_link.py share-approve --request <request_id>
```
