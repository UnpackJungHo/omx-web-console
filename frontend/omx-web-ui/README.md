# OMX-F Web UI

Phase 3 frontend for OMX Web Control.

## Run

Start the backend first if ROS status and joint states should be live:

```bash
/home/kjhz/omx_web_ws/backend/scripts/run_backend.sh
```

Then start the frontend:

```bash
cd /home/kjhz/omx_web_ws/frontend/omx-web-ui
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

Open:

```text
http://127.0.0.1:5173/
```

Default backend endpoints:

```text
HTTP http://127.0.0.1:8000
WS   ws://127.0.0.1:8000/ws/state
```

Override with:

```bash
VITE_OMX_API_BASE=http://127.0.0.1:8000 VITE_OMX_WS_BASE=ws://127.0.0.1:8000 npm run dev
```

## Unity WebGL

The Unity canvas looks for this loader:

```text
public/unity-webgl/Build/build.loader.js
```

The planned Unity build output is:

```text
/home/kjhz/omx_web_ws/unity-webgl/build
```

After Unity WebGL Build Support is installed and the build succeeds, sync the output into the Vite public folder:

```bash
/home/kjhz/omx_web_ws/scripts/sync_unity_webgl.sh
```

React sends live joint states to Unity with:

```javascript
unityInstance.SendMessage(
  'OmxWebJointBridge',
  'SetJointStateJson',
  JSON.stringify({ type: 'joint_state', joints })
)
```

This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the ESLint configuration

If you are developing a production application, we recommend updating the configuration to enable type-aware lint rules:

```js
export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      // Other configs...

      // Remove tseslint.configs.recommended and replace with this
      tseslint.configs.recommendedTypeChecked,
      // Alternatively, use this for stricter rules
      tseslint.configs.strictTypeChecked,
      // Optionally, add this for stylistic rules
      tseslint.configs.stylisticTypeChecked,

      // Other configs...
    ],
    languageOptions: {
      parserOptions: {
        project: ['./tsconfig.node.json', './tsconfig.app.json'],
        tsconfigRootDir: import.meta.dirname,
      },
      // other options...
    },
  },
])
```

You can also install [eslint-plugin-react-x](https://github.com/Rel1cx/eslint-react/tree/main/packages/plugins/eslint-plugin-react-x) and [eslint-plugin-react-dom](https://github.com/Rel1cx/eslint-react/tree/main/packages/plugins/eslint-plugin-react-dom) for React-specific lint rules:

```js
// eslint.config.js
import reactX from 'eslint-plugin-react-x'
import reactDom from 'eslint-plugin-react-dom'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      // Other configs...
      // Enable lint rules for React
      reactX.configs['recommended-typescript'],
      // Enable lint rules for React DOM
      reactDom.configs.recommended,
    ],
    languageOptions: {
      parserOptions: {
        project: ['./tsconfig.node.json', './tsconfig.app.json'],
        tsconfigRootDir: import.meta.dirname,
      },
      // other options...
    },
  },
])
```
