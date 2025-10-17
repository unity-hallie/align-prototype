# ALIGN React Client

Modern React frontend for the ALIGN reflection system.

## Quick Start

```bash
# Install dependencies
npm install

# Start dev server (proxies to Flask on :5004)
npm run dev

# Visit http://localhost:3000
```

## Architecture

- **React 18** - UI framework
- **React Router 6** - Client-side routing
- **Zustand** - Lightweight state management
- **SCSS** - Modular styling with design system
- **Vite** - Fast build tool with HMR

## Structure

```
client/
├── src/
│   ├── components/     # Reusable UI components
│   ├── pages/          # Route pages
│   ├── hooks/          # Custom React hooks
│   ├── styles/         # SCSS modules
│   ├── api/            # API client utilities
│   ├── utils/          # Helper functions
│   ├── store.js        # Zustand state
│   ├── App.jsx         # Route definitions
│   └── main.jsx        # Entry point
├── index.html
├── vite.config.js
└── package.json
```

## Design System

See `src/styles/index.scss` for the full design system:
- CSS custom properties (variables)
- Consistent spacing scale
- Typography system
- Color palette
- Reusable SCSS mixins

## Development

The Vite dev server proxies API calls to Flask (port 5004):
- `/api/*` → Flask backend
- `/design/*` → Flask backend
- `/canvas/*` → Flask backend

Start both servers:
1. Flask: `bash start_ui.sh`
2. React: `npm run dev`