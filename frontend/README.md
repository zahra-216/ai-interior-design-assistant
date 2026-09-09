# Frontend (React)

To be set up with:
```
npx create-react-app .
```
or Vite:
```
npm create vite@latest . -- --template react
```

Will contain:
- Chat interface (connects to Agent 1)
- Design layout viewer (connects to Agent 2)
- Furniture list display (connects to Agent 3)
- Cost breakdown summary (connects to Agent 4)

Connects to each agent via REST API (base URLs configurable in `.env`).
