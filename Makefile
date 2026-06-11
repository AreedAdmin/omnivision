.PHONY: setup server dashboard tunnel

setup:
	cd server && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
	cd dashboard && npm install

server:
	cd server && .venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000

dev-server:
	cd server && .venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 --reload

dashboard:
	cd dashboard && npm run dev

tunnel:
	ngrok http 8000
